"""The frozen `demo_item_delete.yaml` scenario passes through the backend projection. The resolver creates a real item first, then the scenario issues `DELETE items/{id}` and verifies both a successful response and the `item.delete` span."""
from adapters.demo.wiring import build_adapters
from refracto import runner


def test_demo_item_delete_backend_projection_green(demo_server):
    adapters = build_adapters(demo_server)
    rep = runner.run_scenario("scenarios/demo_item_delete.yaml", adapters,
                              projections=("backend",))
    assert rep.passed is True, rep.localize()
    (d,) = rep.domains
    assert d.projection == "backend"
    assert all(not s.skipped for s in d.steps)
    assert any(c.check == "success" and c.ok for c in d.checks)
    assert any(c.check == "span_exists" and c.ok for c in d.checks)
