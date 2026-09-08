"""Browser-gated proof that the demo adapter implements D6.1 stepwise frontend."""
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright  # noqa: E402

from adapters.demo.config import DemoConfig  # noqa: E402
from adapters.demo.ui import DemoUiDriver  # noqa: E402
from adapters.demo.wiring import build_adapters  # noqa: E402
from refracto.declaration.loader import load_scenario  # noqa: E402
from refracto.runner import run_scenario  # noqa: E402


SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "demo_item_frontend_stepwise.yaml"


@pytest.fixture(scope="module")
def _chromium_available():
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except Exception as exc:
        pytest.skip(f"Chromium not available for Playwright: {exc}")


def test_demo_stepwise_frontend_two_step_flow(_chromium_available, demo_server):
    scenario = load_scenario(str(SCENARIO))
    adapters = build_adapters(
        demo_server,
        ui=DemoUiDriver(DemoConfig(base_url=demo_server)),
        scenario=scenario,
    )
    report = run_scenario(str(SCENARIO), adapters, projections=("frontend",))
    result = report.domains[0]

    assert report.status == "PASSED"
    assert report.degradations() == []
    assert [step.status for step in result.steps] == ["PASSED", "PASSED"]
    assert result.steps[1].resolved_bindings == {"itemId": "<stub:itemId>"}
    assert all(check.ok for check in result.checks)
