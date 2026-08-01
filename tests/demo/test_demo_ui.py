"""Tests for adapters/demo/ui.py's Playwright UiDriver.

Two scenarios, both driving the SAME real demo app (tests/demo/conftest.py's
demo_server fixture starts a real uvicorn subprocess):

1. Frontend-only projection (refracto/projection/frontend.py) with mock=<built from the
   declaration's consumer contract>. Playwright intercepts POST /items and returns the
   mock; GET /items (not declared, but the page's own JS calls it right after posting
   to re-render the list) is answered with a synthesized single-item list so item-row
   actually renders — see DemoUiDriver._mock_overlay's docstring/comment for why.

2. Single-drive e2e projection (refracto/projection/e2e.py) with mock=None: the driver
   drives the SAME real backend once, injecting a traceparent into the declared POST
   /items request and capturing its response, so frontend/request/response/backend_state
   all come from that one execution (no double-drive). This is exactly why the demo
   app's page JS sends non-empty rows (rows: [1, 2, 3]): backend_state declares
   span_attr item.create row_count > 0, and only a real click that sends non-empty rows
   satisfies that against the real StateProbe.

Playwright/Chromium gating: these demo UI tests need no VPN or real product (just the
local demo_server subprocess), only a real browser binary. So they gate on browser
presence: a fixture that tries a real chromium.launch()/close() and skips the test
cleanly if that raises. With Chromium installed they run for real (not just skip).
"""
import pytest
from playwright.sync_api import sync_playwright

from refracto.declaration.model import (
    Assertion, Expect, Grid, Input, RequestTemplate, Scenario, Step,
)
from refracto.projection import e2e as e2e_proj
from refracto.projection import frontend as frontend_proj
from refracto.recorder import InMemoryRecorder

from adapters.demo.auth import DemoAuthenticator
from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.state import DemoStateProbe
from adapters.demo.ui import DemoUiDriver


@pytest.fixture(scope="module")
def _chromium_available():
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
    except Exception as e:
        pytest.skip(f"Chromium not available for Playwright: {e}")


def _frontend_scenario() -> Scenario:
    return Scenario(
        id="demo_item_create_frontend_inline",
        grid=Grid(level="smoke", module="demo"),
        actor="tester",
        precondition=[],
        inputs=[],
        intent="create an item via the UI and see it rendered",
        steps=[Step(
            id="main",
            request=RequestTemplate(method="POST", path="items"),
            expect=Expect(
                frontend=[
                    Assertion(check="visible", params={"anchor": "item_row"}),
                    Assertion(check="count_gt", params={"anchor": "item_row", "n": 0}),
                ],
            ),
        )],
    )


def _e2e_scenario() -> Scenario:
    return Scenario(
        id="demo_item_create_e2e_inline",
        grid=Grid(level="smoke", module="demo"),
        actor="tester",
        precondition=[],
        inputs=[Input(kind="rows", value=3)],
        intent="create an item via the UI and observe its item.create span, single drive",
        steps=[Step(
            id="main",
            request=RequestTemplate(method="POST", path="items"),
            expect=Expect(
                frontend=[
                    Assertion(check="visible", params={"anchor": "item_row"}),
                    Assertion(check="count_gt", params={"anchor": "item_row", "n": 0}),
                ],
                response=[Assertion(check="success")],
                backend_state=[
                    Assertion(check="span_exists", params={"span": "item.create"}),
                    Assertion(check="span_attr",
                             params={"span": "item.create", "attr": "row_count", "op": ">", "value": 0}),
                ],
            ),
        )],
    )


def test_frontend_projection_green_mock_mode(_chromium_available, demo_server):
    config = DemoConfig(base_url=demo_server)
    driver = DemoUiDriver(config)

    res = frontend_proj.run(_frontend_scenario(), ui=driver, auth=DemoAuthenticator(),
                            normalizer=DemoResponseNormalizer())

    failures = [c for c in res.checks if not c.ok]
    assert res.passed, failures
    assert any(c.check == "visible" and c.ok for c in res.checks)
    assert any(c.check == "count_gt" and c.ok for c in res.checks)
    assert any(c.check == "request" and c.ok for c in res.checks)


def test_e2e_projection_green_single_drive(_chromium_available, demo_server):
    config = DemoConfig(base_url=demo_server)
    driver = DemoUiDriver(config)
    state = DemoStateProbe(config)

    res = e2e_proj.run(
        _e2e_scenario(),
        auth=DemoAuthenticator(),
        ui=driver,
        state=state,
        recorder=InMemoryRecorder(),
        normalizer=DemoResponseNormalizer(),
    )

    failures = [c for c in res.checks if not c.ok]
    assert res.passed, failures
    # all four observation points present and green, from ONE ui.run_intent call
    assert any(c.point == "frontend" and c.ok for c in res.checks)
    assert any(c.point == "request" and c.ok for c in res.checks)
    assert any(c.point == "response" and c.ok for c in res.checks)
    assert any(c.point == "backend_state" and c.check == "span_exists" and c.ok for c in res.checks)
    assert any(c.point == "backend_state" and c.check == "span_attr" and c.ok for c in res.checks)
    assert res.skipped == []
    assert all(not s.skipped for s in res.steps)
