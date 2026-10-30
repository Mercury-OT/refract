"""Native browser correlation never fabricates transmitted server trace evidence."""
import copy
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from refracto import ports
from refracto.declaration.model import Assertion
from refracto.projection.recording import ProtectedRecorder
from refracto.report import RunReport
from tests.fakes import FakeNormalizer, FakeRecorder
from tests.test_e2e_stepwise import LiveState
from tests.ui_support import ScriptedUi, run, scenario


def _origin(authority, *, scheme="https"):
    return scheme + "://" + authority


ORIGIN = _origin('example.com')


def native(index, result, permit, *, traced=False):
    traffic = []
    for number, old in enumerate(result.evidence.traffic):
        identity = ports.BrowserNetworkIdentity(origin=ORIGIN, request_id=f"network-{index}-{number}")
        request = replace(old.request, traceparent=old.request.traceparent if traced else None)
        response = replace(old.response, request=copy.deepcopy(request),
            trace_id=old.response.trace_id if traced else None,
            request_header_items=[("Traceparent", request.traceparent)] if traced else [],
            header_items=[], browser_identity=copy.deepcopy(identity))
        traffic.append(replace(old, request=request, response=response, browser_identity=identity))
    return ports.UiActionResult(evidence=replace(result.evidence, traffic=traffic,
        mock_recordings=[item.response for item in traffic] if permit.mode == "mock" else []))


class NativeUi(ScriptedUi):
    def __init__(self, count=2, *, mutate=None, traced=False):
        def transform(index, result, permit):
            result = native(index, result, permit, traced=traced)
            return mutate(index, result, permit) if mutate else result
        super().__init__(count, mutate=transform)


def change_pair(result, *, identity=None, response_changes=None, traffic_changes=None):
    item = result.evidence.traffic[0]
    if identity is not None:
        item = replace(item, browser_identity=identity,
                       response=replace(item.response, browser_identity=copy.deepcopy(identity)))
    if response_changes:
        item = replace(item, response=replace(item.response, **response_changes))
    if traffic_changes:
        item = replace(item, **traffic_changes)
    return ports.UiActionResult(evidence=replace(result.evidence, traffic=[item],
        mock_recordings=[item.response] if item.mode == "mock" else []))


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("traced", [False, True])
def test_native_request_pair_works_with_actual_trace_or_without_trace(mode, traced):
    ui = NativeUi(traced=traced)
    domain = run(scenario(), ui, mode=mode)
    assert domain.status == "PASSED"
    assert ui.open_calls == ui.close_calls == 1
    if mode == "live":
        assert len(domain.provider_recordings) == 2
        for index, recording in enumerate(domain.provider_recordings):
            assert recording.browser_identity.request_id == f"network-{index}-0"
            assert recording.browser_identity.origin == ORIGIN
            assert bool(recording.trace_id) is traced
            assert bool(recording.request.traceparent) is traced
            assert recording.browser_identity is not ui.evidence[index].evidence.traffic[0].browser_identity


@pytest.mark.parametrize("origin", [
    _origin('localhost', scheme='http'), _origin('127.0.0.1:1234', scheme='http'), _origin('example.org:444'), _origin('[::1]:1234', scheme='http'),
])
def test_canonical_origins_are_valid(origin):
    def mutate(index, result, permit):
        return change_pair(result, identity=ports.BrowserNetworkIdentity(origin=origin, request_id=f"n{index}"))
    assert run(scenario(), NativeUi(mutate=mutate)).status == "PASSED"


@pytest.mark.parametrize("origin", [
    None, False, 1, "", _origin('EXAMPLE.com'), _origin('example.com', scheme='HTTPS'), _origin('example.com:443'),
    _origin('example.com:80', scheme='http'), _origin('example.com/'), _origin('example.com/path'), _origin('example.com?x=1'),
    _origin('example.com#fragment'), _origin('user:password@' + 'example.com'), _origin('example.com.'),
    _origin('example.com:'), _origin('example.com:0'), _origin('example.com:65536'), _origin('example.com', scheme=' https'),
    _origin('example.com\n'), _origin('exam ple.com'), _origin('example..com'), _origin('/item', scheme='file'), "data:abc",
    _origin('example.com/../'), _origin('example.com%00'), _origin('[::1'), _origin('[0:0:0:0:0:0:0:1]'),
])
def test_noncanonical_or_malformed_origins_fail_without_echoing_values(origin):
    def mutate(index, result, permit):
        return change_pair(result, identity=ports.BrowserNetworkIdentity(origin=origin, request_id="network"))
    result = run(scenario(), NativeUi(mutate=mutate))
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert not result.provider_recordings
    assert "password" not in repr(result)
    assert "password" not in result.steps[0].detail


