"""Real Chromium consumers: mock status and live status are separate evidence."""
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from refracto.runner import run_scenario
from tests.demo.ui_fixtures import creation_plan


ROOT = Path(__file__).resolve().parents[2]


class MisleadingStatusNormalizer(DemoResponseNormalizer):
    """Do not change business success or body, only untrusted status copies."""

    def normalize(self, response):
        normalized = super().normalize(response)
        response.status = 503
        normalized.status = 503
        normalized.raw.status = 503
        normalized.fields["status"] = 503
        return normalized


@pytest.mark.parametrize("projection,check,passed", [
    ("frontend", {"check": "status_equals", "value": 201}, True),
    ("frontend", {"check": "status_in", "values": [202, 204]}, False),
    ("e2e", {"check": "status_in", "values": [200, 202]}, True),
    ("e2e", {"check": "status_equals", "value": 201}, False),
])
def test_chromium_observed_status_is_independent_from_normalizer(
        demo_server, tmp_path, projection, check, passed):
    raw = yaml.safe_load((ROOT / f"scenarios/demo_item_{projection}_stepwise.yaml").read_text())
    for step in raw["steps"]:
        if "response" in step.get("expect", {}):
            step["expect"]["response"].append(check)
    path = tmp_path / "browser_status.yaml"
    # Avoid emitting aliases when one check is reused across two steps.
    class NoAliases(yaml.SafeDumper):
        def ignore_aliases(self, value):
            return True
    path.write_text(yaml.dump(raw, Dumper=NoAliases, sort_keys=False), encoding="utf-8")
    adapters = build_adapters(demo_server, ui=DemoUiDriver(DemoConfig(base_url=demo_server)))
    adapters.normalizer = MisleadingStatusNormalizer()
    plan = [replace(fixture, status=201) if fixture.method == "POST" else fixture
            for fixture in creation_plan(("first", "1"))]
    report = run_scenario(path, adapters, projections=(projection,),
                          mock_plan=plan if projection == "frontend" else None)

    domain = report.domains[0]
    assert report.status == ("PASSED" if passed else "FAILED"), [(s.status, s.detail) for s in domain.steps]
    assert report.degradations() == []
    status_checks = [item for item in domain.checks if item.check == check["check"]]
    assert len(status_checks) == (2 if passed else 1)
    assert all(item.ok is passed for item in status_checks)
    assert all(item.ok for item in domain.checks if item.check == "success")
    if not passed:
        assert [step.status for step in domain.steps[4:]] == ["BLOCKED", "BLOCKED"]
    if projection == "frontend":
        assert not domain.provider_recordings
        assert "create-1" in [item["fixture_id"] for item in domain.mock_consumption]
    else:
        assert [item.status for item in domain.provider_recordings] == [200] * (2 if passed else 1)
