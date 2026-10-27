"""Complete header evidence from real Chromium and independent HTTP fixtures."""
import copy
import time
from dataclasses import replace

import pytest

from refracto import ports
from refracto.declaration.model import Assertion, Expect, RequestTemplate, Scenario, Step
from refracto.projection import e2e, frontend
from refracto.recorder import InMemoryRecorder
from tests.browser.adapter import SyntheticUi
from tests.browser.test_support import act, browser_lab
from tests.fakes import FakeAuth, FakeNormalizer


SECRET = "synthetic-header-sentinel-641"
KEY = "page-independent-key"


def fixture(identity="header-fixture", *, request_headers=None, response_headers=None):
    return ports.MockResponse(fixture_id=identity, source="independent browser header fixture",
        method="POST", path="api/headers", request_headers=request_headers,
        response_headers=response_headers,
        response={"success": True, "data": {"reply": "fixture response"}})


def page_request(headers=None, path="/api/headers"):
    return {"path": path, "headers": {"X-Operation-Key": KEY} if headers is None else headers}


def set_requests(context, requests):
    context.page.evaluate("requests => { window.lab.headerRequests = requests; }", requests)


class HeaderUi(SyntheticUi):
    def __init__(self, base_url, requests, mutate=None, **kwargs):
        super().__init__(base_url, **kwargs)
        self.requests, self.mutate = requests, mutate

    def perform_step(self, context, authorization, *, business_header_names=()):
        result = super().perform_step(context, authorization, business_header_names=business_header_names)
        if authorization.action == "open":
            set_requests(context, self.requests)
        if self.mutate and result.evidence.traffic:
            result = self.mutate(result)
        return result


def scenario(headers, *, target="headers", response=None, query=None):
    return Scenario("synthetic.headers", None, "editor", [], [], "Observe actual HTTP headers", [
        Step("open", None, Expect(), action="open", target="laboratory"),
        Step("headers", RequestTemplate("POST", "api/headers", {"value": "initial"},
                                        headers=headers, query=query),
             Expect(response=response or [Assertion("success")]), action="click", target=target,
             request_asserted=True),
        Step("after", None, Expect(), action="click", target="noop"),
    ])


def run_headers(http_peer, headers, requests=None, *, mode="live", target="headers", response=None,
                plan=None, mutate=None, normalizer=None, recorder=None, context_options=None, query=None):
    ui = HeaderUi(http_peer.base_url, requests or [page_request()], mutate,
                  context_options=context_options)
    declared = scenario(headers, target=target, response=response, query=query)
    common = dict(ui=ui, auth=FakeAuth(), normalizer=normalizer or FakeNormalizer())
    if mode == "mock":
        result = frontend.run(declared, mock_plan=plan or [fixture()], **common)
    else:
        result = e2e.run(declared, recorder=recorder or InMemoryRecorder(), state=None, **common)
    return result, ui


