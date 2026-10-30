"""Behavioral acceptance against real Chromium and real local HTTP servers.

The fixture page supplies its own responses and activity. Assertions inspect
external requests, DOM effects and the unchanged public port shapes.
"""
import json
import time
from urllib.parse import quote
from uuid import uuid4

import pytest

from refracto import ports
from refracto.declaration.model import Assertion, Expect, RequestTemplate, Scenario, Step
from refracto.projection import e2e, frontend
from refracto.recorder import InMemoryRecorder
from refracto.report import RunReport
from refracto_browser import BrowserSupport
from tests.browser.adapter import SyntheticUi, fields, read_rendered
from tests.fakes import FakeAuth, FakeNormalizer


def permit(action="click", *, run="synthetic-run", mode="live", value=None):
    identity = uuid4().hex
    return ports.UiActionPermit(execution_id=run, action_id=identity,
        step_id="step-" + identity, mode=mode, action=action, target="synthetic",
        value=value, token=uuid4().hex)


@pytest.fixture
def browser_lab(http_peer):
    opened = []

    def create(*, timeout_ms=5000, mode="live", mock_plan=None,
               read=read_rendered, logical_path=None, options=None, path="/", base_url=None):
        base_url = base_url or http_peer.base_url
        support = BrowserSupport(base_url, read, logical_path=logical_path,
                                 timeout_ms=timeout_ms)
        context = support.open(mode, mock_plan=mock_plan, context_options=options)
        opened.append((support, context))
        support.perform(context, permit("open", mode=mode), url=base_url + path)
        return support, context

    yield create
    for support, context in opened:
        support.close(context)


def act(support, context, target, *, mode="live", action="click", value=None):
    return support.perform(context, permit(action, mode=mode, value=value), selector=target).evidence


def test_context_creation_is_blank_and_snapshot_has_no_implicit_activity(http_peer):
    support = BrowserSupport(http_peer.base_url, read_rendered)
    context = support.open("live")
    try:
        assert fields(support.snapshot(context))["url"] == "about:blank"
        assert http_peer.requests == []
        assert "playwright" not in repr(context).lower()
        assert "browser_context=" not in repr(context) and "page=" not in repr(context)
    finally:
        support.close(context)
    support.close(context)
    with pytest.raises(Exception):
        support.snapshot(context)
    with pytest.raises(Exception):
        act(support, context, "#fetch")


@pytest.mark.parametrize("target,path,status", [
    ("#fetch", "/api/echo", 200), ("#xhr", "/api/xhr", 201),
    ("#delayed", "/api/delayed", 200), ("#promise", "/api/promise", 200),
    ("#property", "/api/property", 200), ("#inline", "/api/inline", 200),
])
def test_actual_fetch_xhr_delayed_body_and_registered_promise(browser_lab, http_peer, target, path, status):
    support, context = browser_lab()
    act(support, context, "#value", action="fill", value="distinct request payload")
    evidence = act(support, context, target)
    assert len(evidence.traffic) == 1
    traffic = evidence.traffic[0]
    assert traffic.request.method == "POST"
    assert traffic.request.path == path.removeprefix("/")
    assert traffic.request.body == {"value": "distinct request payload"}
    assert traffic.response.request == traffic.request
    assert traffic.response.status == status
    assert traffic.response.json == json.loads(traffic.response.text)
    assert traffic.response.json["data"]["body"] == traffic.request.body
    assert traffic.response.actual_path == path
    assert traffic.response.request_id == traffic.request_id
    assert traffic.response.step_id == traffic.step_id == evidence.step_id
    assert traffic.response.trace_id == traffic.request.traceparent.split("-")[1]
    assert traffic.request.traceparent in http_peer.api_requests[-1]["headers"].values()
    assert len(http_peer.api_requests) == 1  # No independent API replay may repair evidence.
    assert path in http_peer.completed
    assert fields(evidence.rendered)["clicks"] == 1
    assert fields(evidence.rendered)["inputs"] == 1
    assert evidence.mock_recordings == []


def test_multiple_requests_and_repeated_endpoint_keep_distinct_actual_pairs(browser_lab, http_peer):
    support, context = browser_lab()
    multi = act(support, context, "#multi")
    assert {t.request.path for t in multi.traffic} == {"api/first", "api/second"}
    first = act(support, context, "#fetch")
    act(support, context, "#value", action="fill", value="second call")
    second = act(support, context, "#fetch")
    all_traffic = multi.traffic + first.traffic + second.traffic
    assert len({t.request_id for t in all_traffic}) == 4
    assert len({t.response.trace_id for t in all_traffic}) == 4
    assert first.traffic[0].response.json["data"]["reply"] == "initial"
    assert second.traffic[0].response.json["data"]["reply"] == "second call"
    assert all(t.response.request == t.request for t in all_traffic)
    assert len(http_peer.api_requests) == 4


