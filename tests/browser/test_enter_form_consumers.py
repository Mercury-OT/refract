"""Live form variants reuse the frozen Enter Scenario and its exact adapter."""
import hashlib

import pytest

from examples.ui_enter_form.app import Application
from examples.ui_enter_form.run import ROOT, SCENARIO, run_case, target_hashes, verify_frozen_targets
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
    assert not any(item["path"] == "/search" for item in row["server_requests"])
    assert all(item["method"] == "GET" for item in row["server_requests"])
    assert row["target_sha256"] == target_hashes()
    assert row["scenario_sha256"] == hashlib.sha256(SCENARIO.read_bytes()).hexdigest()
    assert row["scenario_source"] == "examples/ui_enter_search/scenario.yaml"
    assert row["adapter_source"] == "examples/ui_enter_search/adapter.py"


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_native_form_search_passes_with_unchanged_scenario_and_adapter(implementation):
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
    assert not any(item["diagnostic_requests"] for item in row["browser_evidence"])
    assert api_requests(row) == [{"method": "GET", "path": "/api/records", "query": {"q": ["report"]}}]
    assert row["server_responses"] == [{"status": 200, "payload": {
        "records": [{"id": "r1", "name": "Quarterly report"}]}}]


class IgnoredSubmit(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = "event.preventDefault();"
        assert source.count(original) == 1
        self.faults_applied = ["ignored-submit"]
        return source.replace(original, original + " return;").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_ignored_submit_retains_key_delivery_but_missing_request_is_error(implementation):
    row = run_case(implementation, app_type=IgnoredSubmit)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    assert row["target_faults"] == ["ignored-submit"]
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
def test_wrong_form_query_fails_without_api_repair(implementation):
    row = run_case(implementation, app_type=WrongQuery)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    observed = step(row, "submit_search")
    assert observed["status"] == "FAILED"
    assert observed["key_press"] == RECEIPT
    assert any(item["check"] == "request" and item["ok"] is False for item in observed["checks"])
    assert api_requests(row) == [{"method": "GET", "path": "/api/records", "query": {"q": ["invoice"]}}]
    assert evidence(row, "submit_search")["rendered_names"] == ["Invoice"]


class WrongResponse(Application):
    def response(self, method, path, query, headers):
        status, payload = super().response(method, path, query, headers)
        if status == 200:
            self.faults_applied = ["wrong-response"]
            return status, {"records": [{"id": "r2", "name": "Invoice"}]}
        return status, payload


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_successful_status_with_wrong_response_does_not_pass(implementation):
    row = run_case(implementation, app_type=WrongResponse)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    observed = step(row, "submit_search")
    assert observed["status"] == "FAILED"
    assert observed["key_press"] == RECEIPT
    assert any(item["point"] == "response" and not item["ok"] for item in observed["checks"])
    assert api_requests(row) == [{"method": "GET", "path": "/api/records", "query": {"q": ["report"]}}]
    assert row["server_responses"] == [{"status": 200, "payload": {
        "records": [{"id": "r2", "name": "Invoice"}]}}]


class StaleResults(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = "render(payload.records);"
        assert source.count(original) == 1
        self.faults_applied = ["stale-results"]
        return source.replace(original, "// Fault: retain previous rendered rows.").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_correct_request_and_response_do_not_hide_stale_form_results(implementation):
    row = run_case(implementation, app_type=StaleResults)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    observed = step(row, "submit_search")
    assert observed["status"] == "FAILED"
    assert all(item["ok"] for item in observed["checks"] if item["point"] != "frontend")
    assert any(not item["ok"] for item in observed["checks"] if item["point"] == "frontend")
    assert evidence(row, "submit_search")["rendered_names"] == ["Quarterly report", "Invoice"]
    assert row["server_responses"][0]["payload"]["records"] == [{"id": "r1", "name": "Quarterly report"}]


class ValidationRejects(Application):
    def page(self):
        self.faults_applied = ["native-validation"]
        return super().page().replace(b'name="q" required', b'name="q" required pattern="invoice"')


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_native_validation_is_not_removed_or_forced_past(implementation):
    row = run_case(implementation, app_type=ValidationRejects)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    observed = step(row, "submit_search")
    assert observed["status"] == "ERROR"
    assert observed["key_press"] == RECEIPT
    assert "missing or ambiguous" in observed["detail"]
    assert api_requests(row) == []
    assert row["server_responses"] == []


class ProgrammaticSubmit(Application):
    def script(self, name):
        source = super().script(name).decode()
        self.faults_applied = ["programmatic-submit"]
        return (source + """
input.addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    form.requestSubmit(document.querySelector('#search-submit'));
  }
});
""").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_programmatic_submit_cannot_replace_enter_default_submission(implementation):
    row = run_case(implementation, app_type=ProgrammaticSubmit)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    assert step(row, "submit_search")["status"] == "ERROR"
    assert all(not item["traffic"] for item in row["browser_evidence"])


class WrongForm(Application):
    def page(self):
        return super().page().replace(b'<p>Press Enter', b'<form id="other-form"><button type="submit">Other</button></form><p>Press Enter')

    def script(self, name):
        source = super().script(name).decode()
        self.faults_applied = ["wrong-form"]
        return (source + """
document.querySelector('#other-form').addEventListener('submit', event => {
  event.preventDefault();
  fetch('/api/records?q=' + encodeURIComponent(input.value), {headers: authorization});
});
input.addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    document.querySelector('#other-form').requestSubmit();
  }
});
""").encode()


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_other_form_request_cannot_satisfy_enter_search(implementation):
    row = run_case(implementation, app_type=WrongForm)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    assert step(row, "submit_search")["status"] == "ERROR"
    assert all(not item["traffic"] for item in row["browser_evidence"])


class FocusTheft(Application):
    def script(self, name):
        self.faults_applied = ["focus-theft-after-fill"]
        return super().script(name) + b"""
input.addEventListener('input', () => document.querySelector('#search-submit').focus());
document.addEventListener('keydown', event => {
  if (event.key === 'Enter') fetch('/api/enter-observed', {headers: authorization});
}, true);
"""


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_form_target_focus_theft_is_not_repaired(implementation):
    row = run_case(implementation, app_type=FocusTheft)
    assert row["status"] == "FAILED", row["steps"]
    assert_bounded_run(row)
    assert step(row, "fill_search")["status"] == "PASSED"
    assert step(row, "submit_search")["status"] == "ERROR"
    assert step(row, "submit_search")["key_press"] is None
    assert [item["step"] for item in row["browser_evidence"]] == ["open_search", "fill_search"]
    assert api_requests(row) == []


def test_frozen_form_targets_reuse_exact_prior_scenario_without_an_adapter_copy():
    verify_frozen_targets()
    assert not (ROOT / "scenario.yaml").exists()
    assert not (ROOT / "adapter.py").exists()
    assert hashlib.sha256(SCENARIO.read_bytes()).hexdigest() == (
        "4456e00a0abbdb29a341c9aab7ee6f5047dcd2d7370f8174c70fdf22918eae07")
    scenario = load_scenario(SCENARIO)
    assert scenario.id == "records.search_with_enter"
    assert [item.id for item in scenario.steps] == ["open_search", "fill_search", "submit_search"]
    assert [item.action for item in scenario.steps] == ["open", "fill", "press"]
    assert scenario.steps[-1].key == "Enter"
