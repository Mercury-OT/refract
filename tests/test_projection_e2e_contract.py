import dataclasses

import pytest

from refracto.projection import e2e, contract as contract_proj
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import Scenario, Grid, Input, Expect, Assertion, Step, RequestTemplate, ValueRef
from refracto.runner import PollConfig
from refracto import ports
from tests.fakes import FakeAuth, FakeStateProbe, FakeRecorder, FakeUi, FakeNormalizer


def _rendered_rows(count=2):
    return {
        "result_row": {
            "identified": [{"id": str(index), "fields": {}} for index in range(1, count + 1)],
            "anonymous": [],
        },
    }


class FakeClock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t
    def sleep(self, seconds): self.t += seconds


def _recorded_import(trace_id="abc"):
    spec = ports.RequestSpec(method="POST", path="resource/action",
                             traceparent=f"00-{trace_id}-def-01")
    return ports.RecordedResponse(
        status=200, headers={}, text="",
        json={"success": True, "data": {"taskId": "T1"}}, trace_id=trace_id, request=spec)


def _ready_state():
    state = FakeStateProbe()
    state.observe = lambda trace_id: ports.StateFacts(trace_id, [
        ports.Span("POST /resource/action"), ports.Span("INSERT resource.job_queue")])
    return state


def test_e2e_single_drive_four_points_green():
    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    recording = _recorded_import()
    ui = FakeUi(rendered=_rendered_rows(), outgoing=[recording.request], recorded=[recording])
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=_ready_state(),
        recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert result.status == "PASSED"
    assert len(result.steps) == 1 and result.steps[0].step_id == scenario.steps[0].id
    assert result.steps[0].resolved_bindings == {}
    assert {"frontend", "request", "response", "backend_state"} <= {c.point for c in result.checks}
    assert len(ui.permits) == 1
    assert ui.open_calls == ui.close_calls == 1


def test_e2e_response_fails_loudly_without_matching_ui_traffic():
    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered_rows(), outgoing=[], recorded=[])
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert not result.passed
    assert result.steps[0].status == "ERROR"
    assert "missing or ambiguous" in result.steps[0].detail
    assert result.provider_recordings == []


def test_e2e_field_equals_resolves_scenario_parameter_and_reports_drift(tmp_path):
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nscenario: x\nactor: a\nparameters: {rows: 3}\n"
        "steps:\n"
        "  - id: query\n    do: click\n    target: results.refresh\n"
        "    expect:\n"
        "      request: {method: GET, path: [result]}\n"
        "      response:\n"
        "        - {check: field_equals, field: count, value: {from_parameter: rows}}\n",
        encoding="utf-8")
    scenario = load_scenario(str(path))
    spec = ports.RequestSpec(method="GET", path="result")
    recording = ports.RecordedResponse(
        status=200, headers={}, text="", trace_id=None, request=spec,
        json={"success": True, "data": {"count": 4}},
    )
    ui = FakeUi(outgoing=[spec], recorded=[recording])
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer())
    check = next(c for c in result.checks if c.check == "field_equals")
    assert not check.ok
    assert "field='count' expected=3 observed=4" in check.detail


