"""Definition of Done: the SAME scenario declaration, loaded from a real YAML file
(scenarios/demo_item_create.yaml, not an inline-built Scenario like the other demo
tests), runs through all four projections (backend / frontend / e2e / contract) in a
SINGLE refracto.runner.run_scenario(...) call and comes back fully green — the whole
framework end to end from one declaration. The demo app has no external/VPN
dependency, so this test is gated only on Chromium availability (frontend/e2e drive a
real Chromium via adapters/demo/ui.py's DemoUiDriver).

Chromium gating: mirrors test_demo_ui.py's `_chromium_available` fixture exactly
(module-scoped, tries a real chromium.launch()/close(), skips cleanly if that raises).
Since backend/frontend/e2e/contract all run from one run_scenario call here, there is
no clean way to run "just the non-UI projections" without re-implementing
run_scenario's internals inline — so this test skips as a whole when Chromium is
unavailable, and otherwise runs green.
"""
import pytest
from playwright.sync_api import sync_playwright

from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from adapters.demo.config import DemoConfig
from refracto import runner


@pytest.fixture(scope="module")
def _chromium_available():
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
    except Exception as e:
        pytest.skip(f"Chromium not available for Playwright: {e}")


def test_demo_item_create_all_four_projections_green(_chromium_available, demo_server):
    config = DemoConfig(base_url=demo_server)
    adapters = build_adapters(demo_server, ui=DemoUiDriver(config))

    rep = runner.run_scenario("scenarios/demo_item_create.yaml", adapters)

    assert rep.passed is True
    assert rep.localize() == []  # empty localize() on a passing run is itself part of the DoD signal
    assert {d.projection for d in rep.domains} == {"backend", "frontend", "e2e", "contract"}

    # Per-projection breakdown so a future regression in one projection cannot hide
    # behind the aggregate `rep.passed`.
    by_projection = {d.projection: d for d in rep.domains}
    for name in ("backend", "frontend", "e2e", "contract"):
        d = by_projection[name]
        failures = [c for c in d.checks if not c.ok]
        assert d.passed, f"{name} projection failed: {failures}"

    backend = by_projection["backend"]
    assert any(c.check == "success" and c.ok for c in backend.checks)
    assert any(c.check == "has" and c.ok for c in backend.checks)
    assert any(c.check == "span_exists" and c.ok for c in backend.checks)
    assert any(c.check == "span_attr" and c.ok for c in backend.checks)

    frontend = by_projection["frontend"]
    assert any(c.check == "visible" and c.ok for c in frontend.checks)
    assert any(c.check == "count_gt" and c.ok for c in frontend.checks)

    e2e = by_projection["e2e"]
    assert any(c.point == "frontend" and c.ok for c in e2e.checks)
    assert any(c.point == "request" and c.ok for c in e2e.checks)
    assert any(c.point == "response" and c.ok for c in e2e.checks)
    assert any(c.point == "backend_state" and c.check == "span_exists" and c.ok for c in e2e.checks)
    assert any(c.point == "backend_state" and c.check == "span_attr" and c.ok for c in e2e.checks)

    contract = by_projection["contract"]
    assert any(c.check == "diff" and c.ok for c in contract.checks)
