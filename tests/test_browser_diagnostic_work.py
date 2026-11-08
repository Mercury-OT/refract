"""Optional live diagnostics cannot recursively consume unbounded body work."""
import json
from types import SimpleNamespace

import pytest

from refracto import ports
from refracto.errors import ActionFailure, ActionFailureReason as Reason
from refracto_browser import BrowserSupport
from refracto_browser._native import NativeCollector


def collector(mode="live", callback=None):
    result = NativeCollector.__new__(NativeCollector)
    result.context = SimpleNamespace(mode=mode, errors=[], permits={}, user=None,
        session_generation=0, traffic=[], diagnostics=[], mock_recordings=[],
        context_id="context")
    result.requests = {}
    result.mock_pending = []
    result.background_count = result.background_bytes = result.background_reads = 0
    result.body_reads_active = 0
    result.deferred_diagnostics = []
    result.notes = []
    result.request_namespace = "namespace"
    result.calls = []
    result.owner = SimpleNamespace(_reason=BrowserSupport._reason, _remaining=lambda _: 5000)

    def send(method, params):
        assert method == "Network.getResponseBody"
        identity = params["requestId"]
        result.calls.append(identity)
        if callback:
            callback(result, identity)
        return {"body": json.dumps({"id": identity}), "base64Encoded": False}

    result.session = SimpleNamespace(send=send)
    return result


def entry(subject, identity, action=None):
    subject.requests[identity] = dict(logical="records", action=action, done=False,
        header_items=[], status=200, spec=ports.RequestSpec("GET", "records"),
        trace_id=None, actual_path="/api/records", fixture_id=None, origin="http://example.com/",
        request_items=[], actual_request_items=[])
    return {"requestId": identity, "encodedDataLength": 20}


def test_body_budget_is_reserved_before_reentrant_protocol_events():
    def reenter(subject, identity):
        if identity == "first":
            for number in range(150):
                subject._finished(entry(subject, str(number)))
    subject = collector(callback=reenter)
    subject._finished(entry(subject, "first"))
    assert subject.calls == ["first"]
    assert subject.background_reads == subject.background_count == 1
    assert subject.body_reads_active == 0
    assert subject.notes == ["background diagnostics truncated"]
    assert subject.context.errors == [] and len(subject.deferred_diagnostics) == 99
    subject._collect_diagnostics()
    assert len(subject.calls) == 9 and subject.background_reads == 9
    assert subject.body_reads_active == 0 and len(subject.deferred_diagnostics) == 91
    while subject.deferred_diagnostics:
        subject._collect_diagnostics()
    assert len(subject.calls) == subject.background_reads == 100
    assert len(set(subject.calls)) == 100 and subject.requests == {}


def test_sequential_optional_body_read_attempts_have_a_context_budget():
    subject = collector()
    for number in range(150):
        subject._finished(entry(subject, str(number)))
    assert len(subject.calls) == subject.background_reads == subject.background_count == 100
    assert subject.background_bytes <= 256 * 1024
    assert subject.notes == ["background diagnostics truncated"]
    assert subject.requests == {}


def test_a_reentrant_completion_does_not_retrieve_one_body_twice():
    def reenter(subject, identity):
        if len(subject.calls) == 1:
            subject._finished({"requestId": identity, "encodedDataLength": 20})
    subject = collector(callback=reenter)
    subject._finished(entry(subject, "one"))
    assert subject.calls == ["one"]
    assert len(subject.context.diagnostics) == 1 and subject.context.errors == []


def test_associated_evidence_is_not_dropped_during_background_body_read():
    def reenter(subject, identity):
        if identity == "background":
            subject._finished(entry(subject, "foreground", action="action"))
    subject = collector(callback=reenter)
    subject.context.permits["action"] = ports.UiActionPermit(
        execution_id="run", action_id="action", step_id="step", mode="live",
        action="click", target="read", value=None, token="token")
    subject._finished(entry(subject, "background"))
    assert subject.calls == ["background", "foreground"]
    assert subject.background_reads == subject.background_count == 1
    assert len(subject.context.traffic) == 1
    assert subject.context.traffic[0].response.json == {"id": "foreground"}
    assert subject.context.traffic[0].step_id == "step"
    assert subject.context.errors == []


