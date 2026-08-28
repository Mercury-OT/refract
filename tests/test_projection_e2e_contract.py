from refracto.projection import e2e, contract as contract_proj
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import Scenario, Grid, Input, Expect, Assertion, Step, RequestTemplate, ValueRef
from refracto.runner import PollConfig
from refracto import ports
from refracto.report import DEGRADED
from tests.fakes import FakeAuth, FakeStateProbe, FakeRecorder, FakeUi, FakeNormalizer


def _rendered_rows(count=2):
    return {
        "result_row": {
            "identified": [
                {"id": str(index), "fields": {}}
                for index in range(1, count + 1)
            ],
            "anonymous": [],
        },
    }

class FakeClock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t
    def sleep(self, s): self.t += s

def _recorded_import(trace_id="abc"):
    spec = ports.RequestSpec(method="POST", path="resource/action",
                             traceparent=f"00-{trace_id}-def-01")
    return ports.RecordedResponse(status=200, headers={}, text="",
        json={"success": True, "data": {"taskId": "T1"}}, trace_id=trace_id, request=spec)

def test_e2e_single_drive_four_points_green():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    rec = _recorded_import()
    ui = FakeUi(rendered=_rendered_rows(),
                outgoing=[rec.request], recorded=[rec])
    state = FakeStateProbe(spans_by_trace={"abc": [
        ports.Span("POST /resource/action"),
        ports.Span("INSERT resource.job_queue")]})
    res = e2e.run(s, auth=FakeAuth(), ui=ui, state=state, recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert res.passed
    assert len(res.steps) == 1 and res.steps[0].step_id == s.steps[0].id
    points = {c.point for c in res.checks}
    assert {"frontend", "request", "response", "backend_state"} <= points

def test_e2e_response_fails_loudly_without_matching_ui_traffic():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered_rows(),
                outgoing=[], recorded=[])
    res = e2e.run(s, auth=FakeAuth(), ui=ui, state=None, recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert not res.passed
    assert any(c.check == "_no_ui_traffic" and not c.ok for c in res.checks)


def test_e2e_field_equals_resolves_scenario_input_and_reports_drift(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "inputs: [{rows: 3}]\n"
        "expect:\n"
        "  request:\n    - {check: request, method: GET, path: result}\n"
        "  response:\n"
        "    - {check: field_equals, field: count, value: {from_input: rows}}\n",
        encoding="utf-8")
    scenario = load_scenario(str(y))
    spec = ports.RequestSpec(method="GET", path="result")
    recorded = ports.RecordedResponse(
        status=200, headers={}, text="", trace_id=None, request=spec,
        json={"success": True, "data": {"count": 4}},
    )
    ui = FakeUi(outgoing=[spec], recorded=[recorded])

    result = e2e.run(
        scenario, auth=FakeAuth(), ui=ui, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer())

    check = next(c for c in result.checks if c.check == "field_equals")
    assert not check.ok
    assert "field='count' expected=3 observed=4" in check.detail


def test_e2e_reuses_frontend_object_identity_and_anonymous_assertions():
    spec = ports.RequestSpec(method="GET", path="items")
    scenario = Scenario(
        id="e2e_object_identity",
        grid=Grid("smoke", "generic"),
        actor="actor1",
        precondition=[],
        inputs=[Input(kind="item_id", value="42")],
        intent="",
        steps=[Step(
            id="main",
            request=RequestTemplate(method="GET", path="items"),
            expect=Expect(frontend=[
                Assertion(check="object_field_equals", params={
                    "anchor": "item_row",
                    "id": ValueRef(source="input", key="item_id"),
                    "field": "state",
                    "value": "ready",
                }),
                Assertion(check="no_anonymous", params={"anchor": "item_row"}),
            ]),
        )],
    )
    ui = FakeUi(
        rendered={
            "item_row": {
                "identified": [{"id": "42", "fields": {"state": "ready"}}],
                "anonymous": [],
            },
        },
        outgoing=[spec],
    )

    result = e2e.run(
        scenario,
        auth=FakeAuth(),
        ui=ui,
        state=None,
        recorder=FakeRecorder(),
        normalizer=FakeNormalizer(),
    )

    assert result.passed
    assert any(c.check == "object_field_equals" and c.ok for c in result.checks)
    assert any(c.check == "no_anonymous" and c.ok for c in result.checks)

    drifted_ui = FakeUi(
        rendered={
            "item_row": {
                "identified": [{"id": "42", "fields": {"state": "running"}}],
                "anonymous": [{"fields": {"state": "ghost"}}],
            },
        },
        outgoing=[spec],
    )
    drifted = e2e.run(
        scenario,
        auth=FakeAuth(),
        ui=drifted_ui,
        state=None,
        recorder=FakeRecorder(),
        normalizer=FakeNormalizer(),
    )

    assert not drifted.passed
    assert any(c.check == "object_field_equals" and not c.ok for c in drifted.checks)
    assert any(c.check == "no_anonymous" and not c.ok for c in drifted.checks)

def test_e2e_backend_state_from_ui_trace_id():
    """the trace id asserted against Tempo must be the one captured from UI traffic."""
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    rec = _recorded_import(trace_id="feed")
    ui = FakeUi(rendered=_rendered_rows(),
                outgoing=[rec.request], recorded=[rec])
    observed = []
    state = FakeStateProbe(spans_by_trace={"feed": [
        ports.Span("POST /resource/action"),
        ports.Span("INSERT resource.job_queue")]})
    orig = state.observe
    state.observe = lambda tid: (observed.append(tid), orig(tid))[1]
    res = e2e.run(s, auth=FakeAuth(), ui=ui, state=state, recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert res.passed and set(observed) == {"feed"}

def test_e2e_backend_state_no_trace_id_when_recorded_lacks_one():
    """declared backend_state + a real StateProbe, but the matched recorded response carries
    no trace_id (e.g. the UI traffic wasn't traced) -> assert_backend_state must fail loudly
    with _no_trace_id rather than silently skip or crash."""
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    spec = ports.RequestSpec(method="POST", path="resource/action",
                             traceparent="00-abc-def-01")
    rec = ports.RecordedResponse(status=200, headers={}, text="",
        json={"success": True, "data": {"taskId": "T1"}}, trace_id=None, request=spec)
    ui = FakeUi(rendered=_rendered_rows(),
                outgoing=[rec.request], recorded=[rec])
    state = FakeStateProbe(spans_by_trace={"abc": [
        ports.Span("POST /resource/action"),
        ports.Span("INSERT resource.job_queue")]})
    res = e2e.run(s, auth=FakeAuth(), ui=ui, state=state, recorder=FakeRecorder(), normalizer=FakeNormalizer())
    assert not res.passed
    assert any(c.point == "backend_state" and c.check == "_no_trace_id" and not c.ok
               for c in res.checks)

def test_e2e_multi_step_unsupported_degrades():
    s = Scenario(
        id="test_multi_step_ui_e2e",
        grid=Grid("integration", "dataset"),
        actor="admin",
        precondition=[],
        inputs=[],
        intent="multi-step UI is not supported in the e2e projection",
        steps=[
            Step(id="s1", request=RequestTemplate(method="POST", path="resource/action"),
                 expect=Expect(response=[Assertion("success", {})])),
            Step(id="s2", request=RequestTemplate(method="POST", path="resource/other"),
                 expect=Expect(response=[Assertion("success", {})])),
        ],
    )
    res = e2e.run(s, auth=FakeAuth(), ui=FakeUi(), state=None, recorder=FakeRecorder(),
                  normalizer=FakeNormalizer())
    assert res.steps == []
    assert res.skipped == ["multi-step UI not supported"]
    assert res.status == DEGRADED

# --- e2e state polling remains independent from business poll timing ---

def test_e2e_state_poll_uses_own_default_timeout_not_poll_config():
    """The e2e state wait uses its own default observation window rather than the business poll configuration. A small business poll timeout must not shorten backend-state observation."""
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    rec = _recorded_import()
    ui = FakeUi(rendered=_rendered_rows(),
                outgoing=[rec.request], recorded=[rec])
    clock = FakeClock()
    calls = {"n": 0}

    def observe(tid):
        calls["n"] += 1
        ready = calls["n"] >= 5   # ready only after ~4 sleeps (simulated t=4s)
        spans = [ports.Span("POST /resource/action"),
                 ports.Span("INSERT resource.job_queue")] if ready else []
        return ports.StateFacts(tid, spans)

    state = FakeStateProbe()
    state.observe = observe
    poll_config = PollConfig(timeout=2, interval=1)   # tiny business-poll timeout
    res = e2e.run(s, auth=FakeAuth(), ui=ui, state=state, recorder=FakeRecorder(),
                  normalizer=FakeNormalizer(), poll_config=poll_config,
                  now=clock.now, sleep=clock.sleep)
    assert res.passed
    assert any(c.check == "span_exists" and c.ok for c in res.checks)
    assert calls["n"] >= 5


def test_contract_projection_clean():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    spec = ports.RequestSpec(method="POST", path="resource/action")
    rec = ports.RecordedResponse(status=200, headers={}, text="",
        json={"success": True, "data": {"taskId": "T1"}}, trace_id=None, request=spec,
        step_id="main", template_path="resource/action")
    res = contract_proj.run(s, [rec], FakeNormalizer())
    assert res.passed
    assert len(res.steps) == 1 and res.steps[0].step_id == "contract"

def test_contract_projection_flags_drift():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    spec = ports.RequestSpec(method="POST", path="resource/action")
    rec = ports.RecordedResponse(status=200, headers={}, text="",
        json={"success": True, "data": {"renamedField": "x"}}, trace_id=None, request=spec)
    res = contract_proj.run(s, [rec], FakeNormalizer())
    assert not res.passed
    assert any(c.point == "contract" and not c.ok for c in res.checks)
