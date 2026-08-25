"""Backend and contract validation for the canonical multi-step demo scenario.

The scenario is loaded from `scenarios/demo_job_run.yaml` and executed through
the backend and contract projections. This exercises ordered execution, binding,
polling, span attribution, fail-fast semantics, and provider-contract matching
for templated paths using the real demo server."""
from refracto import runner

from adapters.demo.wiring import build_adapters

SCENARIO_PATH = "scenarios/demo_job_run.yaml"


def test_demo_job_run_backend_and_contract_projections_green(demo_server):
    adapters = build_adapters(demo_server)
    rep = runner.run_scenario(SCENARIO_PATH, adapters,
                              projections=("backend", "contract"))
    assert rep.status == "PASSED", rep.localize()

    by_projection = {d.projection: d for d in rep.domains}
    assert set(by_projection) == {"backend", "contract"}
    backend = by_projection["backend"]
    contract = by_projection["contract"]
    assert all(not s.skipped for s in backend.steps)

    by_id = {s.step_id: s for s in backend.steps}
    assert set(by_id) == {"create_job", "wait_done", "fetch_result", "archive_job"}
    for step_id, sr in by_id.items():
        assert sr.status == "PASSED", (step_id, sr)

    # the poll step actually polled (readiness only materializes on the 2nd attempt)
    assert by_id["wait_done"].attempts >= 2

    assert any(c.check == "span_exists" and c.ok and c.step == "create_job" for c in backend.checks)
    assert any(c.check == "span_exists" and c.ok and c.step == "fetch_result" for c in backend.checks)
    assert any(c.check == "span_attr" and c.ok and c.step == "create_job" for c in backend.checks)
    assert any(c.check == "span_attr" and c.ok and c.step == "fetch_result" for c in backend.checks)

    assert contract.status == "PASSED"
    assert contract.skipped == []
    assert any(c.check == "diff" and c.ok for c in contract.checks)
