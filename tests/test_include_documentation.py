"""Executable companions for the include specification and published examples."""
import hashlib
import json
from pathlib import Path
import re

import pytest

from refracto.declaration.loader import load_scenario


ROOT = Path(__file__).resolve().parents[1]


def test_specification_scenarios_load_with_their_actual_pinned_companion(tmp_path):
    text = (ROOT / "docs/tasks/scenario-named-results.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)
    assert len(blocks) == 2
    child_bytes = blocks[0].encode("utf-8")
    shared = tmp_path / "shared"
    shared.mkdir()
    child = shared / "create_item.yaml"
    child.write_bytes(child_bytes)
    parent = tmp_path / "create_update_read.yaml"
    parent.write_text(blocks[1], encoding="utf-8")
    digest = hashlib.sha256(child_bytes).hexdigest()
    parent.with_suffix(".includes.json").write_text(json.dumps({
        "manifest_version": 1,
        "scenarios": {"shared.create_item": {
            "path": "shared/create_item.yaml", "sha256": digest,
        }},
    }), encoding="utf-8")

    assert load_scenario(child).id == "shared.create_item"
    scenario = load_scenario(parent)
    assert scenario.id == "demo.create_update_read"
    assert [step.id for step in scenario.steps] == ["create/create_request", "update", "read"]
    assert scenario.source_lookup["create/create_request"] == {
        "scenario_id": "shared.create_item", "step_id": "create_request",
        "include_step_id": "create", "sha256": digest,
    }
    assert scenario.steps[-1].bind[0].from_step == "create/create_request"
    assert scenario.steps[-1].bind[0].field == "itemId"


@pytest.mark.parametrize("name", ["demo_include_items", "demo_include_items_ui"])
def test_published_examples_have_exact_real_companion_pins(name):
    parent = ROOT / "scenarios" / f"{name}.yaml"
    manifest = json.loads(parent.with_suffix(".includes.json").read_text())
    assert set(manifest) == {"manifest_version", "scenarios"}
    for scenario_id, dependency in manifest["scenarios"].items():
        child = parent.parent / dependency["path"]
        assert load_scenario(child).id == scenario_id
        assert dependency["sha256"] == hashlib.sha256(child.read_bytes()).hexdigest()
    expanded = load_scenario(parent)
    assert all("/" in step.id or step.id in {"update", "read"}
               for step in expanded.steps)
    assert expanded.actor == "user"


def test_public_include_documentation_preserves_review_and_evidence_limits():
    contract = (ROOT / "SCENARIO.md").read_text(encoding="utf-8")
    assert "## Including a pinned, reviewed Scenario" in contract
    assert "A hash proves content agreement, not human approval." in contract
    assert "Every include executes anew" in contract
    assert "It never\ncontains runtime response values." in contract
    assert 'report.status == "PASSED"' in (
        ROOT / "docs/tasks/scenario-include.md").read_text(encoding="utf-8")
