"""Published header examples remain executable, approved declarations."""
from pathlib import Path
import re

import pytest
import yaml

from refracto.declaration.loader import load_scenario
from refracto.declaration.binding import prepare_step


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("document", ["SCENARIO.md", "docs/tasks/business-http-headers.md"])
def test_header_fragments_load_in_their_stated_context(tmp_path, document):
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / document).read_text(), re.S)
    blocks = [block for block in blocks if "header_equals" in block or "header_absent" in block]
    assert blocks
    for index, block in enumerate(blocks):
        fragment = yaml.safe_load(block)
        if "check" in fragment[0]:
            fragment = [{"id": "observe", "do": {"request": {
                "method": "GET", "path": ["records"]}}, "expect": {"response": fragment}}]
        raw = {"schema_version": 1, "scenario": "demo.documented_headers", "users": ["creator"],
               "parameters": {"idempotency_key": "example-key", "record_name": "Example record"},
               "steps": fragment}
        path = tmp_path / f"fragment-{index}.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False))
        scenario = load_scenario(path)
        prepared, _ = prepare_step(scenario.steps[0], scenario, {})
        assert {a.check for a in prepared.expect.response} >= {"header_equals", "header_absent"}


def test_approved_idempotency_example_preserves_its_obligations():
    path = ROOT / "examples/minimal/idempotent_create.yaml"
    raw = yaml.safe_load(path.read_text())
    assert raw["schema_version"] == 1
    assert raw["scenario"] == "records.idempotent_create"
    assert raw["users"] == ["creator"]
    assert raw["parameters"] == {"idempotency_key": "record-create-example-001",
                                  "record_name": "idempotency-example-record"}
    first, replay, read = raw["steps"]
    assert [step["id"] for step in raw["steps"]] == ["first_submit", "repeat_submit", "read_back"]
    assert first["do"] == replay["do"] == {"request": {
        "method": "POST", "path": ["records"],
        "headers": {"Idempotency-Key": {"from_parameter": "idempotency_key"}},
        "body": {"name": {"from_parameter": "record_name"}},
    }}
    assert first["expect"]["response"] == [
        {"check": "status_equals", "value": 201},
        {"check": "has", "field": "id"},
        {"check": "field_equals", "field": "name", "value": {"from_parameter": "record_name"}},
        {"check": "header_equals", "header": "Cache-Control", "value": "no-store"},
        {"check": "header_absent", "header": "X-Internal-Debug"},
    ]
    assert replay["expect"]["response"] == [
        {"check": "status_equals", "value": 200},
        {"check": "field_equals", "field": "id",
         "value": {"from_step": "first_submit", "response_field": "id"}},
        {"check": "field_equals", "field": "name", "value": {"from_parameter": "record_name"}},
    ]
    assert read["do"] == {"request": {"method": "GET", "path": ["records"],
                                      "query": {"name": {"from_parameter": "record_name"}}}}
    assert read["expect"]["response"] == [
        {"check": "status_equals", "value": 200},
        {"check": "collection_matching_count", "field": "records",
         "matching": {"name": {"from_parameter": "record_name"}}, "count": 1},
        {"check": "collection_matching_count", "field": "records", "matching": {
            "id": {"from_step": "first_submit", "response_field": "id"},
            "name": {"from_parameter": "record_name"}}, "count": 1},
    ]
    scenario = load_scenario(path)
    assert all(step.on_failure == "continue" for step in scenario.steps)
