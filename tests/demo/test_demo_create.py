"""The frozen `demo_item_create.yaml` scenario passes through the backend projection.

Every other frozen scenario already has a backend-only test that loads its real YAML
(`test_demo_delete.py`, `test_demo_update.py`, `test_demo_list_after_create.py`,
`test_demo_job_run.py`). `demo_item_create.yaml` was the exception: its only coverage
was `test_demo_dof.py`, which is gated on Chromium because it runs all four
projections. On a machine without a browser, nothing exercised the frozen create
declaration at all — so a silent loosening of its assertions could not be detected.

This test closes that gap. It needs no browser: the backend projection alone reaches
the `span_attr` assertion that carries this scenario's strongest claim.
"""
from refracto import runner

from adapters.demo.wiring import build_adapters

SCENARIO_PATH = "scenarios/demo_item_create.yaml"


def test_demo_item_create_backend_projection_green(demo_server):
    adapters = build_adapters(demo_server)
    rep = runner.run_scenario(SCENARIO_PATH, adapters, projections=("backend",))

    assert rep.passed is True, rep.localize()
    (d,) = rep.domains
    assert d.projection == "backend"
    assert all(not s.skipped for s in d.steps)
    assert any(c.check == "success" and c.ok for c in d.checks)
    assert any(c.check == "has" and c.ok for c in d.checks)
    assert any(c.check == "span_exists" and c.ok for c in d.checks)
    assert any(c.check == "span_attr" and c.ok for c in d.checks)
