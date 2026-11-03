"""Offline obligations and publication boundaries of the Escape consumer."""
import hashlib
import importlib
import json
from types import SimpleNamespace

import pytest
import yaml

from examples.ui_escape_suggestions.adapter import NoResponse, no_request
from examples.ui_escape_suggestions.run import ROOT, SCENARIO, verify_target_sources
from refracto.declaration.loader import load_scenario


def test_escape_consumer_preserves_approved_three_step_obligations():
    scenario = load_scenario(SCENARIO)
    document = yaml.safe_load(SCENARIO.read_text())
    assert document["schema_version"] == 1
    assert scenario.id == "records.dismiss_search_suggestions"
    assert scenario.users == ["reader"]
    assert document["parameters"] == {"search_text": "report"}
    assert [(step.id, step.action, step.target) for step in scenario.steps] == [
        ("open_search", "open", "records.search_page"),
        ("enter_search_text", "fill", "records.search_input"),
        ("dismiss_suggestions", "press", "records.search_input")]
    assert [step["on_failure"] for step in document["steps"][:2]] == ["stop", "stop"]
    assert scenario.steps[-1].key == "Escape"
    assert all(set(step["expect"]) == {"ui"} for step in document["steps"])
    fill, press = [step["expect"]["ui"] for step in document["steps"][1:]]
    assert [(item["field"], item["value"], item["count"]) for item in fill] == [
        ("value", {"from_parameter": "search_text"}, 1), ("suggestions_visible", True, 1)]
    assert [(item["field"], item["value"], item["count"]) for item in press] == [
        ("suggestions_visible", False, 1), ("value", {"from_parameter": "search_text"}, 1)]


def test_target_sources_were_frozen_before_adapter_integration():
    inventory = json.loads((ROOT / "target-sources.json").read_text())
    assert inventory["freeze_stage"] == "before adapter integration"
    expected = verify_target_sources()
    assert len(expected) == 3
    for name in ("app.py", "search.css", "search.js"):
        source = (ROOT / name).read_bytes()
        assert expected["examples/ui_escape_suggestions/" + name] == hashlib.sha256(source).hexdigest()
        assert b"refracto" not in source and b"scenario.yaml" not in source


def test_page_only_ports_cannot_invent_api_or_response_evidence():
    with pytest.raises(ValueError, match="no API"):
        no_request(object())
    with pytest.raises(ValueError, match="no response"):
        NoResponse().normalize(object())


@pytest.mark.parametrize("status", ["FAILED", "DEGRADED", "EMPTY", "NOT_SELECTED"])
def test_cli_requires_every_native_report_to_pass(monkeypatch, capsys, status):
    runner = importlib.import_module("examples.ui_escape_suggestions.run")
    calls = []

    def fake_run(implementation, projection):
        calls.append((implementation, projection))
        return {"implementation": implementation, "projection": projection,
                "status": status if len(calls) == 1 else "PASSED"}

    monkeypatch.setattr(runner, "run", fake_run)
    assert runner.main() == 1
    assert calls == [(implementation, projection) for implementation in ("listener", "property")
                     for projection in ("frontend", "e2e")]
    assert len(capsys.readouterr().out.splitlines()) == 4


def test_cli_exception_does_not_become_a_native_result_or_leak_message(monkeypatch, capsys):
    runner = importlib.import_module("examples.ui_escape_suggestions.run")

    def broken(*args):
        raise RuntimeError("RAW_EXCEPTION_SENTINEL")

    monkeypatch.setattr(runner, "run", broken)
    assert runner.main() == 1
    output = capsys.readouterr().out
    assert "RAW_EXCEPTION_SENTINEL" not in output
    assert all("status" not in json.loads(line) for line in output.splitlines())


def test_summary_does_not_export_actual_values_or_receipts():
    runner = importlib.import_module("examples.ui_escape_suggestions.run")
    secret = "DO_NOT_EXPORT_ACTUAL_VALUE"
    step = SimpleNamespace(step_id="dismiss_suggestions", status="FAILED", key_press=secret,
                           checks=[SimpleNamespace(point="frontend", check="objects_matching_count", ok=False)],
                           detail=secret)
    report = SimpleNamespace(status="FAILED", domains=[SimpleNamespace(steps=[step])])
    bundle = SimpleNamespace(auth=SimpleNamespace(session_calls=1),
                             ui=SimpleNamespace(opened_contexts=1, closed_contexts=1, evidence=[secret]))
    result = runner.summarize(report, bundle, "listener", "e2e")
    assert result["steps"][0]["key_delivery_observed"] is True
    assert secret not in json.dumps(result)
