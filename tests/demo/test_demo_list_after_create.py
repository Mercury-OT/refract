"""`demo_item_list_after_create.yaml` is a frontend-only scenario. It verifies rendered UI state and emitted request shape without any backend-state assertions, and runs in both the frontend and e2e projections. If Chromium is unavailable, the test is skipped just like the other Playwright-gated demo tests."""
import pytest

pytest.importorskip("playwright")  # skip cleanly (not abort collection) without the demo extra

from playwright.sync_api import sync_playwright  # noqa: E402

from adapters.demo.config import DemoConfig  # noqa: E402
from adapters.demo.ui import DemoUiDriver  # noqa: E402
from adapters.demo.wiring import build_adapters  # noqa: E402
from refracto import runner  # noqa: E402


@pytest.fixture(scope="module")
def _chromium_available():
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
    except Exception as e:
        pytest.skip(f"Chromium not available for Playwright: {e}")


def test_demo_item_list_after_create_frontend_domain_green(_chromium_available, demo_server):
    config = DemoConfig(base_url=demo_server)
    adapters = build_adapters(demo_server, ui=DemoUiDriver(config))
    rep = runner.run_scenario("scenarios/demo_item_list_after_create.yaml", adapters,
                              projections=("frontend", "e2e"))
    assert rep.passed is True, rep.localize()
    by_projection = {d.projection: d for d in rep.domains}
    assert set(by_projection) == {"frontend", "e2e"}

    fe = by_projection["frontend"]
    assert any(c.check == "visible" and c.ok for c in fe.checks)
    assert any(c.check == "count_gt" and c.ok for c in fe.checks)
    assert any(c.point == "request" and c.ok for c in fe.checks)

    e2e = by_projection["e2e"]
    assert any(c.point == "frontend" and c.ok for c in e2e.checks)
    assert any(c.point == "request" and c.ok for c in e2e.checks)
    # Frontend-only scenario: no backend_state is declared, so nothing should be skipped
    assert e2e.skipped == []
    assert all(not s.skipped for s in e2e.steps)
