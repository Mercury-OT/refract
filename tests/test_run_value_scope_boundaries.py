"""Independent generated sources avoid collisions against shared storage.

The synthetic target reads requests and stored records only; explicit repeated
values still exercise its real uniqueness constraint.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from refracto import ports
from refracto.runner import run_scenario
from tests.test_member_reference_consumers import RecordsService, consumer


EXAMPLE = (Path(__file__).resolve().parents[1]
           / "examples/minimal/run_unique_create_locate_read.yaml")


class UniqueRecords(RecordsService):
    """The same public Records target, with a unique code constraint."""

    def send(self, request, session):
        authenticated = session.get("token") in {
            token for _, token in self.authentications}
        if (authenticated and request.method == "POST" and request.path == "records"
                and isinstance(request.body, dict)
                and set(request.body) == {"code", "name"}
                and any(row["code"] == request.body["code"]
                        for row in self.records.values())):
            self.requests.append((request.method, request.path, deepcopy(request.body)))
            payload = {"error": "duplicate_code"}
            return ports.RecordedResponse(
                409, {}, payload, json.dumps(payload), None, request)
        return super().send(request, session)


def target(*, unique):
    app, adapters = consumer("records")
    if unique:
        app = UniqueRecords()
        adapters = replace(adapters, auth=app, api=app)
    return app, adapters


def repeated_children(tmp_path, *, distinct_codes=False):
    child = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    child["scenario"] = "shared.create_locate_read"
    child_path = tmp_path / "child.yaml"
    child_path.write_text(yaml.safe_dump(child, sort_keys=False), encoding="utf-8")
    steps = []
    for name in ("one", "two"):
        step = {"id": name, "do": {"include": child["scenario"]}}
        if distinct_codes:
            step["with"] = {"record_code": {"concat": [
                {"from_parameter": "token"}, "-" + name]}}
        steps.append(step)
    parent = {"schema_version": 1, "scenario": "records.repeated_children",
              "users": ["creator"], "steps": steps}
    if distinct_codes:
        parent["parameters"] = {"token": {"from_run": "unique"}}
    path = tmp_path / "parent.yaml"
    path.write_text(yaml.safe_dump(parent, sort_keys=False), encoding="utf-8")
    path.with_suffix(".includes.json").write_text(json.dumps({
        "manifest_version": 1,
        "scenarios": {child["scenario"]: {
            "path": child_path.name,
            "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}),
        encoding="utf-8")
    return path


@pytest.mark.parametrize("unique", [False, True])
def test_shared_target_backend_and_e2e_use_distinct_generated_values(unique):
    app, adapters = target(unique=unique)
    report = run_scenario(EXAMPLE, adapters,
                          projections=("backend", "e2e", "contract"))
    backend, live, contract = report.domains
    assert report.status == "PASSED", report.localize()
    assert backend.status == contract.status == live.status == "PASSED"
    writes = [body for method, _, body in app.requests if method == "POST"]
    assert len(writes) == 2 and writes[0]["code"] != writes[1]["code"]
    assert len(app.records) == 2
    assert len({row["code"] for row in app.records.values()}) == 2
    for domain in (backend, live):
        assert [record.status for record in domain.provider_recordings] == [201, 200, 200]
        token = report.run_unique_values[domain.projection]["run_token"]
        assert domain.provider_recordings[0].request.body["code"] == token + "-records-" + token
    assert report.run_unique_values["backend"] == report.run_unique_values["contract"]


def test_repeated_child_defaults_generate_distinct_values_on_unique_target(tmp_path):
    app, adapters = target(unique=True)
    report = run_scenario(repeated_children(tmp_path), adapters,
                          projections=("backend", "contract"))
    backend = report.domains[0]
    assert report.status == backend.status == "PASSED", report.localize()
    assert [step.step_id for step in backend.steps] == [
        "one/create", "one/locate", "one/read", "two/create", "two/locate", "two/read"]
    assert [record.status for record in backend.provider_recordings] == [201, 200, 200, 201, 200, 200]
    assert app.requests[0][2]["code"] != app.requests[3][2]["code"]
    assert len(app.records) == 2
    assert len(set(report.run_unique_values["backend"].values())) == 2


def test_explicit_identical_override_still_fails_unique_target(tmp_path):
    path = repeated_children(tmp_path)
    raw = yaml.safe_load(path.read_text())
    raw["parameters"] = {"shared": {"from_run": "unique"}}
    for step in raw["steps"]:
        step["with"] = {"run_token": {"from_parameter": "shared"}}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    app, adapters = target(unique=True)
    report = run_scenario(path, adapters, projections=("backend", "contract"))
    assert report.status == "FAILED"
    backend = report.domains[0]
    assert [record.status for record in backend.provider_recordings] == [201, 200, 200, 409]
    assert [step.status for step in backend.steps] == [
        "PASSED", "PASSED", "PASSED", "FAILED", "BLOCKED", "BLOCKED"]
    assert len(app.records) == 1
    assert set(report.run_unique_values["backend"]) == {"shared"}
    assert app.requests[0][2]["code"] == app.requests[3][2]["code"]


def test_explicit_caller_disambiguation_allows_both_child_invocations(tmp_path):
    app, adapters = target(unique=True)
    report = run_scenario(repeated_children(tmp_path, distinct_codes=True), adapters,
                          projections=("backend", "contract"))
    assert report.status == "PASSED" and report.degradations() == []
    assert all(domain.status == "PASSED" for domain in report.domains)
    assert [body["code"] for method, _, body in app.requests if method == "POST"] == [
        report.run_unique_values["backend"]["token"] + "-one",
        report.run_unique_values["backend"]["token"] + "-two"]
    assert len(app.records) == 2 and len(app.requests) == 6
    assert app.requests[2][1] == "records/22"
    assert app.requests[5][1] == "records/23"


def test_separate_runner_calls_get_distinct_values_on_the_same_target():
    app, adapters = target(unique=True)
    reports = [run_scenario(EXAMPLE, adapters, projections=selection)
               for selection in (("backend", "contract"), ("e2e",))]
    assert all(report.status == "PASSED" for report in reports)
    assert reports[0].run_unique_values["backend"]["run_token"] != reports[1].run_unique_values["e2e"]["run_token"]
    assert len(app.records) == 2 and len(app.requests) == 6
    assert len({row["code"] for row in app.records.values()}) == 2


def test_two_direct_unique_parameters_are_independent_values(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    raw["parameters"]["record_name"] = {"from_run": "unique"}
    path = tmp_path / "two_parameters.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    app, adapters = target(unique=True)
    report = run_scenario(path, adapters, projections=("backend", "contract"))
    assert report.status == "PASSED"
    created = app.records[22]
    values = report.run_unique_values["backend"]
    assert values["record_name"] != values["run_token"]
    assert created["name"] == values["record_name"]
    assert created["code"] == values["run_token"] + "-records-" + values["run_token"]
