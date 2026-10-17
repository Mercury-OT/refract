"""Real Chromium query evidence, independent fixtures, and rejection controls."""
import copy
from dataclasses import replace
from urllib.parse import urlsplit

import pytest

from refracto import ports
from refracto.declaration.model import Assertion, Expect, RequestTemplate, Scenario, Step
from refracto.projection import e2e, frontend
from refracto.recorder import InMemoryRecorder
from refracto.report import RunReport
from tests.browser.adapter import SyntheticUi
from tests.browser.test_support import act, browser_lab, permit
from tests.fakes import FakeAuth, FakeNormalizer


def query_fixture(identity="query", query=None):
    return ports.MockResponse(fixture_id=identity, source="independent query fixture",
        method="POST", path="api/query", query=query,
        response={"success": True, "data": {"reply": "fixture response"}})


def set_paths(context, paths):
    context.page.evaluate("paths => { window.lab.queryPaths = paths; }", paths)


class QueryUi(SyntheticUi):
    """Fixture transport inputs belong to the page, never to expectations."""
    def __init__(self, base_url, paths, mutate=None):
        super().__init__(base_url)
        self.paths, self.mutate = paths, mutate

    def perform_step(self, scenario, step, context, permit):
        result = super().perform_step(scenario, step, context, permit)
        if step.action == "open":
            set_paths(context, self.paths)
        if self.mutate and result.evidence.traffic:
            result = self.mutate(result)
        return result


def query_scenario(query, target="query"):
    return Scenario("synthetic.query", None, "editor", [], [], "Observe actual queries", [
        Step("open", None, Expect(), action="open", target="laboratory"),
        Step("query", RequestTemplate("POST", "api/query", {"value": "initial"}, query=query),
             Expect(response=[Assertion("success")]), action="click", target=target,
             request_asserted=True),
        Step("after", None, Expect(), action="click", target="noop"),
    ])


def run_query(http_peer, query, paths, *, mode="live", target="query", plan=None,
              mutate=None, recorder=None, normalizer=None):
    ui = QueryUi(http_peer.base_url, paths, mutate)
    scenario = query_scenario(query, target)
    common = dict(ui=ui, auth=FakeAuth(), normalizer=normalizer or FakeNormalizer())
    if mode == "mock":
        result = frontend.run(scenario, mock_plan=plan or [query_fixture()], **common)
    else:
        result = e2e.run(scenario, state=None, recorder=recorder or InMemoryRecorder(), **common)
    return result, ui


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("target", ["#query", "#query-xhr"])
def test_actual_url_decodes_once_and_mapper_only_receives_path(browser_lab, http_peer, mode, target):
    expected = {"caf\u00e9": "\u96ea space+&=%/", "blank": "", "bare": "", "zero": "0", "false": "false"}
    raw = "false=false&zero=0&bare&blank=&caf%C3%A9=%E9%9B%AA+space%2B%26%3D%25%2F"
    mapped = []
    def logical_path(path):
        mapped.append(path)
        return path.removeprefix("/")
    support, context = browser_lab(mode=mode,
        mock_plan=[query_fixture(query=expected)] if mode == "mock" else None,
        logical_path=logical_path)
    set_paths(context, ["/api/query?" + raw])
    evidence = act(support, context, target, mode=mode)
    traffic, = evidence.traffic
    assert traffic.request.query == expected
    assert traffic.response.request.query == expected
    assert traffic.request.query is not traffic.response.request.query
    assert traffic.request.path == "api/query" and traffic.response.actual_path == "/api/query"
    assert mapped == ["/api/query"]
    if mode == "live":
        assert len(http_peer.api_requests) == 1
        assert urlsplit(http_peer.api_requests[0]["url"]).query == raw
    else:
        assert http_peer.api_requests == []
        assert evidence.mock_recordings[0].request.query == expected


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("declared,path,passed", [
    ({"category": "guide", "limit": 1, "cursor": 0}, "/api/query?cursor=0&limit=1&category=guide", True),
    ({"category": "guide"}, "/api/query?category=other", False),
    ({"category": "guide"}, "/api/query", False),
    ({"category": "guide"}, "/api/query?category=guide&extra=1", False),
    ({}, "/api/query?category=guide", False),
    ({}, "/api/query", True),
    (None, "/api/query?anything=accepted", True),
    ({"empty": "", "enabled": False, "count": 0}, "/api/query?empty=&enabled=false&count=0", True),
])
def test_declared_query_checks_actual_traffic_and_ordinary_failure_continues(http_peer, mode, declared, path, passed):
    result, ui = run_query(http_peer, declared, [path], mode=mode)
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED" if passed else "FAILED", "COMPLETED"]
    assert [(c.check, c.ok) for c in result.steps[1].checks] == [("request", passed), ("success", True)]
    assert ui.actions == ["open", "click", "click"]
    assert len(ui.results[1].evidence.traffic) == 1
    assert len(http_peer.api_requests) == (1 if mode == "live" else 0)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("queries,declared,status", [
    (["page=1", "page=2"], {"page": 2}, "PASSED"),
    (["page=1", "page=2"], {"page": 3}, "ERROR"),
    (["page=1", "page=1"], {"page": 1}, "ERROR"),
    (["page=1", "page=2"], None, "ERROR"),
])
def test_same_path_selection_requires_one_exact_query_match(http_peer, mode, queries, declared, status):
    result, ui = run_query(http_peer, declared, ["/api/query?" + q for q in queries],
        mode=mode, target="query-multi", plan=[query_fixture("first"), query_fixture("second")])
    assert result.steps[1].status == status
    assert result.steps[2].status == ("COMPLETED" if status == "PASSED" else "BLOCKED")
    assert len(ui.results[1].evidence.traffic) == 2
    assert [t.request.query["page"] for t in ui.results[1].evidence.traffic] == [q[-1] for q in queries]
    if status == "PASSED":
        assert all(check.ok for check in result.steps[1].checks)
        if mode == "live":
            assert result.provider_recordings[0].request.query == {"page": "2"}
    else:
        assert "ambiguous" in result.steps[1].detail


