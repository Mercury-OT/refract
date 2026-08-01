"""Backend-only validation for the canonical multi-step demo scenario.

The scenario is loaded from `scenarios/demo_job_run.yaml` and executed through
only the backend projection. This keeps the test focused on ordered execution,
binding, polling, span attribution, and fail-fast semantics using the real demo
server."""
from adapters.demo.wiring import build_adapters
from refracto import runner


def test_demo_job_run_backend_projection_green(demo_server):
    adapters = build_adapters(demo_server)
    rep = runner.run_scenario("scenarios/demo_job_run.yaml", adapters,
                              projections=("backend",))
    assert rep.status == "PASSED", rep.localize()

    (d,) = rep.domains
    assert d.projection == "backend"
    assert all(not s.skipped for s in d.steps)

    by_id = {s.step_id: s for s in d.steps}
    assert set(by_id) == {"create_job", "wait_done", "fetch_result", "archive_job"}
    for step_id, sr in by_id.items():
        assert sr.status == "PASSED", (step_id, sr)

    # the poll step actually polled (readiness only materializes on the 2nd attempt)
    assert by_id["wait_done"].attempts >= 2

    assert any(c.check == "span_exists" and c.ok and c.step == "create_job" for c in d.checks)
    assert any(c.check == "span_exists" and c.ok and c.step == "fetch_result" for c in d.checks)
