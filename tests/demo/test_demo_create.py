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
from refracto.declaration.loader import load_scenario

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


def test_frozen_create_scenario_pins_the_exact_row_count_it_declares():
    """The `row_count` assertion must compare against the exact value this scenario
    declares in its own `inputs`, not a near-uninformative lower bound.

    A `row_count > 0` assertion passes whether the product recorded 1 row or 3, so it
    cannot detect a hardcoded or off-by-one span attribute. The precise value `3` is
    legitimate here because it comes from the declaration itself (`inputs: [{rows: 3}]`)
    rather than from test data, a seeded database, or adapter state.

    This is a regression sentinel: it fails loudly if the assertion is ever loosened
    back to a lower bound.
    """
    scenario = load_scenario(SCENARIO_PATH)
    declared_rows = next(i.value for i in scenario.inputs if i.kind == "rows")

    (row_count_assertion,) = [
        a for step in scenario.steps for a in step.expect.backend_state
        if a.check == "span_attr" and a.params.get("attr") == "row_count"
    ]

    assert row_count_assertion.params["op"] == "==", (
        f"expected an exact-value comparison, got op "
        f"{row_count_assertion.params['op']!r}"
    )
    assert row_count_assertion.params["value"] == declared_rows, (
        f"asserted row_count {row_count_assertion.params['value']!r} does not match the "
        f"{declared_rows!r} rows this scenario declares in its own inputs"
    )
