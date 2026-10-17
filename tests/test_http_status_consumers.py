"""Public synthetic consumers, documentation, and composition status evidence."""
import copy
import hashlib
import json
from pathlib import Path
import re

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto.cli import main
from refracto.declaration.impact import inspect_impact
from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/documents/scenarios/http_status_create_delete.yaml"


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


class StatusOnlyMutation(DocumentRestApp):
    """Change one transport status while preserving all response content."""

    def __init__(self, original, replacement):
        super().__init__()
        self.original, self.replacement = original, replacement
        self.original_bodies = []

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        self.original_bodies.append(copy.deepcopy(response.body))
        if response.status == self.original:
            return RestResponse(self.replacement, response.body, response.headers)
        return response


def test_documents_complete_example_creates_201_and_deletes_empty_204():
    app = DocumentRestApp()
    report = run_scenario(EXAMPLE, build_adapters(app), projections=("backend", "contract"))

    assert report.status == "PASSED"
    assert report.degradations() == []
    assert app.request_count == 2  # Contract sends no additional request.
    recordings = report.domains[0].provider_recordings
    assert [item.status for item in recordings] == [201, 204]
    assert recordings[1].json is None and recordings[1].text == ""
    assert recordings[0].json["resource"]["document"]["identifier"] in recordings[1].request.path


@pytest.mark.parametrize("replacement,passed", [(201, True), (202, True), (200, False)])
def test_documents_explicit_status_set_has_passing_neighbors(tmp_path, replacement, passed):
    raw = yaml.safe_load(EXAMPLE.read_text())
    raw["steps"][0]["expect"]["response"][0] = {"check": "status_in", "values": [201, 202]}
    path = _write(tmp_path / "status_set.yaml", raw)
    app = StatusOnlyMutation(201, replacement)
    adapters = build_adapters(app)
    report = run_scenario(path, adapters, projections=("backend", "contract"))

    assert report.status == ("PASSED" if passed else "FAILED")
    assert {domain.status for domain in report.domains} == {report.status}
    first = report.domains[0].provider_recordings[0]
    assert first.json == app.original_bodies[0]
    assert adapters.normalizer.normalize(first).succeeded is True
    status_check = next(check for check in report.domains[0].checks if check.check == "status_in")
    assert status_check.ok is passed
    assert app.request_count == 2


@pytest.mark.parametrize("original,replacement", [(201, 202), (204, 200)])
def test_documents_status_only_mutation_fails_with_business_success_unchanged(original, replacement):
    app = StatusOnlyMutation(original, replacement)
    adapters = build_adapters(app)
    report = run_scenario(EXAMPLE, adapters, projections=("backend", "contract"))

    assert report.status == "FAILED"
    assert {domain.status for domain in report.domains} == {"FAILED"}
    recordings = report.domains[0].provider_recordings
    assert all(record.json == body for record, body in zip(recordings, app.original_bodies))
    assert all(adapters.normalizer.normalize(record).succeeded for record in recordings)
    checks = report.domains[0].checks
    assert [check.check for check in checks if not check.ok] == ["status_equals"]
    assert all(check.ok for check in checks if check.check == "success")
    assert any("status" in check.detail.lower() for check in report.domains[1].checks if not check.ok)


@pytest.mark.parametrize("replacement,expected", [(422, "PASSED"), (500, "FAILED")])
def test_documents_same_rejection_body_cannot_substitute_server_error(tmp_path, replacement, expected):
    source = ROOT / "examples/documents/scenarios/rejected_create.yaml"
    raw = yaml.safe_load(source.read_text())
    raw["steps"][0]["expect"]["response"].append({"check": "status_equals", "value": 422})
    app = StatusOnlyMutation(422, replacement)
    adapters = build_adapters(app)
    report = run_scenario(_write(tmp_path / "reject.yaml", raw), adapters,
                          projections=("backend", "contract"))

    assert report.status == expected
    assert {domain.status for domain in report.domains} == {expected}
    observed = report.domains[0].provider_recordings[0]
    assert observed.json == app.original_bodies[0]
    assert adapters.normalizer.normalize(observed).succeeded is False
    assert adapters.normalizer.normalize(observed).fields["error_code"] == "category_not_allowed"
    normalized_check = next(check for check in report.domains[0].checks if check.check == "failure")
    assert normalized_check.ok
    assert app.request_count == 1