@pytest.mark.parametrize("network_id", [None, False, True, 0, 1, "", "   ", [], {}])
def test_network_identity_requires_a_nonempty_string(network_id):
    def mutate(index, result, permit):
        return change_pair(result, identity=ports.BrowserNetworkIdentity(origin=ORIGIN, request_id=network_id))
    assert run(scenario(), NativeUi(mutate=mutate)).steps[0].status == "ERROR"


@pytest.mark.parametrize("kind", ["missing-traffic", "missing-response", "dict", "origin", "id", "subclass-field"])
def test_network_identity_pair_must_match_strictly(kind):
    class Text(str):
        pass
    def mutate(index, result, permit):
        if kind == "missing-traffic":
            return change_pair(result, traffic_changes={"browser_identity": None})
        if kind == "missing-response":
            return change_pair(result, response_changes={"browser_identity": None})
        if kind == "dict":
            return change_pair(result, identity={"origin": ORIGIN, "request_id": "network"})
        identity = ports.BrowserNetworkIdentity(
            origin=_origin('example.org') if kind == "origin" else Text(ORIGIN) if kind == "subclass-field" else ORIGIN,
            request_id="other" if kind == "id" else f"network-{index}-0")
        return change_pair(result, response_changes={"browser_identity": identity})
    assert run(scenario(), NativeUi(mutate=mutate)).steps[0].status == "ERROR"


def test_unmarked_traffic_still_requires_a_transmitted_trace():
    def mutate(index, result, permit):
        item = result.evidence.traffic[0]
        request = replace(item.request, traceparent=None)
        return change_pair(result, traffic_changes={"request": request},
                           response_changes={"request": copy.deepcopy(request), "trace_id": None})
    assert run(scenario(), ScriptedUi(mutate=mutate)).steps[0].status == "ERROR"


@pytest.mark.parametrize("case", ["missing-block", "hidden-trace", "wrong-header", "duplicate-header", "wrong-id", "missing-id", "bool-trace"])
def test_native_trace_requires_complete_actual_header_evidence(case):
    def mutate(index, result, permit):
        item = result.evidence.traffic[0]
        if case == "missing-block":
            return change_pair(result, response_changes={"request_header_items": None})
        if case == "hidden-trace":
            return change_pair(result, response_changes={"request_header_items": [("traceparent", "00-wire-parent-01")]})
        changes = {
            "wrong-header": {"request_header_items": [("traceparent", "00-other-parent-01")]},
            "duplicate-header": {"request_header_items": [("traceparent", item.request.traceparent), ("Traceparent", item.request.traceparent)]},
            "wrong-id": {"trace_id": "not-the-trace"},
            "missing-id": {"trace_id": None},
            "bool-trace": {"trace_id": False},
        }
        return change_pair(result, response_changes=changes[case])
    result = run(scenario(), NativeUi(mutate=mutate, traced=case not in {"missing-block", "hidden-trace"}))
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]


@pytest.mark.parametrize("changed_origin", [False, True])
def test_reusing_network_request_in_same_context_is_replay(changed_origin):
    def mutate(index, result, permit):
        return change_pair(result, identity=ports.BrowserNetworkIdentity(
            origin=_origin('example.org') if index and changed_origin else ORIGIN, request_id="same-network"))
    result = run(scenario(), NativeUi(mutate=mutate))
    assert [step.status for step in result.steps] == ["PASSED", "ERROR"]


@pytest.mark.parametrize("new_session", [False, True])
def test_network_request_namespace_is_context_local(new_session):
    s = scenario()
    s.users = ["first"] if new_session else ["first", "second"]
    s.steps[0].user = "first"
    s.steps[1].user = "first" if new_session else "second"
    s.steps[1].session = "new" if new_session else None
    def mutate(index, result, permit):
        return change_pair(result, identity=ports.BrowserNetworkIdentity(origin=ORIGIN, request_id="same-network"))
    ui = NativeUi(mutate=mutate)
    assert run(s, ui).status == "PASSED"
    assert ui.permits[0].context_id != ui.permits[1].context_id


