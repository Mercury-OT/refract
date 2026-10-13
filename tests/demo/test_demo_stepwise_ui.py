"""Mandatory Chromium run: primitives, ordered explicit mocks and response refs."""
from adapters.demo.config import DemoConfig
from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from refracto.runner import run_scenario
from tests.demo.ui_fixtures import creation_plan
import httpx


def test_demo_stepwise_frontend_two_step_flow(demo_server):
    driver = DemoUiDriver(DemoConfig(base_url=demo_server))
    report = run_scenario("scenarios/demo_item_frontend_stepwise.yaml",
        build_adapters(demo_server, ui=driver), projections=("frontend",),
        mock_plan=creation_plan(("first", "1")))
    assert report.status == "PASSED", [(s.status, s.detail) for s in report.domains[0].steps]
    assert report.degradations() == []
    domain = report.domains[0]
    assert [s.status for s in domain.steps] == ["COMPLETED"] * 3 + ["PASSED", "COMPLETED", "PASSED"]
    assert list(domain.steps[4].resolved_bindings.values()) == ["1"]
    assert [u["fixture_id"] for u in domain.mock_consumption] == ["initial-list", "create-1", "list-1", "create-2", "list-2"]
    assert not domain.provider_recordings


def test_unmatched_mock_refresh_aborts_without_real_backend_fallback(demo_server):
    report = run_scenario("scenarios/demo_item_frontend_stepwise.yaml",
        build_adapters(demo_server, ui=DemoUiDriver(DemoConfig(base_url=demo_server))),
        projections=("frontend",), mock_plan=creation_plan(("first", "1"))[:2])
    assert report.status == "FAILED"
    assert report.domains[0].steps[3].status == "ERROR"
    assert all(s.status == "BLOCKED" for s in report.domains[0].steps[4:])
    assert httpx.get(demo_server + "/items").json()["data"]["items"] == []
