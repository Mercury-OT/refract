"""Documented response comparison fragments use the implemented declaration."""
from pathlib import Path
import re

import pytest
import yaml

from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import load_scenario
from refracto.ports import NormalizedResponse


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("document", [
    "SCENARIO.md", "docs/tasks/response-field-comparison.md",
])
def test_comparison_fragments_load_and_resolve_in_documented_context(tmp_path, document):
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / document).read_text(), re.S)
    fragments = [yaml.safe_load(block) for block in blocks if "field_not_equals" in block]
    assert fragments
    for index, fragment in enumerate(fragments):
        assert isinstance(fragment, list)
        raw = {
            "schema_version": 1,
            "scenario": "demo.documented_comparisons",
            "users": [],
            "parameters": {"attempted_content": {"title": "Changed", "tags": ["second"]}},
            "steps": [
                {"id": "read_before", "do": {"request": {"method": "GET", "path": ["records"]}},
                 "expect": {"response": [{"check": "has", "field": "content"}]}},
                {"id": "read_after", "do": {"request": {"method": "GET", "path": ["records"]}},
                 "expect": {"response": fragment}},
            ],
        }
        path = tmp_path / f"fragment-{index}.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        scenario = load_scenario(path)
        observed = {"title": "Original", "tags": ["first"]}
        prepared, bound = prepare_step(scenario.steps[1], scenario, {
            "read_before": NormalizedResponse(True, {"content": observed}, 200, None),
        })
        equals, differs = prepared.expect.response
        assert equals.check == "field_equals"
        assert differs.check == "field_not_equals"
        assert equals.params["value"] == observed
        assert differs.params["value"] == raw["parameters"]["attempted_content"]
        assert list(bound.values()) == [observed]
        assert equals.params["value"] is not observed


@pytest.mark.parametrize("relative", [
    "examples/minimal/rejected_update_preserves_content.yaml",
    "examples/documents/scenarios/rejected_update_preserves_content.yaml",
])
def test_published_comparison_examples_load_without_new_schema_version(relative):
    path = ROOT / relative
    assert yaml.safe_load(path.read_text())["schema_version"] == 1
    scenario = load_scenario(path)
    assert len(scenario.steps) == 4
    assert [assertion.check for assertion in scenario.steps[-1].expect.response][-2:] == [
        "field_equals", "field_not_equals",
    ]