@pytest.mark.parametrize("target,body", [("#timer", "timer"), ("#await", "await")])
def test_untracked_identical_endpoint_never_gains_action_origin(browser_lab, target, body):
    support, context = browser_lab()
    first = act(support, context, target)
    # A supported delayed request gives the independent timer time to finish.
    second = act(support, context, "#delayed")
    assert first.traffic == []
    assert [t.request.path for t in second.traffic] == ["api/delayed"]
    recorded = first.diagnostic_recorded + second.diagnostic_recorded
    assert any(r.request.path == "api/echo" and r.request.body == {"value": body}
               for r in recorded)
    assert all(r.step_id is None for r in recorded)
    current = act(support, context, "#fetch")
    assert [t.request.body for t in current.traffic] == [{"value": "initial"}]


def test_delayed_previous_unassigned_response_stays_out_of_current_evidence(browser_lab):
    support, context = browser_lab()
    previous = act(support, context, "#stale")
    current = act(support, context, "#delayed")
    # Collect a completed diagnostic even if it finishes just after the current action.
    last = act(support, context, "#delayed")
    assert previous.traffic == []
    assert all(t.request.path == "api/delayed" for t in current.traffic + last.traffic)
    diagnostics = previous.diagnostic_recorded + current.diagnostic_recorded + last.diagnostic_recorded
    stale = [r for r in diagnostics if r.request.path == "api/stale"]
    assert len(stale) == 1
    assert stale[0].request.body == {"value": "previous"}
    assert stale[0].step_id is None
    assert stale[0].request_id not in {t.request_id for t in current.traffic + last.traffic}


def test_continuous_background_traffic_does_not_hold_action_open(browser_lab, http_peer):
    support, context = browser_lab(timeout_ms=1200)
    start = act(support, context, "#background")
    before = time.monotonic()
    evidence = act(support, context, "#delayed")
    elapsed = time.monotonic() - before
    assert elapsed < 1.2
    assert [t.request.path for t in evidence.traffic] == ["api/delayed"]
    assert any(r["path"] == "/api/background" for r in http_peer.api_requests)
    assert any(r.request.path == "api/background"
               for r in start.diagnostic_recorded + evidence.diagnostic_recorded)


def test_unfinished_unassociated_body_does_not_block_completed_action(browser_lab, http_peer):
    support, context = browser_lab(timeout_ms=700)
    first = act(support, context, "#background-hang")
    before = time.monotonic()
    current = act(support, context, "#delayed")
    assert time.monotonic() - before < 0.7
    assert first.traffic == []
    assert [t.request.path for t in current.traffic] == ["api/delayed"]
    assert current.traffic[0].response.json["data"]["reply"] == "initial"
    assert any(r["path"] == "/api/hang" for r in http_peer.api_requests)
    assert "/api/hang" not in http_peer.completed


def test_removed_listener_has_no_effect_and_next_action_still_works(browser_lab, http_peer):
    support, context = browser_lab()
    removed = act(support, context, "#removed")
    assert removed.traffic == []
    next_action = act(support, context, "#fetch")
    assert len(next_action.traffic) == 1
    assert not any(r["path"] == "/api/removed" for r in http_peer.api_requests)
    assert fields(next_action.rendered)["clicks"] == 2


def test_property_handler_identity_and_false_return_preserve_dom_behavior(browser_lab, http_peer):
    support, context = browser_lab()
    evidence = act(support, context, "#cancel")
    assert fields(evidence.rendered)["propertyIdentity"] is True
    assert fields(evidence.rendered)["url"] == http_peer.base_url + "/"
    assert fields(evidence.rendered)["clicks"] == 1
    assert not any(r["path"] == "/unexpected-navigation" for r in http_peer.requests)


def test_thrown_handler_failure_closes_context_and_does_not_poison_next_run(browser_lab):
    pages = []
    def remember(page):
        pages.append(page)
        return read_rendered(page)
    support, context = browser_lab(read=remember)
    with pytest.raises(Exception):
        act(support, context, "#throw")
    assert pages[-1].is_closed()
    next_support, next_context = browser_lab()
    evidence = act(next_support, next_context, "#fetch")
    assert [t.request.body for t in evidence.traffic] == [{"value": "initial"}]


