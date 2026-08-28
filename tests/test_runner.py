import pytest

from refracto import ports, runner
from refracto.report import DEGRADED, EMPTY, NOT_SELECTED, PASSED
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
    ui = FakeUi(rendered={
                    "result_row": {
                        "identified": [
                            {"id": "1", "fields": {}},
                            {"id": "2", "fields": {}},
                        ],
                        "anonymous": [],
                    },
                },
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
    assert rep.degradations() == []
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


def test_contract_without_backend_is_refused_before_any_request():
    """The contract projection consumes recordings the backend projection produces.

    Requesting it alone used to quietly run a full backend pass to manufacture those
    recordings — real requests, real side effects, and no trace of them in the report,
    even though the projection documents itself as issuing no requests. It is now
    refused up front, before any request is sent.
    """
    ad = _adapters()
    try:
        runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", ad, projections=("contract",))
        assert False, "expected ValueError for contract without backend"
    except ValueError as e:
        assert "backend" in str(e)
    assert ad.api.sent == []


def test_contract_with_backend_reuses_its_recordings_without_resending():
    """One backend pass feeds both domains: the scenario's single request is sent once."""
    ad = _adapters()
    rep = runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", ad,
                              projections=("backend", "contract"))
    assert len(ad.api.sent) == 1
    assert {d.projection for d in rep.domains} == {"backend", "contract"}


def test_contract_passes_on_templated_paths_using_backend_recording_identity():
    ad = _adapters()
    rep = runner.run_scenario("tests/fixtures/synthetic_templated_scenario.yaml", ad,
                              projections=("backend", "contract"))
    contract_domain = next(d for d in rep.domains if d.projection == "contract")
    assert contract_domain.status == "PASSED"
    assert contract_domain.skipped == []


def test_missing_normalizer_raises():
    ad = _adapters()
    ad.normalizer = None
    try:
        runner.run_scenario("tests/fixtures/synthetic_scenario.yaml", ad)
        assert False, "expected ValueError for missing normalizer"
    except ValueError as e:
        assert "normalizer" in str(e)


@pytest.mark.parametrize("projections", [("frontend",), ("e2e",)])
def test_ui_projection_without_ui_driver_is_refused_before_any_request(projections):
    ad = _adapters()
    ad.ui = None

    with pytest.raises(ValueError, match="UiDriver"):
        runner.run_scenario(
            "tests/fixtures/synthetic_scenario.yaml",
            ad,
            projections=projections,
        )

    assert ad.api.sent == []


def test_missing_ui_is_refused_before_a_preceding_backend_projection_can_run():
    ad = _adapters()
    ad.ui = None

    with pytest.raises(ValueError, match="UiDriver"):
        runner.run_scenario(
            "tests/fixtures/synthetic_scenario.yaml",
            ad,
            projections=("backend", "frontend"),
        )

    assert ad.api.sent == []


def test_backend_only_run_does_not_require_ui_driver():
    ad = _adapters()
    ad.ui = None

    rep = runner.run_scenario(
        "tests/fixtures/synthetic_scenario.yaml",
        ad,
        projections=("backend",),
    )

    assert rep.status == PASSED
    assert len(ad.api.sent) == 1


def test_missing_state_probe_is_discoverable_from_the_run_report():
    ad = _adapters()
    ad.state = None

    rep = runner.run_scenario(
        "tests/fixtures/synthetic_scenario.yaml",
        ad,
        projections=("backend",),
    )

    assert rep.status == DEGRADED
    assert rep.passed
    assert rep.degradations()
    assert any(
        projection == "backend"
        and step_id == "main"
        and "no StateProbe" in reason
        for projection, step_id, reason in rep.degradations()
    )
