"""The frozen `demo_item_update.yaml` scenario passes through the backend projection. Update is modeled as a backend-only scenario with no frontend assertions, and the resolver establishes its precondition by creating a real item first."""
from adapters.demo.wiring import build_adapters
from refracto import runner


def test_demo_item_update_backend_projection_green(demo_server):
    adapters = build_adapters(demo_server)
    rep = runner.run_scenario("scenarios/demo_item_update.yaml", adapters,
                              projections=("backend",))
    assert rep.passed is True, rep.localize()
    (d,) = rep.domains
    assert d.projection == "backend"
    assert all(not s.skipped for s in d.steps)
    assert any(c.check == "success" and c.ok for c in d.checks)
    assert any(c.check == "has" and c.ok for c in d.checks)
    assert any(c.check == "span_exists" and c.ok for c in d.checks)
    assert any(c.check == "span_attr" and c.ok for c in d.checks)
