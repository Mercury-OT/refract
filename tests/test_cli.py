"""CLI tests for `refracto validate`."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALID = ROOT / "scenarios" / "demo_item_create.yaml"


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "refracto", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_validate_valid_scenario_exits_zero_with_summary():
    r = _run("validate", str(VALID))
    assert r.returncode == 0, r.stderr
    assert "demo.item_create" in r.stdout
    assert "OK" in r.stdout


def test_validate_invalid_scenario_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: bad.x\n"
        "grid: {level: smoke, module: demo}\n"
        "actor: user\n"
        "precondition: []\n"
        "inputs: []\n"
        "intent: x\n"
        "expect:\n"
        "  response:\n"
        "    - {check: no_such_check}\n",
        encoding="utf-8",
    )
    r = _run("validate", str(bad))
    assert r.returncode == 2
    assert "no_such_check" in r.stderr or "invalid" in r.stderr.lower()


def test_no_args_shows_usage_and_exits_nonzero():
    r = _run()
    assert r.returncode != 0
    assert "usage" in (r.stdout + r.stderr).lower()


def test_validate_malformed_yaml_exits_two(tmp_path):
    bad = tmp_path / "malformed.yaml"
    bad.write_text("scenario: bad\ngrid: [unclosed\n", encoding="utf-8")
    r = _run("validate", str(bad))
    assert r.returncode == 2, r.stderr
    assert "INVALID" in r.stderr
    assert "Traceback" not in r.stderr


def test_validate_non_mapping_top_level_exits_two(tmp_path):
    bad = tmp_path / "notmap.yaml"
    bad.write_text("3\n", encoding="utf-8")
    r = _run("validate", str(bad))
    assert r.returncode == 2, r.stderr
    assert "INVALID" in r.stderr
    assert "Traceback" not in r.stderr
