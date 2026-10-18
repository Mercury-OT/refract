"""Protect the bounded measurement inventory and its honest classification."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from tests import stabilization_controls as controls


ROOT = Path(__file__).resolve().parents[1]


def measurement_module():
    spec = importlib.util.spec_from_file_location("measure_stabilization", ROOT / "scripts/measure_stabilization.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_stabilization_manifest_has_no_silent_omissions_or_source_drift():
    module = measurement_module()
    manifest = module.verify_manifest()
    assert {row["lane"] for row in manifest["current_rows"]} == {"assertion", "guard", "engine"}


@pytest.mark.parametrize("row", [row for row in controls.ROWS if not row.startswith("C")])
def test_current_stabilization_controls_match_the_frozen_detector(row):
    neighbor = controls.observe(row, False)
    injected = controls.observe(row, True)
    assert neighbor["status"] == "PASSED" and neighbor["degradation_count"] == 0
    classification = controls.classify(row, injected, neighbor)
    if row.startswith("G"):
        assert classification == "guard_conformant"  # Existing mechanical safety promises.
    else:
        assert classification in {"detected", "missed"}  # No target detection percentage.


@pytest.mark.parametrize("row", ["C01", "C02"])
def test_unmutated_engine_preserves_continuation_and_failed_aggregate(row):
    controls.engine_assertion(controls.observe(row, True), row)


def test_setup_failure_and_unreached_fault_never_count_as_detection():
    neighbor = {"status": "ERROR", "degradation_count": 0}
    assert controls.classify("F01", {}, neighbor) == "invalid_control"
    expected = controls.neighbor_expectation("F01")
    neighbor = {**expected, "degradation_count": 0,
                "steps": [{"id": step, "status": status} for step, status in expected["steps"]]}
    assert controls.classify("F01", {"reach_count": 0}, neighbor) == "not_reached"
    assert controls.classify("F01", {"reach_count": 0, "steps": [{"status": "ERROR"}]}, neighbor) == "invalid_control"
    assert controls.classify("F01", {"reach_count": 1, "steps": [{"status": "ERROR"}]}, neighbor) == "invalid_control"
    neighbor["action_count"] -= 1
    assert controls.classify("F01", {}, neighbor) == "invalid_control"


def test_saved_results_match_every_planned_execution_and_do_not_mix_lanes():
    fixture = ROOT / "tests/fixtures/stabilization"
    result_path = fixture / "results-r2.json"
    if not result_path.exists():
        pytest.fail("approved measurement evidence has not been generated")
    results = json.loads(result_path.read_text())
    module = measurement_module()
    module.audit_results(results, module.verify_manifest())
    records = results["records"]
    keys = [(r["subject"], r["panel"], r["row"], r["form"], r["injected"]) for r in records]
    assert len(keys) == len(set(keys)) == 52
    assert len([r for r in records if r["panel"] == "historical"]) == 24
    for row in controls.ROWS:
        selected = [r for r in records if r["panel"] != "historical" and r["row"] == row]
        assert len(selected) == 2
        assert all(r["projection"] == "backend" for r in selected)
        assert all(r["result"]["classification"] not in {"invalid_control", "not_reached"} for r in selected)


@pytest.mark.parametrize("panel", ["historical", "current"])
def test_nonzero_worker_exit_is_invalid_even_with_passing_structured_output(panel):
    module = measurement_module()
    record = {"panel": panel, "exit_code": 2, "result": {"classification": "detected", "status": "PASSED"}}
    assert module.outcome(record, None, controls) == "invalid_control"


def test_exact_mutant_bytes_reject_an_unrelated_edit_in_the_same_file():
    module = measurement_module()
    original = (ROOT / "refracto/report.py").read_bytes()
    expected = module.engine_bytes(original, "C02")
    module.verify_engine_source(original, expected, "C02")
    with pytest.raises(ValueError, match="exact frozen mutation"):
        module.verify_engine_source(original, expected + b"\n# unrelated change\n", "C02")
    assert b"if sts and sts[-1] == PASSED:" in expected


def test_structured_results_reject_changed_hash_missing_duplicate_and_extra_units():
    module = measurement_module()
    manifest = json.loads(module.MANIFEST.read_text())
    bad = {"manifest_sha256": "0" * 64}
    with pytest.raises(ValueError, match="different manifest"):
        module.audit_results(bad, manifest)
    keys = module.expected_keys(manifest)
    records = [dict(zip(("subject", "panel", "row", "form", "injected"), key)) for key in keys]
    for variant in (records[:-1], records + [deepcopy(records[0])], records[:-1] + [
            {**records[-1], "row": "not-in-the-plan"}]):
        with pytest.raises(ValueError, match="execution keys"):
            module.recompute(variant, manifest)


def test_first_measurement_evidence_remains_archived_byte_for_byte():
    module = measurement_module()
    for name, expected in module.ARCHIVED_EVIDENCE.items():
        assert module.digest((module.FIXTURES / name).read_bytes()) == expected
    old = json.loads((module.FIXTURES / "results.json").read_text())
    assert old["manifest_sha256"] == module.ARCHIVED_EVIDENCE["manifest.json"]
