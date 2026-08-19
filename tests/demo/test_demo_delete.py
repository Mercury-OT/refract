"""The frozen `demo_item_delete.yaml` scenario passes through the backend projection.

The resolver creates the declared number of pre-existing items, then the scenario
issues `DELETE items/{id}` and verifies a successful response, the `item.delete` span,
and the exact number of items the backend reports as remaining afterwards.
"""
from refracto import runner
from refracto.declaration.loader import load_scenario

from adapters.demo.wiring import build_adapters

SCENARIO_PATH = "scenarios/demo_item_delete.yaml"


def test_demo_item_delete_backend_projection_green(demo_server):
    scenario = load_scenario(SCENARIO_PATH)
    adapters = build_adapters(demo_server, scenario=scenario)
    rep = runner.run_scenario(SCENARIO_PATH, adapters, projections=("backend",))
    assert rep.passed is True, rep.localize()
    (d,) = rep.domains
    assert d.projection == "backend"
    assert all(not s.skipped for s in d.steps)
    assert any(c.check == "success" and c.ok for c in d.checks)
    assert any(c.check == "span_exists" and c.ok for c in d.checks)
    assert any(c.check == "span_attr" and c.ok for c in d.checks)
