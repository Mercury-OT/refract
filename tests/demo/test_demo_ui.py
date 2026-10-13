"""The same authored creation Scenario exercises real UI in mock and live modes."""
from adapters.demo.config import DemoConfig
from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from refracto.runner import run_scenario
from tests.demo.ui_fixtures import creation_plan


def test_frontend_projection_green_mock_mode(demo_server):
    adapters = build_adapters(demo_server, ui=DemoUiDriver(DemoConfig(base_url=demo_server)))
    report = run_scenario("scenarios/demo_item_create.yaml", adapters,
                          projections=("frontend",), mock_plan=creation_plan())
    assert report.status == "PASSED", [(s.status, s.detail) for s in report.domains[0].steps]
    checks = report.domains[0].checks
    assert {"visible", "count_gt", "object_field_equals", "no_anonymous", "request"} <= {c.check for c in checks if c.ok}


def test_e2e_projection_green_single_drive(demo_server):
    adapters = build_adapters(demo_server, ui=DemoUiDriver(DemoConfig(base_url=demo_server)))
    report = run_scenario("scenarios/demo_item_create.yaml", adapters, projections=("e2e",))
    assert report.status == "PASSED", [(s.status, s.detail) for s in report.domains[0].steps]
    assert {"frontend", "request", "response", "backend_state"} <= {c.point for c in report.domains[0].checks if c.ok}
    assert report.degradations() == []
