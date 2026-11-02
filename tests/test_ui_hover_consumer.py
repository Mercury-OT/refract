"""Offline checks for the neutral hover consumer and its publication boundary."""
import hashlib
import importlib
import json
from types import SimpleNamespace

import pytest
import yaml

from examples.ui_hover_menu.adapter import Normalizer
from examples.ui_hover_menu.run import ROOT, SCENARIO, verify_target_sources
from refracto.declaration.loader import load_scenario
from refracto.ports import RecordedResponse, RequestSpec


def test_hover_consumer_uses_approved_obligations_without_hidden_operations():
    scenario = load_scenario(SCENARIO)
    document = yaml.safe_load(SCENARIO.read_text())
    assert document["schema_version"] == 1
    assert scenario.users == ["reader"]
    assert [(step.id, step.action, step.target) for step in scenario.steps] == [
        ("open_page", "open", "records.page"),
        ("reveal_menu", "hover", "records.menu_trigger"),
        ("browse_archived", "click", "records.archived_menu_item")]
    assert [step["on_failure"] for step in document["steps"][:2]] == ["stop", "stop"]
    assert [step["expect"]["ui"][0]["count"] for step in document["steps"][:2]] == [0, 1]
    assert document["steps"][1]["expect"].keys() == {"ui"}
    final = document["steps"][-1]["expect"]
    assert final["request"] == {"method": "GET", "path": ["records"], "query": {"status": "archived"}}
    assert [check["check"] for check in final["response"]] == [
        "status_equals", "success", "collection_length", "collection_matching_count"]
    assert [check["count"] for check in final["ui"]] == [1, 0]


def test_target_is_frozen_before_adapter_integration_and_independent_of_declarations():
    inventory = json.loads((ROOT / "target-sources.json").read_text())
    assert inventory["freeze_stage"] == "before adapter integration"
    expected = verify_target_sources()
    assert len(expected) == 3
    for name in ("app.py", "menu.js", "menu.css"):
        source = (ROOT / name).read_bytes()
        assert expected["examples/ui_hover_menu/" + name] == hashlib.sha256(source).hexdigest()
        assert b"refracto" not in source and b"scenario.yaml" not in source


@pytest.mark.parametrize("payload", [
    {"success": False, "data": {"records": []}},
    {"success": True, "data": {"records": [{"name": "Wrong record"}]}},
])
def test_normalizer_preserves_wrong_or_unsuccessful_actual_response(payload):
    response = RecordedResponse(200, {}, payload, "", None, RequestSpec("GET", "records"))
    result = Normalizer().normalize(response)
    assert result.succeeded is payload["success"]
    assert result.fields == payload["data"]
    result.fields["records"].append({"name": "changed copy"})
    assert result.fields != payload["data"]


@pytest.mark.parametrize("payload", [None, [], {"success": 1, "data": {}}, {"success": True}])
def test_normalizer_does_not_invent_missing_evidence(payload):
    response = RecordedResponse(200, {}, payload, "", None, RequestSpec("GET", "records"))
    with pytest.raises(ValueError):
        Normalizer().normalize(response)


@pytest.mark.parametrize("status", ["FAILED", "DEGRADED", "EMPTY", "NOT_SELECTED"])
def test_cli_requires_all_four_native_runs_to_pass(monkeypatch, capsys, status):
    runner = importlib.import_module("examples.ui_hover_menu.run")
    calls = []

    def fake_run(implementation, projection):
        calls.append((implementation, projection))
        return {"implementation": implementation, "projection": projection,
                "status": status if len(calls) == 1 else "PASSED"}

    monkeypatch.setattr(runner, "run", fake_run)
    assert runner.main() == 1
    assert calls == [(implementation, projection) for implementation in ("css", "javascript")
                     for projection in ("frontend", "e2e")]
    assert len(capsys.readouterr().out.splitlines()) == 4


def test_cli_exception_is_not_a_native_result_and_does_not_echo_private_values(monkeypatch, capsys):
    runner = importlib.import_module("examples.ui_hover_menu.run")

    def broken(*args):
        raise RuntimeError("RAW_EXCEPTION_SENTINEL")

    monkeypatch.setattr(runner, "run", broken)
    assert runner.main() == 1
    output = capsys.readouterr().out
    assert "RAW_EXCEPTION_SENTINEL" not in output
    assert all("status" not in json.loads(line) for line in output.splitlines())


def test_summary_excludes_actual_values_and_raw_traffic():
    runner = importlib.import_module("examples.ui_hover_menu.run")
    secret = "DO_NOT_PUBLISH_ACTUAL_VALUE"
    step = SimpleNamespace(step_id="reveal_menu", status="FAILED", hover=None,
                           checks=[SimpleNamespace(point="frontend", check="objects_matching_count", ok=False)],
                           detail=secret)
    report = SimpleNamespace(status="FAILED", domains=[SimpleNamespace(steps=[step], provider_recordings=[secret])])
    bundle = SimpleNamespace(auth=SimpleNamespace(session_calls=1),
                             ui=SimpleNamespace(opened_contexts=1, closed_contexts=1, evidence=[secret]))
    result = runner.summarize(report, bundle, "css", "e2e")
    assert result["status"] == "FAILED"
    assert result["steps"][0]["checks"][0]["ok"] is False
    assert secret not in json.dumps(result)