def _include_bundle(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text())
    child = copy.deepcopy(raw)
    child["scenario"] = "shared.create_document"
    child["steps"] = child["steps"][:1]
    child["results"] = {"document_id": {"from_step": "create", "response_field": "document_id"}}
    parent = copy.deepcopy(raw)
    parent["scenario"] = "documents.included_status"
    parent["steps"] = [{"id": "setup", "do": {"include": child["scenario"]},
                        "with": {"document_title": {"from_parameter": "document_title"}}},
                       parent["steps"][1]]
    parent["steps"][1]["do"]["request"]["path"][1] = {"from_step": "setup", "result": "document_id"}
    child_path = _write(tmp_path / "scenarios/shared/create.yaml", child)
    parent_path = _write(tmp_path / "scenarios/parent.yaml", parent)
    parent_path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1, "scenarios": {
        child["scenario"]: {"path": "shared/create.yaml", "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}
    }}), encoding="utf-8")
    return parent_path, child_path


def test_included_status_checks_and_named_results_execute_and_expand(tmp_path, capsys):
    parent, _ = _include_bundle(tmp_path)
    report = run_scenario(parent, build_adapters(DocumentRestApp()), projections=("backend", "contract"))
    assert report.status == "PASSED"
    assert [step.step_id for step in report.domains[0].steps] == ["setup/create", "delete"]
    assert report.source_lookup["setup/create"]["scenario_id"] == "shared.create_document"
    assert list(report.domains[0].steps[1].resolved_bindings.values()) == ["document-1"]
    assert main(["validate", str(parent)]) == 0
    assert "OK documents.included_status" in capsys.readouterr().out
    assert main(["validate", str(parent), "--expand"]) == 0
    expanded = json.loads(capsys.readouterr().out)
    check = expanded["steps"][0]["expect"]["response"][0]
    assert check == {"check": "status_equals", "value": {"kind": "literal", "value": 201}}


def test_included_wrong_status_fails_at_child_source_but_usable_result_continues(tmp_path):
    parent, _ = _include_bundle(tmp_path)
    app = StatusOnlyMutation(201, 202)
    report = run_scenario(parent, build_adapters(app), projections=("backend", "contract"))
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["FAILED", "PASSED"]
    assert report.domains[0].steps[1].after_failures == ["setup/create"]
    assert report.domains[0].steps[0].step_id == "setup/create"
    located = [item for item in report.localize() if item[1] == "setup/create"]
    assert located
    assert report.source_lookup[located[0][1]]["scenario_id"] == "shared.create_document"
    assert app.request_count == 2


@pytest.mark.parametrize("new_check", [{"check": "status_equals", "value": 202},
                                       {"check": "status_in", "values": [201, 202]}])
def test_impact_detects_included_status_contract_change(tmp_path, new_check):
    parent, child = _include_bundle(tmp_path)
    before = tmp_path / "before.yaml"
    before.write_bytes(child.read_bytes())
    changed = yaml.safe_load(child.read_text())
    changed["steps"][0]["expect"]["response"][0] = new_check
    _write(child, changed)

    report = inspect_impact(before, child, parent.parent)
    assert report["status"] == "COMPLETE" and report["review_required"] is True
    assert report["target"]["structure_changed"] is True
    assert any(change["location"].startswith("/steps/by-id/create/expect/response/0")
               for change in report["changes"])
    assert report["parents"][0]["validity"] == {
        "actual": "invalid", "hypothetical_before": "valid", "hypothetical_after": "valid"}


@pytest.mark.parametrize("document", ["SCENARIO.md", "docs/tasks/http-status-assertions.md"])
def test_new_documentation_fragments_load_in_declared_response_context(tmp_path, document):
    fragments = re.findall(r"```yaml\n(.*?)\n```", (ROOT / document).read_text(), re.S)
    checks_seen = set()
    for index, fragment in enumerate(fragments):
        checks = yaml.safe_load(fragment)
        if not isinstance(checks, list) or not checks or not all(
                isinstance(check, dict) and check.get("check") in {"status_equals", "status_in"}
                for check in checks):
            continue
        raw = {"schema_version": 1, "scenario": "docs.status_fragment", "actor": "reader",
               "steps": [{"id": "read", "do": {"request": {"method": "GET", "path": ["documents"]}},
                          "expect": {"response": checks}}]}
        loaded = load_scenario(_write(tmp_path / f"fragment-{index}.yaml", raw))
        checks_seen.update(check.check for check in loaded.steps[0].expect.response)
    assert checks_seen == {"status_equals", "status_in"}
