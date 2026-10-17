"""Mandatory real Chromium proof of continued actions and explicit stopping."""
from pathlib import Path

import httpx
import pytest
import yaml

from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from refracto.runner import run_scenario
from tests.demo.ui_fixtures import creation_plan


ROOT = Path(__file__).resolve().parents[2]


class ObservedUi(DemoUiDriver):
    def __init__(self, config):
        super().__init__(config)
        self.opens = self.closes = 0
        self.contexts, self.permits, self.evidence = [], [], []

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None):
        self.opens += 1
        return super().open_stepwise(scenario, session, mode=mode, mock_plan=mock_plan)

    def perform_step(self, scenario, step, context, permit):
        self.contexts.append(context)
        self.permits.append(permit)
        result = super().perform_step(scenario, step, context, permit)
        self.evidence.append(result.evidence)
        return result

    def close_stepwise(self, context):
        self.closes += 1
        return super().close_stepwise(context)


class FirstTitleFault(DemoResponseNormalizer):
    """Inject a known observation fault without changing ID, traffic, or checks."""
    def __init__(self):
        self.calls = 0

    def normalize(self, response):
        value = super().normalize(response)
        self.calls += 1
        if self.calls == 1:
            value.fields["name"] = "wrong-observed-title"
        return value


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
@pytest.mark.parametrize("stop", [False, True])
def test_chromium_failure_continues_or_stops_real_actions(demo_server, tmp_path, projection, stop):
    raw = yaml.safe_load((ROOT / f"scenarios/demo_item_{projection}_stepwise.yaml").read_text())
    first = raw["steps"][3]
    first["expect"]["response"].append({"check": "field_equals", "field": "name",
                                         "value": {"from_parameter": "first_name"}})
    if stop:
        first["on_failure"] = "stop"
    path = tmp_path / "browser_continuation.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    ui = ObservedUi(DemoConfig(base_url=demo_server))
    adapters = build_adapters(demo_server, ui=ui)
    adapters.normalizer = FirstTitleFault()
    report = run_scenario(path, adapters, projections=(projection,),
                          mock_plan=creation_plan(("first", "1")) if projection == "frontend" else None)
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["COMPLETED"] * 3 + ["FAILED"] + (
        ["BLOCKED", "BLOCKED"] if stop else ["COMPLETED", "PASSED"])
    assert [(check.point, check.check) for check in domain.checks if not check.ok] == [
        ("response", "field_equals")]
    assert ui.opens == ui.closes == 1
    assert len(ui.permits) == (4 if stop else 6)
    assert len({id(context) for context in ui.contexts}) == 1
    assert [permit.step_id for permit in ui.permits] == [step["id"] for step in raw["steps"][:4 if stop else 6]]
    if stop:
        assert [step.blocked_by for step in domain.steps[4:]] == [["create_first"], ["create_first"]]
    else:
        assert [step.after_failures for step in domain.steps[4:]] == [["create_first"], ["create_first"]]
        assert list(domain.steps[4].resolved_bindings.values()) == ["1"]
    if projection == "frontend":
        assert domain.provider_recordings == []
        assert [item["fixture_id"] for item in domain.mock_consumption] == [
            "initial-list", "create-1", "list-1"] + ([] if stop else ["create-2", "list-2"])
        assert httpx.get(demo_server + "/items").json()["data"]["items"] == []
    else:
        assert [item.step_id for item in domain.provider_recordings] == ["create_first"] + (
            [] if stop else ["create_second"])
        assert [item.json["data"]["itemKey"] for item in domain.provider_recordings] == ["1"] + (
            [] if stop else ["2"])
        assert [item["name"] for item in httpx.get(demo_server + "/items").json()["data"]["items"]] == [
            "first"] + ([] if stop else ["1"])