def test_passive_target_readiness_performs_exactly_one_action(browser_lab, http_peer):
    support, context = browser_lab()
    evidence = act(support, context, "#late")
    assert fields(evidence.rendered)["clicks"] == 1
    assert fields(evidence.rendered)["inputs"] == 0
    assert http_peer.api_requests == []


@pytest.mark.parametrize("selector", ["#missing", "#hidden", ".duplicate"])
def test_absent_hidden_and_ambiguous_targets_fail_without_action(browser_lab, http_peer, selector):
    observed = []
    def remember(page):
        observed.append(page)
        return read_rendered(page)
    support, context = browser_lab(timeout_ms=350, read=remember)
    page = observed[-1]
    clicks = []
    page.expose_function("observeClick", lambda: clicks.append(True))
    page.evaluate("document.addEventListener('click', () => window.observeClick())")
    with pytest.raises(Exception):
        act(support, context, selector)
    assert clicks == []
    assert http_peer.api_requests == []


def test_permits_are_one_use_and_cannot_mix_contexts_or_runs(browser_lab):
    support, context = browser_lab()
    authorization = permit()
    support.perform(context, authorization, selector="#noop")
    with pytest.raises(Exception):
        support.perform(context, authorization, selector="#noop")
    assert fields(support.snapshot(context))["clicks"] == 1
    other_support, other_context = browser_lab()
    with pytest.raises(Exception):
        support.perform(other_context, permit(), selector="#noop")
    with pytest.raises(Exception):
        other_support.perform(other_context, permit(run="different-run"), selector="#noop")
    fresh = support.open("live")
    try:
        with pytest.raises(Exception):
            support.perform(fresh, authorization, selector="#noop")
    finally:
        support.close(fresh)


def test_closing_one_owned_browser_does_not_terminate_another_helper(browser_lab, http_peer):
    support, context = browser_lab()
    other_support, other_context = browser_lab()
    support.close(context)
    evidence = act(other_support, other_context, "#fetch")
    assert len(evidence.traffic) == 1
    assert len(http_peer.api_requests) == 1


def test_product_logical_mapping_preserves_actual_transport_path(browser_lab, http_peer):
    support, context = browser_lab(logical_path=lambda path: "records" if path == "/api/echo" else path)
    evidence = act(support, context, "#fetch")
    assert evidence.traffic[0].request.path == "records"
    assert evidence.traffic[0].response.actual_path == "/api/echo"
    assert http_peer.api_requests[0]["path"] == "/api/echo"


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True, "100"])
def test_timeout_must_be_positive_and_finite(http_peer, timeout):
    with pytest.raises((TypeError, ValueError)):
        BrowserSupport(http_peer.base_url, read_rendered, timeout_ms=timeout)


@pytest.mark.parametrize("mode", ["", "record", "LIVE", None])
def test_unknown_modes_are_rejected_before_browser_activity(http_peer, mode):
    support = BrowserSupport(http_peer.base_url, read_rendered)
    with pytest.raises((TypeError, ValueError)):
        support.open(mode)
    assert http_peer.requests == []


def test_live_mock_plan_and_cross_mode_permit_are_incompatible(browser_lab, http_peer):
    support, context = browser_lab()
    with pytest.raises(Exception):
        support.open("live", mock_plan=[])
    with pytest.raises(Exception):
        support.perform(context, permit(mode="mock"), selector="#fetch")
    assert fields(support.snapshot(context))["clicks"] == 0
    assert http_peer.api_requests == []


@pytest.mark.parametrize("options", [
    dict(action="open", url="relative"),
    dict(action="open", selector="#noop"),
    dict(action="click", url="http://127.0.0.1/"),
    dict(action="fill", selector="#value", value=42),
    dict(action="click", selector="#noop", value="not-used"),
])
def test_incompatible_primitive_arguments_fail_before_activity(browser_lab, http_peer, options):
    support, context = browser_lab()
    kwargs = {k: v for k, v in options.items() if k in {"url", "selector"}}
    with pytest.raises(Exception):
        support.perform(context, permit(options["action"], value=options.get("value")), **kwargs)
    assert http_peer.api_requests == []


