"""Live Enter consumers: frozen normal targets and explicit target-side faults."""
import json

import pytest

from examples.ui_enter_search.app import Application
from examples.ui_enter_search.run import ROOT, SCENARIO, run_case, target_hashes, verify_frozen_targets
from refracto.declaration.loader import load_scenario


IMPLEMENTATIONS = ("listener", "property")
RECEIPT = {"key": "Enter", "target_matches": 1, "focused": True,
           "keydown_count": 1, "keyup_count": 1}


def step(row, identity):
    return next(item for item in row["steps"] if item["id"] == identity)


def evidence(row, identity):
    return next(item for item in row["browser_evidence"] if item["step"] == identity)


def api_requests(row):
    return [item for item in row["server_requests"] if item["path"].startswith("/api/")]


def assert_bounded_run(row):
    assert row["degradation"] == []
    assert row["closed_contexts"] == row["browser_context_count"] == row["session_calls"] == 1
    assert row["api_send_calls"] == 0
    assert {item["user"] for item in row["browser_evidence"]} == {"reader"}
    assert len({item["session_generation"] for item in row["browser_evidence"]}) == 1
    assert row["records"] == [
        {"id": "r1", "name": "Quarterly report"}, {"id": "r2", "name": "Invoice"}]
    assert not evidence(row, "open_search")["traffic"]
    assert not evidence(row, "fill_search")["traffic"]
    assert not any(item["diagnostic_requests"] for item in row["browser_evidence"])
    assert all(item["method"] == "GET" for item in row["server_requests"])


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_enter_search_live(implementation):
    row = run_case(implementation)
    assert row["status"] == "PASSED", row["steps"]
    assert_bounded_run(row)
    assert row["target_faults"] == []
    assert step(row, "open_search")["status"] == "COMPLETED"
    assert step(row, "fill_search")["status"] == step(row, "submit_search")["status"] == "PASSED"
    assert step(row, "submit_search")["key_press"] == RECEIPT
    assert evidence(row, "submit_search")["key_press"] == RECEIPT
    assert evidence(row, "submit_search")["traffic"] == [
        {"method": "GET", "path": "records", "query": {"q": "report"}}]
    assert evidence(row, "submit_search")["rendered_names"] == ["Quarterly report"]
    assert api_requests(row) == [{"method": "GET", "path": "/api/records", "query": {"q": ["report"]}}]
    assert row["server_responses"] == [{"status": 200, "payload": {
        "records": [{"id": "r1", "name": "Quarterly report"}]}}]


class IgnoredEnter(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = "if (event.key !== 'Enter') return;"
        assert source.count(original) == 1
        self.faults_applied = ["ignored-enter"]
        return source.replace(original, "return;").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_ignored_enter_has_delivery_but_missing_request_is_an_error(implementation):
    row = run_case(implementation, app_type=IgnoredEnter)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    assert row["target_faults"] == ["ignored-enter"]
    assert step(row, "fill_search")["status"] == "PASSED"
    observed = step(row, "submit_search")
    assert observed["status"] == "ERROR"
    assert observed["key_press"] == RECEIPT
    assert "missing or ambiguous" in observed["detail"]
    assert evidence(row, "submit_search")["traffic"] == []
    assert api_requests(row) == []
    assert row["server_responses"] == []


class WrongQuery(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = "encodeURIComponent(input.value)"
        assert source.count(original) == 1
        self.faults_applied = ["wrong-query"]
        return source.replace(original, "encodeURIComponent('invoice')").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_associated_wrong_query_fails_without_a_repair_request(implementation):
    row = run_case(implementation, app_type=WrongQuery)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    assert row["target_faults"] == ["wrong-query"]
    observed = step(row, "submit_search")
    assert observed["status"] == "FAILED"
    assert observed["key_press"] == RECEIPT
    assert any(item["check"] == "request" and item["ok"] is False for item in observed["checks"])
    assert api_requests(row) == [{"method": "GET", "path": "/api/records", "query": {"q": ["invoice"]}}]
    assert evidence(row, "submit_search")["rendered_names"] == ["Invoice"]


class StaleResults(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = "render(payload.records);"
        assert source.count(original) == 1
        self.faults_applied = ["stale-results"]
        return source.replace(original, "// Fault: retain the previous rendered rows.").encode()


class WrongResults(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = "render(payload.records);"
        assert source.count(original) == 1
        self.faults_applied = ["wrong-results"]
        return source.replace(original, "render([{name: 'Invoice'}]);").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
@pytest.mark.parametrize("app_type,names", [
    (StaleResults, ["Quarterly report", "Invoice"]), (WrongResults, ["Invoice"]),
])
def test_correct_query_and_response_cannot_hide_stale_or_wrong_rendering(implementation, app_type, names):
    row = run_case(implementation, app_type=app_type)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    observed = step(row, "submit_search")
    assert observed["status"] == "FAILED"
    assert observed["key_press"] == RECEIPT
    assert all(item["ok"] for item in observed["checks"] if item["point"] != "frontend")
    assert any(not item["ok"] for item in observed["checks"] if item["point"] == "frontend")
    assert evidence(row, "submit_search")["rendered_names"] == names
    assert api_requests(row) == [{"method": "GET", "path": "/api/records", "query": {"q": ["report"]}}]
    assert row["server_responses"][0]["payload"]["records"] == [{"id": "r1", "name": "Quarterly report"}]


class FocusTheft(Application):
    def page(self):
        source = super().page().decode()
        return source.replace('<p>Press Enter', '<button id="elsewhere" type="button">Help</button><p>Press Enter').encode()

    def script(self, name):
        source = super().script(name).decode()
        self.faults_applied = ["focus-theft-after-fill"]
        return (source + """
input.addEventListener('input', () => document.querySelector('#elsewhere').focus());
// This explicit fault witness records any erroneously dispatched Enter.
document.addEventListener('keydown', event => {
  if (event.key === 'Enter') fetch('/api/enter-observed', {headers: authorization});
}, true);
""").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_focus_stolen_after_fill_errors_before_enter_without_focus_repair(implementation):
    row = run_case(implementation, app_type=FocusTheft)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    assert row["target_faults"] == ["focus-theft-after-fill"]
    assert step(row, "fill_search")["status"] == "PASSED"
    assert step(row, "submit_search")["status"] == "ERROR"
    assert step(row, "submit_search")["key_press"] is None
    assert [item["step"] for item in row["browser_evidence"]] == ["open_search", "fill_search"]
    # Neither the search handler nor the document-level Enter witness ran.
    assert api_requests(row) == []
    assert row["server_responses"] == []


def test_normal_targets_are_frozen_and_scenario_keeps_the_approved_shape():
    verify_frozen_targets()
    assert target_hashes() == json.loads((ROOT / "target-sources.json").read_text())["sha256"]
    scenario = load_scenario(SCENARIO)
    assert scenario.id == "records.search_with_enter"
    assert [item.id for item in scenario.steps] == ["open_search", "fill_search", "submit_search"]
    assert [item.action for item in scenario.steps] == ["open", "fill", "press"]
    assert scenario.steps[1].on_failure == "stop"
    assert scenario.steps[2].key == "Enter"
    assert scenario.steps[1].target == scenario.steps[2].target == "records.search_input"
    assert [item.params["anchor"] for item in scenario.steps[2].expect.frontend] == [
        "records.result_rows", "records.result_rows"]
    assert scenario.parameters == {
        "search_text": "report", "expected_name": "Quarterly report", "excluded_name": "Invoice"}
