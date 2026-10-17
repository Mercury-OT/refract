"""Real in-process second-adapter evidence for continued declared actions."""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto.runner import run_scenario


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/documents/scenarios/continue_after_failure.yaml"


class ChangedCreation(DocumentRestApp):
    """Bounded target fault: returned content or stored content, not assertions."""

    def __init__(self, fault):
        super().__init__()
        self.fault = fault

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if method != "POST" or response.status != 201:
            return response
        changed = deepcopy(response.body)
        document = changed["resource"]["document"]
        if self.fault == "missing-id":
            del document["identifier"]
        elif self.fault == "null-id":
            document["identifier"] = None
        else:
            document["properties"]["title"] = "wrong-title"
            if self.fault == "stored-title":
                self._documents[document["identifier"]]["properties"]["title"] = "wrong-title"
        return RestResponse(response.status, changed, response.headers)


def write_example(tmp_path, change):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "documents.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
@pytest.mark.parametrize("fault,statuses", [
    (None, ["PASSED", "PASSED", "PASSED"]),
    ("response-title", ["FAILED", "PASSED", "PASSED"]),
    ("stored-title", ["FAILED", "FAILED", "PASSED"]),
])
def test_documents_collect_checks_and_really_delete(projections, fault, statuses):
    app = DocumentRestApp() if fault is None else ChangedCreation(fault)
    report = run_scenario(EXAMPLE, build_adapters(app), projections=projections)
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == statuses
    assert report.status == ("PASSED" if fault is None else "FAILED")
    assert app.request_count == 3  # Contract must not issue another request.
    assert [(method, path.split("?")[0]) for method, path, _, _ in app.requests] == [
        ("POST", "/v3/documents"), ("GET", "/v3/documents"),
        ("DELETE", "/v3/documents/document-1")]
    assert app._documents == {}
    assert domain.steps[0].after_failures == []
    assert domain.steps[1].after_failures == ([] if fault is None else ["create"])
    assert domain.steps[2].after_failures == (
        ["create", "read"] if fault == "stored-title" else [] if fault is None else ["create"])
    assert all(step.blocked_by == [] for step in domain.steps)
    if fault:
        assert (projections[0], "create", "response", "field_equals") in [
            item[:4] for item in report.localize()]
    if "contract" in projections:
        assert report.domains[1].status == report.status


@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
def test_explicit_stop_preserves_failed_result_and_does_not_delete(tmp_path, projections):
    path = write_example(tmp_path, lambda raw: raw["steps"][0].update(on_failure="stop"))
    app = ChangedCreation("response-title")
    report = run_scenario(path, build_adapters(app), projections=projections)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["FAILED", "BLOCKED", "BLOCKED"]
    assert [step.blocked_by for step in report.domains[0].steps[1:]] == [["create"], ["create"]]
    assert app.request_count == 1
    assert list(app._documents) == ["document-1"]


@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
@pytest.mark.parametrize("fault", ["missing-id", "null-id"])
def test_unavailable_id_blocks_consumers_but_not_independent_list(tmp_path, projections, fault):
    def append_independent_read(raw):
        raw["steps"].append({"id": "independent_read", "do": {"request": {
            "method": "GET", "path": ["documents", "search"]}}, "expect": {
            "response": [{"check": "status_equals", "value": 200}, {"check": "success"}]}})
    path = write_example(tmp_path, append_independent_read)
    app = ChangedCreation(fault)
    report = run_scenario(path, build_adapters(app), projections=projections)
    domain = report.domains[0]
    # has asserts presence, not non-nullness; unavailable references remain blocked.
    expected_first = "FAILED" if fault == "missing-id" else "PASSED"
    assert [step.status for step in domain.steps] == [expected_first, "BLOCKED", "BLOCKED", "PASSED"]
    assert report.status != "PASSED"
    assert domain.status == ("FAILED" if fault == "missing-id" else "DEGRADED")
    assert app.request_count == 2
    assert [method for method, _, _, _ in app.requests] == ["POST", "GET"]
    assert list(app._documents) == ["document-1"]
    for step in domain.steps[1:3]:
        assert step.blocked_by == ["create"]
        assert step.resolved_bindings == {}
    assert any(item[1] == "delete" for item in report.degradations())
