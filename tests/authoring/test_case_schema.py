"""Guard the optional authoring layer assets.

Each `examples/authoring/cases/*.case.yaml` file must follow the case-template
contract (`id`, `actor`, `intent`, `precondition`, `inputs`, `oracle`). This
keeps human-authored cases machine-checkable rather than free-form prose.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
CASES_DIR = ROOT / "examples" / "authoring" / "cases"

REQUIRED_KEYS = {"id", "actor", "intent", "precondition", "inputs", "oracle"}


def _case_files():
    return sorted(CASES_DIR.glob("*.case.yaml"))


def test_at_least_three_cases_exist():
    assert len(_case_files()) >= 3


def test_every_case_matches_the_template_contract():
    for path in _case_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path.name}: top level must be a mapping"
        assert set(data) == REQUIRED_KEYS, (
            f"{path.name}: keys must be exactly {REQUIRED_KEYS}, got {set(data)}"
        )
        assert isinstance(data["id"], str) and data["id"]
        assert isinstance(data["actor"], str) and data["actor"]
        assert isinstance(data["intent"], str) and data["intent"]
        assert isinstance(data["precondition"], list)
        assert isinstance(data["inputs"], list)
        for item in data["inputs"]:
            assert isinstance(item, dict) and len(item) == 1, (
                f"{path.name}: each inputs entry must be a single-key mapping"
            )
        assert isinstance(data["oracle"], list) and data["oracle"], (
            f"{path.name}: oracle must be a non-empty list"
        )
        for bullet in data["oracle"]:
            assert isinstance(bullet, str) and bullet, (
                f"{path.name}: each oracle bullet must be a non-empty string"
            )


def test_authoring_layer_artifacts_present():
    assert (ROOT / "examples" / "authoring" / "rules.md").is_file()
    assert (ROOT / "examples" / "authoring" / "README.md").is_file()
    assert (ROOT / "examples" / "authoring" / "GENERATION-LOG.md").is_file()
    assert (ROOT / ".claude" / "skills" / "refract-authoring" / "SKILL.md").is_file()
