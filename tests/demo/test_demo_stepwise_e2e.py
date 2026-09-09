"""Chromium-gated D6.2 proof for the public demo live UI adapter."""
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright  # noqa: E402

from adapters.demo.config import DemoConfig  # noqa: E402
from adapters.demo.ui import DemoUiDriver  # noqa: E402
from adapters.demo.wiring import build_adapters  # noqa: E402
from refracto.declaration.loader import load_scenario  # noqa: E402
from refracto.runner import run_scenario  # noqa: E402


SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "demo_item_e2e_stepwise.yaml"
)


@pytest.fixture(scope="module")
def _chromium_available():
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except Exception as exc:
        pytest.skip(f"Chromium not available for Playwright: {exc}")


class ObservedDemoUiDriver(DemoUiDriver):
    def __init__(self, config):
        super().__init__(config)
        self.open_calls = 0
        self.close_calls = 0
        self.contexts = []
        self.permits = []
        self.results = []

    def open_stepwise(self, scenario, session, *, mode):
        self.open_calls += 1
        context = super().open_stepwise(scenario, session, mode=mode)
        self.contexts.append(context)
        return context

    def perform_step(self, scenario, step, context, permit):
        self.contexts.append(context)
        self.permits.append(permit)
        result = super().perform_step(scenario, step, context, permit)
        self.results.append(result)
        return result

    def close_stepwise(self, context):
        self.close_calls += 1
        return super().close_stepwise(context)


def test_demo_live_two_step_e2e_is_strictly_correlated(
    _chromium_available,
    demo_server,
):
    scenario = load_scenario(str(SCENARIO))
    driver = ObservedDemoUiDriver(DemoConfig(base_url=demo_server))
    adapters = build_adapters(
        demo_server,
        ui=driver,
        scenario=scenario,
    )

    report = run_scenario(str(SCENARIO), adapters, projections=("e2e",))
    domain = report.domains[0]

    assert report.status == "PASSED"
    assert report.degradations() == []
    assert [step.status for step in domain.steps] == ["PASSED", "PASSED"]
    assert all(
        {check.point for check in step.checks}
        == {"frontend", "request", "response", "backend_state"}
        for step in domain.steps
    )

    assert driver.open_calls == driver.close_calls == 1
    assert len(driver.permits) == 2
    assert driver.contexts[0] is driver.contexts[1] is driver.contexts[2]
    assert all(permit.mode == "live" for permit in driver.permits)
    assert all(permit.mock_response is None for permit in driver.permits)
    assert len({permit.action_id for permit in driver.permits}) == 2
    assert len({permit.trace_id for permit in driver.permits}) == 2

    assert domain.steps[1].resolved_bindings == {"itemKey": "1"}
    assert driver.permits[1].resolved_bindings == {"itemKey": "1"}
    assert len(domain.provider_recordings) == 2
    assert [recording.step_id for recording in domain.provider_recordings] == [
        "create_first",
        "create_bound",
    ]
    assert [recording.request.method for recording in domain.provider_recordings] == [
        "POST",
        "POST",
    ]
    assert [recording.request.path for recording in domain.provider_recordings] == [
        "items",
        "items",
    ]
    assert [recording.actual_path for recording in domain.provider_recordings] == [
        "/items",
        "/items",
    ]
    assert [recording.json["data"]["itemKey"] for recording in domain.provider_recordings] == [
        "1",
        "2",
    ]
    assert [recording.trace_id for recording in domain.provider_recordings] == [
        permit.trace_id for permit in driver.permits
    ]

    diagnostics = [
        request
        for result in driver.results
        for request in result.evidence.diagnostic_outgoing
    ]
    assert diagnostics
    assert all(request.method == "GET" for request in diagnostics)
    assert all(request.path == "items" for request in diagnostics)
    assert not any(recording.request.method == "GET" for recording in domain.provider_recordings)
