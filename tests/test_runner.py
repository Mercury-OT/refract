from refracto import ports, runner
from refracto.report import DEGRADED, EMPTY, NOT_SELECTED
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder, FakeStateProbe, FakeUi


def _resolver(scenario, step, template):
    return ports.RequestSpec(method=template.method, path=template.path, body=(template.body or {}))


def _adapters():
    api = FakeApi(responses={
        ("POST", "resource/action"): {"status": 200, "json": {"success": True, "data": {"taskId": "T1"}}}
    })
    state = FakeStateProbe()
    state.observe = lambda tid: ports.StateFacts(tid, [
        ports.Span("POST /resource/action"),
        ports.Span("INSERT resource.job_queue"),
    ])
    rec_spec = ports.RequestSpec(method="POST", path="resource/action", traceparent="00-abc-def-01")
    rec_resp = ports.RecordedResponse(
        status=200,
        headers={},
        text="",
        json={"success": True, "data": {"taskId": "T1"}},
        trace_id="abc",
        request=rec_spec,
    )
    ui = FakeUi(rendered={"result_row": {"visible": True, "count": 2}},
                outgoing=[rec_spec], recorded=[rec_resp])
    return runner.Adapters(
        auth=FakeAuth(),
        api=api,
        state=state,
        ui=ui,
        recorder_factory=FakeRecorder,
        resolve_request=_resolver,
        resolve_precondition=None,
        normalizer=FakeNormalizer(),
    )


def test_run_all_projections_green():
    rep = runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", _adapters())
    assert rep.passed
    assert {d.projection for d in rep.domains} == {"backend", "frontend", "e2e", "contract"}


def test_grid_skips_when_module_filtered_out():
    rep = runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", _adapters(), module="etl")
    assert rep.domains == []
    assert rep.status == NOT_SELECTED
    assert not rep.passed


def test_empty_projection_set_is_not_passed():
    rep = runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", _adapters(), projections=())
    assert rep.domains == []
    assert rep.status == EMPTY
    assert not rep.passed


def test_localize_reports_failing_check():
    ad = _adapters()
    ad.api.responses[("POST", "resource/action")]["json"]["data"] = {}
    rep = runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", ad, projections=("backend",))
    assert not rep.passed
    locs = rep.localize()
    assert any(point == "response" and check == "has" for (_proj, _step, point, check, _detail) in locs)


def test_unknown_projection_raises():
    try:
        runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", _adapters(), projections=("bogus",))
        assert False, "expected ValueError for unknown projection"
    except ValueError as e:
        assert "bogus" in str(e)


def test_partial_unknown_projection_raises():
    try:
        runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", _adapters(), projections=("backend", "bogus"))
        assert False, "expected ValueError for unknown projection"
    except ValueError as e:
        assert "bogus" in str(e)


def test_contract_only_skips_backend_fallback_when_templated():
    ad = _adapters()
    rep = runner.run_scenario("tests/fixtures/synthetic_templated_scenario.yaml", ad, projections=("contract",))
    assert ad.api.sent == []
    assert {d.projection for d in rep.domains} == {"contract"}
    contract_domain = rep.domains[0]
    assert contract_domain.status == DEGRADED
    assert contract_domain.skipped


def test_missing_normalizer_raises():
    ad = _adapters()
    ad.normalizer = None
    try:
        runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", ad)
        assert False, "expected ValueError for missing normalizer"
    except ValueError as e:
        assert "normalizer" in str(e)