@pytest.mark.parametrize("target", ["#abort", "#hang", "#sync-xhr"])
def test_failed_or_unsupported_transports_fail_visibly_and_close(browser_lab, target):
    pages = []
    def remember(page):
        pages.append(page)
        return read_rendered(page)
    support, context = browser_lab(timeout_ms=450, read=remember)
    before = time.monotonic()
    with pytest.raises(Exception):
        act(support, context, target)
    assert time.monotonic() - before < 2
    assert pages[-1].is_closed()
    support.close(context)


@pytest.mark.parametrize("failure", ["render", "mapper"])
def test_product_callback_failures_are_sanitized_and_release_resources(browser_lab, failure):
    secret = "synthetic-secret-callback-value"
    pages = []
    failing = False
    def read(page):
        pages.append(page)
        if failing and failure == "render":
            raise ValueError(secret)
        return read_rendered(page)
    def logical_path(path):
        if failing and failure == "mapper":
            raise ValueError(secret)
        return path.removeprefix("/")
    support, context = browser_lab(read=read, logical_path=logical_path)
    failing = True
    with pytest.raises(Exception) as error:
        act(support, context, "#fetch")
    assert secret not in str(error.value)
    assert pages[-1].is_closed()


def fixture(identity, path="api/echo", *, reply=None, method="POST"):
    return ports.MockResponse(fixture_id=identity, source="public synthetic fixture",
        method=method, path=path, response={"success": True, "data": {"reply": reply or identity}})


def test_mock_repeated_endpoints_consume_ordered_fixtures_without_backend(browser_lab, http_peer):
    support, context = browser_lab(mode="mock", mock_plan=[fixture("one"), fixture("two")])
    first = act(support, context, "#fetch", mode="mock")
    second = act(support, context, "#fetch", mode="mock")
    for evidence, identity in [(first, "one"), (second, "two")]:
        assert evidence.traffic[0].response.json["data"]["reply"] == identity
        assert evidence.traffic[0].mock_fixture_id == identity
        assert [r.mock_fixture_id for r in evidence.mock_recordings] == [identity]
        assert evidence.mode == "mock"
    assert http_peer.api_requests == []


@pytest.mark.parametrize("plan", [[], [fixture("wrong", "api/other"), fixture("matching-later")],
                                  [fixture("method", method="GET")]])
def test_mock_missing_mismatched_and_wrong_order_requests_never_fall_through(browser_lab, http_peer, plan):
    support, context = browser_lab(mode="mock", mock_plan=plan)
    with pytest.raises(Exception):
        act(support, context, "#fetch", mode="mock")
    assert http_peer.api_requests == []


def test_mock_background_consumes_fixture_but_remains_diagnostic(browser_lab, http_peer):
    plan = [fixture("background"), fixture("foreground", "api/delayed")]
    support, context = browser_lab(mode="mock", mock_plan=plan)
    first = act(support, context, "#timer", mode="mock")
    # Wait through the browser event loop so the timer's explicit fixture is first.
    time.sleep(0.08)
    support.snapshot(context)
    current = act(support, context, "#delayed", mode="mock")
    records = first.mock_recordings + current.mock_recordings
    assert [r.mock_fixture_id for r in records] == ["background", "foreground"]
    assert first.traffic == []
    assert [t.mock_fixture_id for t in current.traffic] == ["foreground"]
    assert http_peer.api_requests == []


def synthetic_scenario(target="fetch"):
    steps = [Step("open", None, Expect(), action="open", target="laboratory"),
             Step("first", RequestTemplate("POST", "api/echo"),
                  Expect(response=[Assertion("success")]), action="click", target=target,
                  request_asserted=True),
             Step("second", RequestTemplate("POST", "api/echo"),
                  Expect(response=[Assertion("success")]), action="click", target="fetch",
                  request_asserted=True)]
    return Scenario("synthetic.browser", None, "editor", [], [], "Exercise public browser primitives", steps)


def run_live(scenario, ui):
    return e2e.run(scenario, auth=FakeAuth(), ui=ui, state=None,
                   recorder=InMemoryRecorder(), normalizer=FakeNormalizer())