def test_mock_diagnostic_receipts_are_complete_and_keep_order_under_reentrancy():
    def reenter(subject, identity):
        if identity == "first":
            subject._finished({"requestId": "second", "encodedDataLength": 20})
    subject = collector(mode="mock", callback=reenter)
    first = entry(subject, "first")
    entry(subject, "second")
    subject.mock_pending[:] = ["first", "second"]
    subject._finished(first)
    assert subject.calls == ["first", "second"]
    assert [record.json for record in subject.context.mock_recordings] == [
        {"id": "first"}, {"id": "second"}]
    assert subject.background_reads == 0 and subject.background_count == 2
    assert subject.notes == [] and subject.context.errors == []


def test_oversized_optional_diagnostic_is_not_retrieved():
    subject = collector()
    event = entry(subject, "large")
    event["encodedDataLength"] = 256 * 1024 + 1
    subject._finished(event)
    assert subject.calls == [] and subject.background_reads == 0
    assert subject.notes == ["background diagnostics truncated"]


@pytest.mark.parametrize("reason", list(Reason))
def test_primary_safe_reason_survives_cleanup_failure(reason):
    support = BrowserSupport("http://example.com/", lambda _: {})
    def failed_close(_):
        raise RuntimeError("private-cleanup-message")
    support.close = failed_close
    with pytest.raises(ActionFailure) as error:
        support._fail(object(), reason)
    assert error.value.reason is reason and error.value.cleanup_failed is True
    assert "private-cleanup-message" not in str(error.value) + repr(error.value)


def test_reason_does_not_inspect_exception_payload_or_custom_name():
    class Untrusted(Exception):
        def __str__(self):
            pytest.fail("untrusted error text evaluated")
        def __repr__(self):
            pytest.fail("untrusted error repr evaluated")
    context = SimpleNamespace(errors=[])
    assert BrowserSupport._reason(context, Untrusted()) is Reason.COLLECTION_FAILED
    context.errors.append("private-ledger-value")
    assert BrowserSupport._reason(context, Untrusted()) is Reason.EVIDENCE_INVALID


@pytest.mark.parametrize("error", [TimeoutError("private-timeout"),
                                  ActionFailure(Reason.COLLECTION_TIMEOUT)])
def test_native_body_read_preserves_safe_timeout_reason(error):
    subject = collector()
    def fail(*_):
        raise error
    subject.session.send = fail
    subject._finished(entry(subject, "one"))
    assert subject.context.errors == [Reason.COLLECTION_TIMEOUT]
    assert subject.background_reads == 1 and subject.body_reads_active == 0
    assert subject.requests == {} and subject.context.diagnostics == []


def test_deferred_optional_reads_respect_the_action_deadline():
    subject = collector()
    event = entry(subject, "one")
    subject.body_reads_active = 1
    subject._finished(event)
    subject.body_reads_active = 0
    def expired(_):
        raise ActionFailure(Reason.COLLECTION_TIMEOUT)
    subject.owner._remaining = expired
    with pytest.raises(ActionFailure) as failure:
        subject._collect_diagnostics()
    assert failure.value.reason is Reason.COLLECTION_TIMEOUT
    assert subject.calls == [] and subject.deferred_diagnostics == ["one"]


def test_request_abort_failure_retains_primary_and_secondary_safe_reasons():
    subject = collector()
    def failed_abort(*_):
        raise RuntimeError("private-abort-message")
    subject.target_guard = SimpleNamespace(send=failed_abort)
    subject._error("request", reason=Reason.POLICY_DENIED)
    assert subject.context.errors == [Reason.POLICY_DENIED, Reason.CLEANUP_FAILED]
    support = BrowserSupport("http://example.com/", lambda _: {})
    support.close = lambda _: None
    with pytest.raises(ActionFailure) as error:
        support._fail(subject.context, support._reason(subject.context, RuntimeError()))
    assert error.value.reason is Reason.POLICY_DENIED
    assert error.value.cleanup_failed is True
    assert "private-abort-message" not in str(error.value) + repr(error.value)


def test_untrusted_cleanup_ledger_text_does_not_create_a_secondary_flag():
    support = BrowserSupport("http://example.com/", lambda _: {})
    support.close = lambda _: None
    context = SimpleNamespace(errors=["cleanup_failed"])
    with pytest.raises(ActionFailure) as error:
        support._fail(context, Reason.EVIDENCE_INVALID)
    assert error.value.cleanup_failed is False