def values(items, name):
    return [value for key, value in items if key.lower() == name.lower()]


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("target", ["#headers", "#headers-xhr"])
def test_full_browser_headers_include_credentials_and_effective_trace(browser_lab, http_peer, mode, target):
    options = {"extra_http_headers": {"Authorization": "Bearer " + SECRET}}
    supplied = {"x-OPERATION-key": KEY, "X-Empty": ""}
    response_headers = {"X-Reply": "independent reply"}
    http_peer.response_header_items["/api/headers"] = list(response_headers.items())
    support, context = browser_lab(mode=mode, options=options,
        mock_plan=[fixture(request_headers={"X-Operation-Key": KEY}, response_headers=response_headers)]
        if mode == "mock" else None)
    context.browser_context.add_cookies([{"name": "account", "value": SECRET, "url": http_peer.base_url}])
    set_requests(context, [page_request(supplied)])
    browser_responses = []
    context.page.on("response", lambda response: browser_responses.append(
        [(item["name"], item["value"]) for item in response.headers_array()])
        if response.url.endswith("/api/headers") else None)
    evidence = act(support, context, target, mode=mode)
    traffic, = evidence.traffic
    request_items = traffic.response.request_header_items
    assert values(request_items, "x-operation-key") == [KEY]
    assert values(request_items, "x-empty") == [""]
    assert values(request_items, "authorization") == ["Bearer " + SECRET]
    assert values(request_items, "cookie") == ["account=" + SECRET]
    assert values(request_items, "content-type") == ["application/json"]
    assert values(request_items, "traceparent") == [traffic.request.traceparent]
    assert not any(name.lower().startswith("x-refract-") for name, _ in request_items)
    assert traffic.request.headers == traffic.response.request.headers == {}
    assert values(traffic.response.header_items, "x-reply") == ["independent reply"]
    assert values(traffic.response.header_items, "content-length")
    assert len(browser_responses) == 1
    if mode == "live":
        received, = http_peer.api_requests
        for name in ("x-operation-key", "x-empty", "authorization", "cookie", "traceparent", "content-type"):
            assert values(request_items, name) == values(received["header_items"], name)
        assert not any(name.lower().startswith("x-refract-") for name, _ in received["header_items"])
    else:
        assert http_peer.api_requests == []
        assert traffic.response.header_items == browser_responses[0]
        assert values(traffic.response.header_items, "content-length") == [str(len(traffic.response.text.encode()))]
    assert all(SECRET not in repr(item) for item in (traffic.request, traffic.response, evidence, context))


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("target", ["headers", "headers-xhr"])
@pytest.mark.parametrize("actual,expected,passed", [
    ({"x-OPERATION-key": KEY, "X-Extra": "allowed"}, {"X-Operation-Key": KEY}, True),
    ({"X-Operation-Key": "wrong"}, {"X-Operation-Key": KEY}, False),
    ({}, {"X-Operation-Key": KEY}, False),
    ({"X-Operation-Key": KEY.upper()}, {"X-Operation-Key": KEY}, False),
    ({"X-Operation-Key": ""}, {"X-Operation-Key": ""}, True),
])
def test_declared_headers_compare_actual_values_and_failure_continues(http_peer, mode, target, actual, expected, passed):
    result, ui = run_headers(http_peer, expected, [page_request(actual)], mode=mode, target=target)
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED" if passed else "FAILED", "COMPLETED"]
    assert ui.actions == ["open", "click", "click"]
    observed = ui.results[1].evidence.traffic[0].response.request_header_items
    for name, value in actual.items():
        assert values(observed, name) == [value]
    assert len(http_peer.api_requests) == (mode == "live")


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("check,value,actual,status", [
    ("header_equals", "exact", [("X-Reply", "exact")], "PASSED"),
    ("header_equals", "exact", [("x-reply", "EXACT")], "FAILED"),
    ("header_equals", "exact", [], "FAILED"),
    ("header_equals", "", [("x-reply", "")], "PASSED"),
    ("header_absent", None, [], "PASSED"),
    ("header_absent", None, [("x-reply", "")], "FAILED"),
])
def test_response_headers_are_observed_in_live_and_mock(http_peer, mode, check, value, actual, status):
    params = {"header": "X-RePlY"}
    if check == "header_equals":
        params["value"] = value
    http_peer.response_header_items["/api/headers"] = actual
    result, _ = run_headers(http_peer, {"X-Operation-Key": KEY}, mode=mode,
        response=[Assertion(check, params)], plan=[fixture(response_headers=dict(actual))])
    assert [step.status for step in result.steps] == ["COMPLETED", status, "COMPLETED"]