def with_diagnostic(result, network_id, *, remove_primary=False):
    raw = copy.deepcopy(result.evidence.traffic[0].response)
    raw.request_id = "background-" + network_id
    raw.step_id = None
    raw.browser_identity = ports.BrowserNetworkIdentity(origin=ORIGIN, request_id=network_id)
    return ports.UiActionResult(evidence=replace(result.evidence,
        traffic=[] if remove_primary else result.evidence.traffic,
        diagnostic_outgoing=[copy.deepcopy(raw.request)], diagnostic_recorded=[raw]))


@pytest.mark.parametrize("source", ["current", "previous"])
def test_diagnostic_cannot_relabel_an_accepted_network_request(source):
    def mutate(index, result, permit):
        if source == "previous" and not index:
            return result
        return with_diagnostic(result, f"network-{0 if source == 'previous' else index}-0")
    result = run(scenario(), NativeUi(mutate=mutate))
    assert result.steps[0 if source == "current" else 1].status == "ERROR"


def test_previous_background_cannot_be_promoted_into_new_action():
    def mutate(index, result, permit):
        return with_diagnostic(result, "network-1-0") if not index else result
    result = run(scenario(), NativeUi(mutate=mutate))
    assert [step.status for step in result.steps] == ["PASSED", "ERROR"]


def test_matching_background_cannot_replace_missing_primary():
    def mutate(index, result, permit):
        return with_diagnostic(result, f"unassociated-{index}", remove_primary=True)
    result = run(scenario(), NativeUi(mutate=mutate))
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert not result.provider_recordings


@pytest.mark.parametrize("metadata", [None, {}, ports.BrowserNetworkIdentity(origin=ORIGIN + "/", request_id="bad")])
def test_malformed_diagnostic_network_metadata_is_rejected(metadata):
    def mutate(index, result, permit):
        wrapped = with_diagnostic(result, f"background-{index}")
        # An absent identity remains supported for legacy diagnostics; use a
        # malformed origin for the native missing-origin case instead.
        wrapped.evidence.diagnostic_recorded[0].browser_identity = (
            ports.BrowserNetworkIdentity(origin=None, request_id="bad") if metadata is None else metadata)
        return wrapped
    assert run(scenario(), NativeUi(mutate=mutate)).steps[0].status == "ERROR"


@pytest.mark.parametrize("kind", ["origin", "id", "missing", "typed-field"])
def test_recorder_cannot_rewrite_native_origin_or_network_identity(kind):
    class Text(str):
        pass
    class Recorder(FakeRecorder):
        def responses(self):
            items = copy.deepcopy(super().responses())
            if items:
                identity = items[-1].browser_identity
                items[-1].browser_identity = (None if kind == "missing" else ports.BrowserNetworkIdentity(
                    origin=_origin('example.org') if kind == "origin" else identity.origin,
                    request_id="other" if kind == "id" else Text(identity.request_id) if kind == "typed-field" else identity.request_id))
            return items
    assert run(scenario(), NativeUi(), recorder=Recorder()).steps[0].status == "ERROR"


@pytest.mark.parametrize("field", ["origin", "request_id"])
@pytest.mark.parametrize("stage", ["record", "responses"])
def test_shared_protected_recorder_rejects_native_identity_scalar_subclasses(field, stage):
    class Text(str):
        pass
    class Recorder(FakeRecorder):
        mutate = stage == "record"
        def responses(self):
            items = copy.deepcopy(super().responses())
            if self.mutate and items:
                identity = items[-1].browser_identity
                items[-1].browser_identity = replace(identity, **{field: Text(getattr(identity, field))})
            return items
    recorder = Recorder()
    protected = ProtectedRecorder(recorder)
    response = ports.RecordedResponse(200, {}, {"id": 1}, "", None,
        ports.RequestSpec("GET", "/items"), browser_identity=ports.BrowserNetworkIdentity(
            origin=ORIGIN, request_id="network-1"))
    if stage == "record":
        with pytest.raises(ValueError, match="Recorder changed response evidence or order"):
            protected.record(response)
        assert protected.responses() == []
    else:
        protected.record(response)
        retained = protected.responses()[0]
        assert retained.browser_identity == response.browser_identity
        assert retained.browser_identity is not response.browser_identity
        recorder.mutate = True
        with pytest.raises(ValueError, match="Recorder changed response evidence or order"):
            protected.responses()


