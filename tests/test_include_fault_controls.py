"""Reachable fixed faults and identical flat/include backend observations."""
import hashlib
import json
from pathlib import Path

import pytest

from tests.include_fault_controls import FAULTS
from tests.named_results_fault_controls import run_control


BASELINE_PATH = Path(__file__).with_name("include_fault_controls_baseline.json")
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _baseline_result(fault, inject):
    return next(result for result in BASELINE["results"]
                if result["fault"] == fault and result["injected"] is inject)


def _comparable(result):
    # JSON canonicalization changes tuples to arrays, not observed value types.
    output = json.loads(json.dumps(result))
    output.pop("form")
    return output


def test_fault_assets_still_match_the_preimplementation_freeze():
    harness = Path(__file__).with_name("include_fault_controls.py")
    assert hashlib.sha256(harness.read_bytes()).hexdigest() == BASELINE["harness_sha256"]
    assert BASELINE["baseline_commit"] == "9bebfa7559bfc22e7121bc31b1945e803676a1f8"
    assert BASELINE["exit_code"] == 0
    assert BASELINE["detected"] == BASELINE["valid_executed"] == 3
    assert BASELINE["exclusions"] == []
    assert len(BASELINE["results"]) == 6
    for filename, expected_hash in {
        "include_fault_controls.py": "caf1932c715316b95859c2554e5370f1a00d3f11b84a5505cc31e3f800739733",
        "include_fault_controls_baseline.json": "3057742b7d89587e1ad5a64c38a2b0a8a757a1539ad76825427f5449bb1c9d36",
        "include_fault_controls_candidate.json": "3e448db12df795d66bf5994e5f9b648bc7d5d4085cf05e46a8c80d7e878ec18b",
    }.items():
        assert hashlib.sha256(Path(__file__).with_name(filename).read_bytes()).hexdigest() == expected_hash


@pytest.mark.parametrize("fault", FAULTS)
@pytest.mark.parametrize("form", ("flat", "include"))
@pytest.mark.parametrize("inject", (False, True))
def test_fixed_backend_fault_detection_matches_historical_baseline(fault, form, inject):
    result = run_control(fault, form, inject=inject)
    baseline = _comparable(_baseline_result(fault, inject))
    current = _comparable(result)
    # The frozen measurements retain their original fail-fast behavior. Compare
    # the actual injected fault, detecting check and observed prefix, not old
    # stopping behavior that this task intentionally changes.
    for field in ("fault", "injected", "classification", "status", "fault_reached",
                  "failures", "degradations"):
        assert current[field] == baseline[field]
    for field in ("requests", "observed"):
        assert current[field][:len(baseline[field])] == baseline[field]
    assert _comparable(run_control(fault, "include" if form == "flat" else "flat", inject=inject)) == current
    assert result["degradations"] == []
    if inject:
        assert result["classification"] == "detected"
        assert result["fault_reached"] == 1
        assert result["steps"][-1] == ("after", "PASSED")
        assert len(result["failures"]) == 1
        assert len(result["requests"]) == (2 if fault == "accepted_rejection" else 3)
    else:
        assert result["classification"] == "passing_neighbor"
        assert result["fault_reached"] == 0
        assert result["failures"] == []


@pytest.mark.parametrize("form", ("flat", "include"))
def test_wrong_object_fault_reaches_the_real_response_derived_request(form):
    result = run_control("wrong_object_read", form)
    assert result["classification"] == "detected"
    assert result["observed"][0]["data"]["id"] == "record-1"
    assert result["requests"][1][:2] == ("GET", "records/record-1")
    assert result["observed"][1]["data"] == {"id": "record-2", "name": "target-name"}
    assert result["failures"] == [{"step": "read", "check": "field_equals"}]


@pytest.mark.parametrize("form", ("flat", "include"))
def test_collection_fault_changes_only_the_target_not_the_unrelated_member(form):
    result = run_control("changed_collection_target", form)
    assert result["classification"] == "detected"
    assert result["observed"][1]["data"]["records"] == [
        {"id": "unrelated", "name": "other-name"},
        {"id": "record-1", "name": "changed-name"},
    ]


def test_setup_errors_are_invalid_controls_not_detections(monkeypatch):
    from tests import include_fault_controls

    def fail_setup(*args, **kwargs):
        raise ImportError("deliberate setup failure")

    monkeypatch.setattr(include_fault_controls, "run_scenario", fail_setup)
    result = run_control("accepted_rejection")
    assert result["classification"] == "invalid_control"
    assert result["fault_reached"] == 0
    assert result["requests"] == []
    assert result["error_type"] == "ImportError"


def test_named_results_setup_errors_are_not_counted_as_detected_faults(monkeypatch):
    from tests import named_results_fault_controls

    def fail_setup(*args, **kwargs):
        raise ImportError("deliberate current-declaration setup failure")

    monkeypatch.setattr(named_results_fault_controls, "run_scenario", fail_setup)
    result = run_control("wrong_object_read", "include")
    assert result["classification"] == "invalid_control"
    assert result["fault_reached"] == 0
    assert result["requests"] == []
    assert result["error_type"] == "ImportError"


def test_current_fault_declarations_expose_only_the_named_result_interface():
    from tests import named_results_fault_controls

    for fault in ("changed_collection_target", "wrong_object_read"):
        parent, child, _ = named_results_fault_controls.FIXTURES[fault]
        assert "from_step: setup, result: record_id" in parent
        assert "from_step: setup/" not in parent
        assert "results:\n  record_id:\n    from_step: create\n    response_field: id" in child