@pytest.mark.parametrize("target", ["abort", "hang", "missing", "timer", "await"])
def test_existing_core_errors_and_blocks_without_performing_later_action(http_peer, target):
    ui = SyntheticUi(http_peer.base_url, timeout_ms=450)
    domain = run_live(synthetic_scenario(target), ui)
    assert [step.status for step in domain.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert ui.actions == ["open", "click"]
    assert ui.close_calls == 1
    assert not any(r["path"] == "/api/echo" and r["body"] == {"value": "initial"}
                   for r in http_peer.api_requests)


def test_synthetic_adapter_passes_existing_core_live_and_mock_ports(http_peer):
    live_ui = SyntheticUi(http_peer.base_url)
    live = run_live(synthetic_scenario(), live_ui)
    assert live.status == "PASSED", [(s.status, s.detail) for s in live.steps]
    assert RunReport("synthetic", [live]).degradations() == []
    assert len(live.provider_recordings) == 2
    assert len(http_peer.api_requests) == 2
    mock_ui = SyntheticUi(http_peer.base_url)
    mock = frontend.run(synthetic_scenario(), ui=mock_ui, auth=FakeAuth(), normalizer=FakeNormalizer(),
                        mock_plan=[fixture("first"), fixture("second")])
    assert mock.status == "PASSED", [(s.status, s.detail) for s in mock.steps]
    assert [item["fixture_id"] for item in mock.mock_consumption] == ["first", "second"]
    assert mock.provider_recordings == []
    assert len(http_peer.api_requests) == 2
    assert live_ui.close_calls == mock_ui.close_calls == 1


def test_secret_values_and_internal_markers_do_not_leak(browser_lab, http_peer):
    secret = "synthetic-secret-sentinel-49a"
    support, context = browser_lab(options={"extra_http_headers": {"Authorization": "Bearer " + secret}})
    fill = permit("fill", value=secret)
    support.perform(context, fill, selector="#value")
    result = support.perform(context, permit(), selector="#fetch")
    for obj in [support, context, fill, result, result.evidence, *result.evidence.traffic]:
        assert secret not in repr(obj)
    sent = http_peer.api_requests[-1]
    assert sent["body"] == {"value": secret}
    assert "?" not in sent["url"]
    assert not any("refract" in name.lower() or "origin-token" in name.lower() for name in sent["headers"])
    assert sent["headers"]["Authorization"] == "Bearer " + secret
    with pytest.raises(Exception) as error:
        act(support, context, "[" + secret)
    assert secret not in str(error.value)


def test_secret_query_rejected_without_error_or_report_leak(http_peer, foreign_peer):
    secret = "synthetic-query-secret-812"
    support = BrowserSupport(http_peer.base_url, read_rendered)
    context = support.open("live")
    try:
        with pytest.raises(Exception) as error:
            support.perform(context, permit("open"), url=foreign_peer.base_url + "/?token=" + secret)
        assert secret not in str(error.value)
        assert foreign_peer.requests == []
    finally:
        support.close(context)
    ui = SyntheticUi(http_peer.base_url)
    scenario = synthetic_scenario()
    scenario.steps.insert(1, Step("fill", None, Expect(), action="fill", target="value", value=secret))
    report = RunReport(scenario.id, [run_live(scenario, ui)])
    assert report.status == "PASSED"
    assert secret not in repr(report)


@pytest.mark.parametrize("target", ["#cross", "#redirect"])
def test_cross_origin_and_redirects_never_forward_secret_headers(browser_lab, http_peer, foreign_peer, target):
    secret = "synthetic-header-secret-770"
    http_peer.redirect_to = foreign_peer.base_url + "/api/received"
    support, context = browser_lab(options={"extra_http_headers": {"Authorization": secret}},
        path="/?foreign=" + quote(foreign_peer.base_url + "/api/received", safe=""))
    with pytest.raises(Exception) as error:
        act(support, context, target)
    assert secret not in str(error.value)
    assert foreign_peer.requests == []


@pytest.mark.parametrize("target", ["#websocket", "#eventsource", "#worker"])
def test_unsupported_cross_origin_transports_fail_before_sending_credentials(browser_lab, foreign_peer, target):
    secret = "synthetic-unsupported-transport-secret-219"
    support, context = browser_lab(options={"extra_http_headers": {"Authorization": secret}},
        path="/?foreign=" + quote(foreign_peer.base_url + "/api/received", safe=""))
    with pytest.raises(Exception) as error:
        act(support, context, target)
    assert secret not in str(error.value)
    assert foreign_peer.requests == []


@pytest.mark.parametrize("flag", ["0", "null"])
def test_synchronous_xhr_boolean_coercions_still_fail_without_sending(browser_lab, http_peer, flag):
    support, context = browser_lab(path="/?asyncFlag=" + flag)
    with pytest.raises(Exception):
        act(support, context, "#sync-xhr")
    assert http_peer.api_requests == []
