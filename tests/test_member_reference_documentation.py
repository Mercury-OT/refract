"""Execute documented value fragments in their declared reference context."""
from pathlib import Path
import re

import pytest
import yaml

from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import load_scenario
from refracto.ports import NormalizedResponse


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = [
    "examples/minimal/create_locate_update_read.yaml",
    "examples/minimal/dictionary_record_reference.yaml",
    "examples/documents/scenarios/locate_update_read.yaml",
    "examples/documents/scenarios/dictionary_document_reference.yaml",
]


def documented_references(document):
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / document).read_text(), re.S)
    references = []
    for block in blocks:
        if "member_field:" not in block and "key: id" not in block:
            continue
        # The task explicitly presents three separate reference values separated
        # by blank lines, not a single YAML document or Scenario.
        values = block.split("\n\n") if document.startswith("docs/tasks/") else [block]
        for value in values:
            reference = yaml.safe_load(value)
            if isinstance(reference, dict) and "from_step" in reference:
                references.append(reference)
    return references


@pytest.mark.parametrize("document", ["SCENARIO.md", "docs/tasks/response-member-references.md"])
def test_reference_fragments_load_and_read_actual_data(tmp_path, document):
    references = documented_references(document)
    assert any("key" in reference for reference in references)
    assert any("member_field" in reference for reference in references)
    for index, reference in enumerate(references):
        raw = {
            "schema_version": 1, "scenario": "demo.documented_member_reference",
            "users": [], "parameters": {"record_code": "B"},
            "steps": [
                {"id": "create", "do": {"request": {"method": "POST", "path": ["records"]}}},
                {"id": "locate", "do": {"request": {"method": "GET", "path": ["records"]}}},
                {"id": "consume", "do": {"request": {"method": "POST", "path": ["selected"],
                    "body": {"selected": reference}}},
                 "expect": {"response": [{"check": "success"}]}},
            ],
        }
        path = tmp_path / f"documented-value-{index}.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        scenario = load_scenario(path)
        record = {"id": 22, "code": "B", "name": "Dictionary record"}
        rows = [{"id": 19, "code": "other"}, {"id": 23, "code": "B"}]
        prepared, bound = prepare_step(scenario.steps[-1], scenario, {
            "create": NormalizedResponse(True, {"record": record}, 201, None),
            "locate": NormalizedResponse(True, {"records": rows}, 200, None),
        })
        expected = 22 if "key" in reference else 23 if "matching" in reference else record
        assert prepared.request.body == {"selected": expected}
        assert list(bound.values()) == [expected]
        assert record == {"id": 22, "code": "B", "name": "Dictionary record"}
        assert rows == [{"id": 19, "code": "other"}, {"id": 23, "code": "B"}]


@pytest.mark.parametrize("relative", EXAMPLES)
def test_published_member_examples_keep_schema_one_and_use_selection(relative):
    path = ROOT / relative
    raw = yaml.safe_load(path.read_text())
    assert raw["schema_version"] == 1
    scenario = load_scenario(path)
    assert scenario.steps
    selectors = [binding for step in scenario.steps for binding in step.bind
                 if binding.key is not None or binding.matching is not None]
    assert selectors
    if "dictionary" in relative:
        assert all(binding.key is not None and binding.matching is None for binding in selectors)
    else:
        assert all(binding.matching is not None and binding.key is None for binding in selectors)