@pytest.mark.parametrize("raw", ["a=1&a=2", "a=1&%61=2", "a+b=1&a%20b=2", "q=%", "q=%2Z", "q=%FF", "q=%C3%28"])
@pytest.mark.parametrize("mode", ["live", "mock"])
def test_invalid_wire_query_fails_before_http_or_fixture_consumption(browser_lab, http_peer, raw, mode):
    support, context = browser_lab(mode=mode,
        mock_plan=[query_fixture()] if mode == "mock" else None)
    set_paths(context, ["/api/query?" + raw])
    with pytest.raises(Exception) as error:
        act(support, context, "#query", mode=mode)
    assert raw not in str(error.value)
    assert context.errors[0] == "browser request transport or recording failed"
    assert context.mock_queue.index == 0
    assert http_peer.api_requests == []


def test_unrecorded_document_query_does_not_gain_api_restrictions(browser_lab, http_peer):
    support, context = browser_lab(path="/?asset=1&asset=2")
    evidence = act(support, context, "#fetch")
    assert evidence.traffic[0].request.query == {}
    assert any(request["url"] == "/?asset=1&asset=2" for request in http_peer.requests)


@pytest.mark.parametrize("fixture_query,passes", [(None, True), ({"page": "1"}, True), ({}, False), ({"page": "2"}, False)])
def test_ordered_mock_fixture_enforces_only_its_explicit_query(browser_lab, http_peer, fixture_query, passes):
    support, context = browser_lab(mode="mock", mock_plan=[query_fixture(query=fixture_query)])
    set_paths(context, ["/api/query?page=1"])
    if passes:
        evidence = act(support, context, "#query", mode="mock")
        assert evidence.traffic[0].request.query == {"page": "1"}
        assert context.mock_queue.index == 1
    else:
        with pytest.raises(Exception):
            act(support, context, "#query", mode="mock")
        assert context.mock_queue.index == 0
    assert http_peer.api_requests == []


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_matching_unassigned_query_does_not_satisfy_action(http_peer, mode):
    result, ui = run_query(http_peer, {"page": 1}, ["/api/query?page=1"], mode=mode, target="query-timer")
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert ui.results[1].evidence.traffic == []
    assert result.steps[1].checks == []
    assert "missing or ambiguous" in result.steps[1].detail