def test_normalizer_mutation_does_not_change_retained_native_evidence():
    class Normalizer(FakeNormalizer):
        def normalize(self, raw):
            result = super().normalize(raw)
            raw.browser_identity = ports.BrowserNetworkIdentity(origin=_origin('example.org'), request_id="changed")
            return result
    result = run(scenario(), NativeUi(), normalizer=Normalizer())
    assert result.status == "PASSED"
    assert [item.browser_identity.request_id for item in result.provider_recordings] == ["network-0-0", "network-1-0"]


def test_missing_real_trace_cannot_satisfy_declared_span_evidence():
    state = LiveState()
    result = run(scenario(state=True), NativeUi(), state=state)
    assert result.status == "FAILED"
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert state.calls == []
    assert all(step.trace_id is None for step in result.steps)


def test_missing_real_trace_cannot_satisfy_object_observation_identity():
    class Probe(ports.ObjectStateProbe):
        calls = []
        def observe_object(self, query):
            self.calls.append(query)
            raise AssertionError("must not synthesize a server trace")
    s = scenario()
    s.steps[1].expect.backend_state = [Assertion("object_field_equals", {
        "object": "item", "id": "1", "field": "name", "value": "alpha"})]
    # The literal model is already resolved; this checks the runtime boundary.
    probe = Probe()
    result = run(s, NativeUi(), object_state=probe)
    assert [step.status for step in result.steps] == ["PASSED", "ERROR"]
    assert not probe.calls


@pytest.mark.parametrize("initial", [
    ["background diagnostics truncated"],
    ["background HTTP acquisition failed"],
    ["background diagnostics truncated", "background HTTP acquisition failed"],
    ["background HTTP acquisition failed", "background diagnostics truncated"],
])
def test_fixed_diagnostic_notes_are_visible_owned_and_not_a_new_verdict(initial):
    notes = list(initial)
    def mutate(index, result, permit):
        return ports.UiActionResult(evidence=replace(result.evidence, diagnostic_notes=notes))
    result = run(scenario(), NativeUi(mutate=mutate))
    notes.clear()
    assert result.status == "PASSED"
    assert all(step.not_checked == initial for step in result.steps)


def test_truncation_note_cannot_hide_a_required_assertion_failure():
    def mutate(index, result, permit):
        return ports.UiActionResult(evidence=replace(result.evidence,
            rendered={}, diagnostic_notes=["background diagnostics truncated"]))
    result = run(scenario(), NativeUi(mutate=mutate))
    assert [step.status for step in result.steps] == ["FAILED", "FAILED"]
    assert all(step.not_checked == ["background diagnostics truncated"] for step in result.steps)


@pytest.mark.parametrize("notes", [None, "background diagnostics truncated", [False], ["secret-notice"],
                                   ["background diagnostics truncated"] * 2,
                                   ["background HTTP acquisition failed"] * 2,
                                   ["background diagnostics truncated", "background HTTP acquisition failed", "background diagnostics truncated"],
                                   ["background diagnostics truncated", "secret-notice"],
                                   [{"background HTTP acquisition failed": True}]])
def test_arbitrary_diagnostic_notes_cannot_enter_report(notes):
    def mutate(index, result, permit):
        return ports.UiActionResult(evidence=replace(result.evidence, diagnostic_notes=notes))
    result = run(scenario(), NativeUi(mutate=mutate))
    assert result.steps[0].status == "ERROR"
    assert "secret-notice" not in repr(result)
    assert "secret-notice" not in result.steps[0].detail


def test_network_metadata_is_frozen_keyword_only_and_sensitive_in_default_repr():
    identity = ports.BrowserNetworkIdentity(origin=ORIGIN, request_id="network-sensitive-sentinel")
    assert all(item.kw_only and not item.repr and item.metadata["sensitive"] for item in fields(identity))
    with pytest.raises(FrozenInstanceError):
        identity.origin = _origin('example.org')
    with pytest.raises(TypeError):
        ports.BrowserNetworkIdentity(ORIGIN, "n")
    ui = NativeUi()
    result = run(scenario(), ui)
    for value in [identity, *ui.evidence, result, RunReport("native", [result])]:
        assert ORIGIN not in repr(value)
        assert "network-sensitive-sentinel" not in repr(value)