@pytest.mark.parametrize("actual,check,status", [
    ([("X-Reply", "one"), ("x-reply", "two")], "header_equals", "ERROR"),
    ([("X-Reply", "one"), ("x-reply", "one")], "header_equals", "ERROR"),
    ([("X-Reply", "one"), ("x-reply", "two")], "header_absent", "ERROR"),
    ([("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("X-Reply", "one")], "header_equals", "PASSED"),
])
def test_raw_http_response_duplicates_are_not_flattened(http_peer, actual, check, status):
    http_peer.response_header_items["/api/headers"] = actual
    params = {"header": "X-Reply"}
    if check == "header_equals":
        params["value"] = "one"
    result, ui = run_headers(http_peer, None, response=[Assertion(check, params)])
    assert result.steps[1].status == status
    observed = ui.results[1].evidence.traffic[0].response.header_items
    assert [pair for pair in observed if pair[0].lower() in {"x-reply", "set-cookie"}] == actual


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("field,broken", [
    ("request_header_items", None),
    ("request_header_items", [("X-Operation-Key", KEY), ("x-operation-key", KEY)]),
    ("request_header_items", [("X-Operation-Key", 42)]),
    ("header_items", None),
    ("header_items", [("X-Reply", "one"), ("x-reply", "two")]),
    ("header_items", [("X-Reply", None)]),
])
def test_missing_malformed_or_ambiguous_evidence_never_uses_legacy_map(http_peer, mode, field, broken):
    def corrupt(result):
        result = copy.deepcopy(result)
        setattr(result.evidence.traffic[0].response, field, copy.deepcopy(broken))
        result.evidence.traffic[0].response.headers["X-Reply"] = "one"
        return result
    result, _ = run_headers(http_peer, {"X-Operation-Key": KEY}, mode=mode, mutate=corrupt,
        response=[Assertion("header_absent", {"header": "X-Reply"})])
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("keys,expected,status", [
    (["one", "two"], "two", "PASSED"),
    (["one", "two"], "missing", "ERROR"),
    (["two", "two"], "two", "ERROR"),
])
def test_headers_disambiguate_only_associated_method_path_candidates(http_peer, mode, keys, expected, status):
    result, ui = run_headers(http_peer, {"X-Operation-Key": expected},
        [page_request({"X-Operation-Key": key}) for key in keys], mode=mode, target="headers-multi",
        plan=[fixture("first"), fixture("second")])
    assert result.steps[1].status == status
    assert len(ui.results[1].evidence.traffic) == 2
    if mode == "live" and status == "PASSED":
        assert values(result.provider_recordings[0].request_header_items, "x-operation-key") == [expected]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_query_then_headers_select_one_and_unknown_candidate_cannot_be_discarded(http_peer, mode):
    requests = [page_request({"X-Operation-Key": key}, "/api/headers?page=" + page)
                for key, page in [("two", "1"), ("one", "2"), ("two", "2")]]
    plan = [fixture(str(i)) for i in range(3)]
    result, _ = run_headers(http_peer, {"X-Operation-Key": "two"}, requests, mode=mode,
        target="headers-multi", plan=plan, query={"page": "2"})
    assert result.steps[1].status == "PASSED"
    def omit(result):
        result = copy.deepcopy(result)
        result.evidence.traffic[1].response.request_header_items = None
        return result
    broken, _ = run_headers(http_peer, {"X-Operation-Key": "two"}, requests, mode=mode,
        target="headers-multi", plan=plan, query={"page": "2"}, mutate=omit)
    assert broken.steps[1].status == "ERROR"


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_background_headers_cannot_gain_current_action_origin(http_peer, mode):
    result, ui = run_headers(http_peer, {"X-Operation-Key": KEY}, mode=mode, target="headers-timer")
    assert result.steps[1].status == "ERROR"
    assert ui.results[1].evidence.traffic == []


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_custom_credential_header_collision_rejects_before_action(http_peer, mode):
    result, ui = run_headers(http_peer, {"X-Account-Key": SECRET}, mode=mode,
        context_options={"extra_http_headers": {"x-ACCOUNT-key": SECRET}})
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert ui.actions == ["open"]
    assert http_peer.api_requests == []
    assert SECRET not in repr(result)


@pytest.mark.parametrize("constraint,passes", [(None, True), ({}, True),
    ({"X-Operation-Key": KEY}, True), ({"X-Operation-Key": "wrong"}, False)])
def test_mock_request_fixture_is_an_independent_subset(browser_lab, http_peer, constraint, passes):
    support, context = browser_lab(mode="mock", mock_plan=[fixture(request_headers=constraint)])
    set_requests(context, [page_request({"X-Operation-Key": KEY, "X-Extra": "allowed"})])
    if passes:
        outcome = act(support, context, "#headers", mode="mock")
        assert values(outcome.traffic[0].response.request_header_items, "x-extra") == ["allowed"]
        assert context.mock_queue.index == 1
    else:
        with pytest.raises(RuntimeError):
            act(support, context, "#headers", mode="mock")
        assert context.mock_queue.index == 0
    assert http_peer.api_requests == []


def test_mock_response_header_tampering_cannot_match_the_fixture(http_peer):
    def corrupt(result):
        result = copy.deepcopy(result)
        result.evidence.traffic[0].response.header_items = [("X-Reply", "forged")]
        return result
    result, _ = run_headers(http_peer, None, mode="mock", mutate=corrupt,
        plan=[fixture(response_headers={"X-Reply": "independent"})])
    assert result.steps[1].status == "ERROR"


def test_normalizer_cannot_repair_response_headers(http_peer):
    class RewritingNormalizer(FakeNormalizer):
        def normalize(self, response):
            normalized = super().normalize(response)
            normalized.raw.header_items = [("X-Reply", SECRET)]
            return normalized
    result, _ = run_headers(http_peer, None, normalizer=RewritingNormalizer(),
        response=[Assertion("header_equals", {"header": "X-Reply", "value": SECRET})])
    assert result.steps[1].status == "ERROR"
    assert SECRET not in repr(result)


@pytest.mark.parametrize("field", ["request_header_items", "header_items"])
def test_recorder_cannot_rewrite_header_observations(http_peer, field):
    class RewritingRecorder(InMemoryRecorder):
        def record(self, response):
            setattr(response, field, [("X-Operation-Key", SECRET)])
            super().record(response)
    result, _ = run_headers(http_peer, {"X-Operation-Key": KEY}, recorder=RewritingRecorder())
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert SECRET not in repr(result)


def test_replayed_header_evidence_is_not_new_traffic(http_peer):
    held = []
    def replay(result):
        if not held:
            held.append(result)
        return held[0]
    ui = HeaderUi(http_peer.base_url, [page_request()], replay)
    declared = scenario({"X-Operation-Key": KEY})
    declared.steps[2] = replace(declared.steps[1], id="replay")
    result = e2e.run(declared, ui=ui, auth=FakeAuth(), normalizer=FakeNormalizer(),
                     state=None, recorder=InMemoryRecorder())
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "ERROR"]


def test_anonymous_context_has_complete_credential_free_request(browser_lab):
    support, context = browser_lab()
    set_requests(context, [page_request()])
    outcome = act(support, context, "#headers")
    observed = outcome.traffic[0].response.request_header_items
    assert values(observed, "authorization") == values(observed, "cookie") == []


def test_mock_header_collection_freezes_boundary_and_retains_later_arrivals(browser_lab, monkeypatch, http_peer):
    plan = [fixture(name, response_headers={"X-Reply": name})
            for name in ("background", "later", "current")]
    support, context = browser_lab(mode="mock", mock_plan=plan)
    set_requests(context, [page_request()])
    observe = support._capture_mock_headers
    delayed = []

    def delay_background_event(ctx, response):
        recording = ctx.pending_mock_responses.get(response.request)
        if recording is not None and recording.mock_fixture_id in {"background", "later"}:
            delayed.append((ctx, response))
        else:
            observe(ctx, response)

    monkeypatch.setattr(support, "_capture_mock_headers", delay_background_event)
    settle = support._settle

    def settle_after_background_started(ctx, action_id):
        settle(ctx, action_id)
        # Make the original race deterministic: the timer request has fulfilled,
        # but its actual response event has not reached the helper's collector.
        ctx.page.wait_for_function("() => window.lab.results.length >= 1")

    monkeypatch.setattr(support, "_settle", settle_after_background_started)
    wait = context.page.wait_for_timeout
    drains = []

    def deliver_frozen_event(milliseconds):
        wait(milliseconds)
        if not drains:
            assert len(delayed) == 1
            # A later, unassociated request arrives while the frozen first block
            # is being collected. Its event stays delayed until the next action.
            context.page.evaluate("() => sendHeaders(window.lab.headerRequests[0])")
            context.page.wait_for_function("() => window.lab.results.length >= 2")
            assert len(delayed) == 2
        observe(*delayed[len(drains)])
        drains.append(True)

    monkeypatch.setattr(context.page, "wait_for_timeout", deliver_frozen_event)
    first = act(support, context, "#headers-timer", mode="mock")
    assert first.traffic == []
    assert [record.mock_fixture_id for record in first.mock_recordings] == ["background"]
    assert [record.mock_fixture_id for record in first.diagnostic_recorded] == ["background"]
    assert first.diagnostic_recorded[0].step_id is None
    assert values(first.mock_recordings[0].header_items, "x-reply") == ["background"]
    assert values(first.mock_recordings[0].header_items, "content-length")
    assert context.mock_queue.index == 2 and len(drains) == 1
    assert context.mock_cursor == context.diagnostic_cursor == 1
    assert context.traffic_cursor == 0
    assert context.mock_recordings[1].header_items is None
    second = act(support, context, "#headers", mode="mock")
    assert [traffic.mock_fixture_id for traffic in second.traffic] == ["current"]
    assert [record.mock_fixture_id for record in second.diagnostic_recorded] == ["later"]
    assert second.diagnostic_recorded[0].step_id is None
    assert [record.mock_fixture_id for record in second.mock_recordings] == ["later", "current"]
    for record in first.mock_recordings + second.mock_recordings:
        assert values(record.header_items, "x-reply") == [record.mock_fixture_id]
        assert values(record.header_items, "content-length")
    assert len(drains) == 2 and context.mock_queue.index == 3
    assert context.mock_cursor == 3 and context.diagnostic_cursor == 2
    assert context.traffic_cursor == 1
    assert [record.mock_fixture_id for record in first.mock_recordings + second.mock_recordings] == [
        "background", "later", "current"]
    assert context.pending_mock_responses == context.mock_response_events == {}
    assert http_peer.api_requests == []


@pytest.mark.parametrize("failure", ["missing_event", "headers_read"])
def test_incomplete_mock_header_capture_fails_within_existing_deadline(browser_lab, monkeypatch, failure):
    support, context = browser_lab(mode="mock", mock_plan=[fixture()], timeout_ms=5000)
    set_requests(context, [page_request()])
    observe = support._capture_mock_headers

    def failed_read():
        raise RuntimeError(SECRET)

    def incomplete_event(ctx, response):
        if failure == "headers_read":
            monkeypatch.setattr(response, "headers_array", failed_read)
            observe(ctx, response)

    monkeypatch.setattr(support, "_capture_mock_headers", incomplete_event)
    collect = support._collect_mock_headers
    started = []

    def collect_at_budget_boundary(ctx, recordings):
        assert len(recordings) == 1 and recordings[0].header_items is None
        started.append(time.monotonic())
        # Simulate a mostly spent action budget after the request has actually
        # fulfilled; a slow CI click cannot invalidate this collection control.
        ctx.deadline = min(ctx.deadline, started[0] + 0.05)
        collect(ctx, recordings)

    monkeypatch.setattr(support, "_collect_mock_headers", collect_at_budget_boundary)
    with pytest.raises(RuntimeError, match="browser action or evidence collection failed") as error:
        act(support, context, "#headers", mode="mock")
    assert len(started) == 1 and time.monotonic() - started[0] < 2
    assert context.closed and context.page.is_closed()
    assert context.mock_recordings[0].header_items is None
    assert SECRET not in str(error.value)