def test_e2e_reuses_frontend_object_identity_and_anonymous_assertions():
    spec = ports.RequestSpec(method="GET", path="items")
    recording = ports.RecordedResponse(
        status=200, headers={}, text="", json={"success": True}, trace_id=None, request=spec)
    scenario = Scenario(
        id="e2e_object_identity", grid=Grid("smoke", "generic"), actor="actor1",
        precondition=[], inputs=[Input(kind="item_id", value="42")], intent="",
        steps=[Step(
            id="main", action="click", target="items.refresh", request_asserted=True,
            request=RequestTemplate(method="GET", path="items"),
            expect=Expect(frontend=[
                Assertion(check="object_field_equals", params={
                    "anchor": "item_row", "id": ValueRef(source="input", key="item_id"),
                    "field": "state", "value": "ready",
                }),
                Assertion(check="no_anonymous", params={"anchor": "item_row"}),
            ]),
        )],
    )
    ui = FakeUi(
        rendered={"item_row": {
            "identified": [{"id": "42", "fields": {"state": "ready"}}], "anonymous": [],
        }},
        outgoing=[spec], recorded=[recording],
    )
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert result.status == "PASSED"
    assert any(c.check == "object_field_equals" and c.ok for c in result.checks)
    assert any(c.check == "no_anonymous" and c.ok for c in result.checks)

    drifted_ui = FakeUi(
        rendered={"item_row": {
            "identified": [{"id": "42", "fields": {"state": "running"}}],
            "anonymous": [{"fields": {"state": "ghost"}}],
        }},
        outgoing=[spec], recorded=[recording],
    )
    drifted = e2e.run(
        scenario, auth=FakeAuth(), ui=drifted_ui, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert not drifted.passed
    assert any(c.check == "object_field_equals" and not c.ok for c in drifted.checks)
    assert any(c.check == "no_anonymous" and not c.ok for c in drifted.checks)


def test_e2e_backend_state_from_ui_trace_id():
    """Observe the verified live request's trace, never an independent fixture trace."""
    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    recording = _recorded_import(trace_id="feed")
    ui = FakeUi(rendered=_rendered_rows(), outgoing=[recording.request], recorded=[recording])
    observed = []
    state = _ready_state()
    original = state.observe
    state.observe = lambda trace_id: (observed.append(trace_id), original(trace_id))[1]
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=state,
        recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert result.status == "PASSED"
    captured = result.provider_recordings[0].trace_id
    assert captured != "feed"
    assert observed == [captured]


def test_e2e_backend_state_missing_recording_trace_is_protocol_error():
    """Missing correlation is rejected before it can authorize state observation."""
    class MissingTraceUi(FakeUi):
        def perform_step(self, scenario, step, context, permit):
            result = super().perform_step(scenario, step, context, permit)
            traffic = result.evidence.traffic[0]
            bad = dataclasses.replace(traffic, response=dataclasses.replace(traffic.response, trace_id=None))
            return dataclasses.replace(result, evidence=dataclasses.replace(result.evidence, traffic=[bad]))

    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    recording = _recorded_import()
    ui = MissingTraceUi(
        rendered=_rendered_rows(), outgoing=[recording.request], recorded=[recording])
    state = FakeStateProbe()
    observed = []
    state.observe = lambda trace_id: observed.append(trace_id)
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=state,
        recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert result.steps[0].status == "ERROR"
    assert "trace identity" in result.steps[0].detail
    assert observed == []
    assert result.provider_recordings == []


def test_e2e_missing_primitive_driver_errors_and_blocks_before_execution():
    scenario = Scenario(
        id="multi_step_ui_e2e", grid=Grid("integration", "generic"), actor="admin",
        precondition=[], inputs=[], intent="primitive UI capability is mandatory",
        steps=[
            Step(id="s1", action="click", target="resource.submit", request_asserted=True,
                 request=RequestTemplate(method="POST", path="resource/action"),
                 expect=Expect(response=[Assertion("success", {})])),
            Step(id="s2", action="click", target="resource.other", request_asserted=True,
                 request=RequestTemplate(method="POST", path="resource/other"),
                 expect=Expect(response=[Assertion("success", {})])),
        ],
    )
    recorder = FakeRecorder()
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ports.UiDriver(), state=None,
        recorder=recorder, normalizer=FakeNormalizer())
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert "primitive UI capability" in result.steps[0].detail
    assert recorder.responses() == []


@pytest.mark.parametrize(("timeout", "expected_status"), [(2, "FAILED"), (5, "PASSED")])
def test_e2e_state_poll_uses_configured_budget_without_repeating_ui_action(timeout, expected_status):
    """The shared primitive loop applies PollConfig to its state-observation window."""
    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    recording = _recorded_import()
    ui = FakeUi(rendered=_rendered_rows(), outgoing=[recording.request], recorded=[recording])
    clock = FakeClock()
    observed = []

    def observe(trace_id):
        observed.append(trace_id)
        spans = [
            ports.Span("POST /resource/action"), ports.Span("INSERT resource.job_queue")
        ] if clock.t >= 4 else []
        return ports.StateFacts(trace_id, spans)

    state = FakeStateProbe()
    state.observe = observe
    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=state, recorder=FakeRecorder(),
        normalizer=FakeNormalizer(), poll_config=PollConfig(timeout=timeout, interval=1),
        now=clock.now, sleep=clock.sleep)
    assert result.steps[0].status == expected_status
    assert all(c.ok == (expected_status == "PASSED") for c in result.checks if c.check == "span_exists")
    assert clock.t == min(timeout, 4)
    assert len(observed) >= 3
    assert set(observed) == {result.provider_recordings[0].trace_id}
    assert len(ui.permits) == 1
    assert ui.open_calls == ui.close_calls == 1


def test_contract_projection_clean():
    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    spec = ports.RequestSpec(method="POST", path="resource/action")
    recording = ports.RecordedResponse(
        status=200, headers={}, text="", json={"success": True, "data": {"taskId": "T1"}},
        trace_id=None, request=spec, step_id="main", template_path="resource/action")
    result = contract_proj.run(scenario, [recording], FakeNormalizer())
    assert result.status == "PASSED"
    assert len(result.steps) == 1 and result.steps[0].step_id == "contract"
    assert result.steps[0].resolved_bindings == {}


def test_contract_projection_flags_response_field_drift():
    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    spec = ports.RequestSpec(method="POST", path="resource/action")
    recording = ports.RecordedResponse(
        status=200, headers={}, text="", json={"success": True, "data": {"renamedField": "x"}},
        trace_id=None, request=spec, step_id="main", template_path="resource/action")
    result = contract_proj.run(scenario, [recording], FakeNormalizer())
    assert not result.passed
    assert any(c.point == "contract" and not c.ok and "taskId" in c.detail for c in result.checks)