def test_unassigned_query_is_retained_as_diagnostic(browser_lab):
    support, context = browser_lab()
    set_paths(context, ["/api/query?page=1"])
    first = act(support, context, "#query-timer")
    next_action = act(support, context, "#delayed")
    diagnostics = first.diagnostic_recorded + next_action.diagnostic_recorded
    matches = [r for r in diagnostics if r.request.path == "api/query"]
    assert len(matches) == 1 and matches[0].request.query == {"page": "1"}
    assert matches[0].step_id is None
    assert first.traffic == []
    assert all(t.request.path == "api/delayed" for t in next_action.traffic)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("side", ["traffic", "response"])
def test_mutated_query_breaks_actual_request_response_pair(http_peer, mode, side):
    changed = []
    def mutate(result):
        changed.append(True)
        traffic = result.evidence.traffic[0]
        target = traffic.request if side == "traffic" else traffic.response.request
        target.query["page"] = "2"
        return result
    result, ui = run_query(http_peer, {"page": 1}, ["/api/query?page=1"], mode=mode, mutate=mutate)
    assert changed == [True]
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert "pairing mismatch" in result.steps[1].detail
    assert result.steps[1].checks == []


def test_recorder_cannot_rewrite_actual_query(http_peer):
    class RewritingRecorder(InMemoryRecorder):
        def record(self, response):
            response.request.query["page"] = "2"
            super().record(response)
    result, ui = run_query(http_peer, {"page": 1}, ["/api/query?page=1"], recorder=RewritingRecorder())
    assert len(http_peer.api_requests) == 1
    assert ui.results[1].evidence.traffic[0].request.query == {"page": "1"}
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert "Recorder" in result.steps[1].detail


def test_mock_query_fixture_rejects_coordinated_pair_mutation(http_peer):
    changed = []
    def mutate(result):
        changed.append(True)
        traffic = result.evidence.traffic[0]
        traffic.request.query["page"] = "2"
        traffic.response.request.query["page"] = "2"
        return result
    result, ui = run_query(http_peer, {"page": 2}, ["/api/query?page=1"], mode="mock",
        plan=[query_fixture(query={"page": "1"})], mutate=mutate)
    assert changed == [True]
    assert ui.results[1].evidence.traffic[0].request == ui.results[1].evidence.traffic[0].response.request
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert "fixture query" in result.steps[1].detail
    assert result.steps[1].checks == []
    assert http_peer.api_requests == []


def test_normalizer_cannot_rewrite_actual_query(http_peer):
    class RewritingNormalizer(FakeNormalizer):
        def normalize(self, response):
            response.request.query["page"] = "2"
            return super().normalize(response)
    result, ui = run_query(http_peer, {"page": 1}, ["/api/query?page=1"], normalizer=RewritingNormalizer())
    assert len(http_peer.api_requests) == 1
    assert ui.results[1].evidence.traffic[0].request.query == {"page": "1"}
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert "normalizer" in result.steps[1].detail.lower()


def test_replayed_query_action_evidence_cannot_satisfy_new_action(http_peer):
    captured = []
    def replay(result):
        captured.append(copy.deepcopy(result))
        return captured[0]
    ui = QueryUi(http_peer.base_url, ["/api/query?page=1"], replay)
    scenario = query_scenario({"page": 1})
    scenario.steps[2] = replace(scenario.steps[1], id="second_query")
    result = e2e.run(scenario, ui=ui, auth=FakeAuth(), state=None,
        recorder=InMemoryRecorder(), normalizer=FakeNormalizer())
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "ERROR"]
    assert len(http_peer.api_requests) == 2
    assert captured[0].evidence.traffic[0].request.query == {"page": "1"}


def test_query_sentinels_are_absent_from_default_runtime_representations(http_peer):
    secret = "synthetic-query-sensitive-672"
    result, ui = run_query(http_peer, {"token": "different"}, ["/api/query?token=" + secret])
    assert result.steps[1].status == "FAILED"
    traffic = ui.results[1].evidence.traffic[0]
    assert traffic.request.query == {"token": secret}
    report = RunReport("synthetic.query", [result])
    objects = [traffic.request, traffic.response, traffic, ui.results[1], ui.results[1].evidence,
               query_fixture(query={"token": secret}), RequestTemplate("POST", "api/query", query={"token": secret}),
               permit(value=secret), report, result, *result.steps, *result.checks]
    assert all(secret not in repr(obj) for obj in objects)
    assert secret not in str(report.localize())
