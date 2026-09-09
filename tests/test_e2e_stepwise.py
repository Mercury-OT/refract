import copy
import dataclasses
import inspect

import pytest

from refracto import ports
from refracto.declaration import binding
from refracto.declaration.model import (
    Assertion,
    Binding,
    Expect,
    Grid,
    Input,
    PollPolicy,
    Ref,
    RequestTemplate,
    Scenario,
    Step,
    ValueRef,
)
from refracto.projection import e2e
from refracto import runner
from refracto.report import (
    BLOCKED,
    DEGRADED,
    ERROR,
    FAILED,
    PASSED,
    SKIPPED,
    RunReport,
)
from tests.fakes import FakeApi, FakeNormalizer, FakeRecorder, FakeUi


def _input(scenario, name, default=None):
    return next((item.value for item in scenario.inputs if item.kind == name), default)


def _rendered(object_id, *, state="ready"):
    return {
        "result_row": {
            "identified": [{"id": str(object_id), "fields": {"state": state}}],
            "anonymous": [],
        },
    }


def _bound_frontend():
    return Assertion("object_field_equals", {
        "anchor": "result_row",
        "id": ValueRef("bind", "item_id"),
        "field": "state",
        "value": "ready",
    })


def _flow(*, same_path=False, third=False, state=True, precondition=None):
    second_path = "items" if same_path else "items/{item_id}"
    backend_state = [Assertion("span_exists", {"span": "item.write"})] if state else []
    steps = [
        Step(
            "create",
            RequestTemplate("POST", "items"),
            Expect(
                frontend=[Assertion("visible", {"anchor": "result_row"})],
                response=[
                    Assertion("success"),
                    Assertion("has", {"field": "item_id"}),
                    Assertion("field_equals", {"field": "order", "value": "first"}),
                ],
                backend_state=list(backend_state),
            ),
        ),
        Step(
            "use",
            RequestTemplate(
                "POST" if same_path else "GET",
                second_path,
                {"source": "{item_id}"} if same_path else None,
            ),
            Expect(
                frontend=[_bound_frontend()],
                response=[
                    Assertion("success"),
                    Assertion("field_equals", {"field": "order", "value": "second"}),
                ],
                backend_state=list(backend_state),
            ),
            bind=[Binding("item_id", "create", "item_id")],
        ),
    ]
    if third:
        steps.append(Step(
            "after",
            RequestTemplate("GET", "after"),
            Expect(response=[Assertion("success")]),
        ))
    return Scenario(
        id="stepwise.e2e",
        grid=Grid("regression", "ui"),
        actor="actor",
        precondition=list(precondition or []),
        inputs=[Input("item_id", "first-object")],
        intent="exercise live stepwise e2e orchestration",
        steps=steps,
    )


class CountingAuth(ports.Authenticator):
    def __init__(self, events=None, error=None):
        self.calls = 0
        self.events = events if events is not None else []
        self.error = error

    def session(self, role):
        self.calls += 1
        self.events.append(("auth", role))
        if self.error:
            raise RuntimeError(self.error)
        return {"role": role}


class LiveState(ports.StateProbe):
    def __init__(self, *, events=None, wrong_trace=None, ready_after=1, return_value=None):
        self.events = events if events is not None else []
        self.wrong_trace = wrong_trace
        self.ready_after = ready_after
        self.return_value = return_value
        self.calls = []

    def observe(self, trace_id):
        self.calls.append(trace_id)
        self.events.append(("state", trace_id))
        if self.return_value is not None:
            return self.return_value
        observed_trace = self.wrong_trace if self.wrong_trace is not None else trace_id
        spans = [ports.Span("item.write")] if len(self.calls) >= self.ready_after else []
        return ports.StateFacts(observed_trace, spans)


class EventNormalizer(FakeNormalizer):
    def __init__(self, events=None, error_step=None):
        self.events = events if events is not None else []
        self.error_step = error_step

    def normalize(self, response):
        self.events.append(("normalize", response.step_id))
        if self.error_step is not None and response.step_id == self.error_step:
            raise RuntimeError("normalizer exploded")
        return super().normalize(response)


class StrictRecorder(FakeRecorder):
    def __init__(self, *, events=None, record_error_step=None, responses_error_at=None,
                 transform=None):
        super().__init__()
        self.events = events if events is not None else []
        self.record_error_step = record_error_step
        self.responses_error_at = responses_error_at
        self.transform = transform

    def record(self, response):
        self.events.append(("record", response.step_id))
        if (
            self.record_error_step is not None
            and response.step_id == self.record_error_step
        ):
            raise RuntimeError("recorder record exploded")
        super().record(response)

    def responses(self):
        self.events.append(("responses", len(self._responses)))
        if self.responses_error_at == len(self._responses):
            raise RuntimeError("recorder responses exploded")
        responses = super().responses()
        return self.transform(responses) if self.transform else responses


def _background(permit, *, correlated=False, same_path=False, trace=None):
    traceparent = permit.traceparent if correlated else trace
    trace_id = permit.trace_id if correlated else (
        traceparent.split("-")[1] if isinstance(traceparent, str) else None
    )
    request = ports.RequestSpec(
        permit.method,
        permit.bound_logical_path if same_path else "background",
        traceparent=traceparent,
    )
    response = ports.RecordedResponse(
        200,
        {},
        {"success": True, "data": {"order": "background"}},
        "",
        trace_id,
        dataclasses.replace(request),
        actual_path=f"/api/{request.path}",
    )
    return [request], [response]


class LiveStepwiseFake(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(
        self,
        *,
        events=None,
        live=True,
        mutate=None,
        error_step=None,
        skip_step=None,
        fail_frontend_step=None,
        close_error=False,
        diagnostics=None,
        body_for=None,
    ):
        self.events = events if events is not None else []
        self.live = live
        self.mutate = mutate
        self.error_step = error_step
        self.skip_step = skip_step
        self.fail_frontend_step = fail_frontend_step
        self.close_error = close_error
        self.diagnostics = diagnostics
        self.body_for = body_for
        self.run_intent_calls = 0
        self.open_calls = 0
        self.close_calls = 0
        self.actions = []
        self.permits = []
        self.evidence = []
        self.contexts = []

    def supports_stepwise_mode(self, mode):
        return mode == "mock" or (mode == "live" and self.live)

    def run_intent(self, scenario, session=None, mock=None):
        self.run_intent_calls += 1
        step = scenario.steps[0]
        response = ports.RecordedResponse(
            200,
            {},
            {"success": True, "data": {"item_id": "legacy", "order": "first"}},
            "",
            "legacy-trace",
            ports.RequestSpec(step.request.method, step.request.path),
        )
        return ports.UiResult(
            rendered=_rendered(_input(scenario, "item_id", "legacy")),
            outgoing=[response.request],
            recorded=[response],
        )

    def open_stepwise(self, scenario, session, *, mode):
        self.open_calls += 1
        self.events.append(("open", mode))
        context = {"mode": mode, "ordinal": self.open_calls}
        self.contexts.append(context)
        return context

    def perform_step(self, scenario, step, context, permit):
        self.events.append(("action", step.id))
        self.actions.append((step.id, context))
        self.permits.append(permit)
        if step.id == self.error_step:
            raise RuntimeError("adapter exploded")
        if step.id == self.skip_step:
            return ports.UiActionResult(skip_reason="adapter intentionally skipped")

        default_bodies = {
            "create": {
                "success": True,
                "data": {
                    "item_id": "bound-id",
                    "order": "first",
                    "zero": 0,
                    "empty": "",
                    "flag": False,
                },
            },
            "use": {"success": True, "data": {"order": "second"}},
            "after": {"success": True, "data": {}},
        }
        if permit.mode == "mock":
            body = copy.deepcopy(permit.mock_response)
        else:
            body = copy.deepcopy(
                self.body_for(step, permit) if self.body_for else default_bodies[step.id]
            )
        template = binding.substitute(step.request, permit.resolved_bindings)
        primary = ports.RequestSpec(
            permit.method,
            permit.bound_logical_path,
            copy.deepcopy(template.body),
            permit.traceparent,
        )
        actual_path = f"/service/{permit.bound_logical_path}"
        response = ports.RecordedResponse(
            200,
            {},
            body,
            "sensitive-response-text",
            permit.trace_id,
            dataclasses.replace(primary),
            step_id=permit.step_id,
            attempt_index=permit.attempt_index,
            is_final=True,
            template_path=permit.template_path,
            bound_logical_path=permit.bound_logical_path,
            actual_path=actual_path,
        )
        object_id = next(iter(permit.resolved_bindings.values()), None)
        if object_id is None:
            object_id = _input(scenario, "item_id", step.id)
        rendered = (
            {"result_row": {"identified": [], "anonymous": []}}
            if step.id == self.fail_frontend_step
            else _rendered(object_id)
        )
        diagnostic_outgoing, diagnostic_recorded = [], []
        if self.diagnostics:
            diagnostic_outgoing, diagnostic_recorded = self.diagnostics(permit)
        evidence = ports.UiActionEvidence(
            execution_id=permit.execution_id,
            action_id=permit.action_id,
            request_id=permit.request_id,
            step_id=permit.step_id,
            attempt_index=permit.attempt_index,
            mode=permit.mode,
            method=permit.method,
            template_path=permit.template_path,
            bound_logical_path=permit.bound_logical_path,
            permit_token=permit.token,
            actual_path=actual_path,
            is_final=True,
            primary_request=primary,
            primary_response=response,
            rendered=rendered,
            diagnostic_outgoing=diagnostic_outgoing,
            diagnostic_recorded=diagnostic_recorded,
        )
        result = ports.UiActionResult(evidence=evidence)
        if self.mutate:
            result = self.mutate(result, permit, len(self.actions) - 1)
        if result.evidence is not None:
            self.evidence.append(result.evidence)
        return result

    def close_stepwise(self, context):
        self.close_calls += 1
        self.events.append(("close", context["ordinal"]))
        if self.close_error:
            raise RuntimeError("close exploded")


def _run(
    scenario,
    driver,
    *,
    auth=None,
    state=None,
    recorder=None,
    normalizer=None,
    resolve_precondition=None,
    poll_config=None,
    now=None,
    sleep=None,
):
    return e2e.run(
        scenario,
        auth=auth or CountingAuth(),
        ui=driver,
        state=state,
        recorder=recorder or StrictRecorder(),
        normalizer=normalizer or EventNormalizer(),
        resolve_precondition=resolve_precondition,
        poll_config=poll_config,
        now=now,
        sleep=sleep,
    )


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def test_stepwise_mode_api_is_backward_compatible_and_live_is_explicit():
    from tests.test_frontend_stepwise import StepwiseFake

    assert StepwiseFake().supports_stepwise_mode("mock") is True
    assert StepwiseFake().supports_stepwise_mode("live") is False
    assert LiveStepwiseFake().supports_stepwise_mode("live") is True
    assert "supports_stepwise_mode" not in ports.StepwiseUiDriver.__abstractmethods__
    signature = inspect.signature(ports.UiActionPermit)
    assert signature.parameters["mock_response"].default is inspect.Parameter.empty
    assert signature.parameters["mock_response"].kind is inspect.Parameter.KEYWORD_ONLY


def test_single_step_e2e_still_uses_legacy_run_intent_once():
    scenario = _flow(state=False)
    scenario.steps = scenario.steps[:1]
    driver = LiveStepwiseFake()

    result = _run(scenario, driver)

    assert result.status == PASSED
    assert driver.run_intent_calls == 1
    assert driver.open_calls == 0
    assert driver.actions == []


@pytest.mark.parametrize("driver", [FakeUi(), LiveStepwiseFake(live=False)])
def test_non_live_capability_degrades_before_auth_context_or_action(driver):
    auth = CountingAuth()

    result = _run(_flow(), driver, auth=auth)

    assert result.status == DEGRADED
    assert result.skipped == ["multi-step e2e live capability not supported"]
    assert auth.calls == 0
    assert getattr(driver, "open_calls", 0) == 0
    assert getattr(driver, "actions", []) == []


def test_truthy_non_bool_live_capability_is_not_accepted():
    class AmbiguousCapability(LiveStepwiseFake):
        def supports_stepwise_mode(self, mode):
            return 1

    driver = AmbiguousCapability()
    auth = CountingAuth()

    result = _run(_flow(), driver, auth=auth)

    assert result.skipped == ["multi-step e2e live capability not supported"]
    assert auth.calls == 0
    assert driver.open_calls == 0


def test_multistep_business_poll_rejected_before_all_side_effects():
    scenario = _flow(precondition=[Ref("ready")])
    scenario.steps[1].poll = PollPolicy("FAIL")
    driver = LiveStepwiseFake()
    auth = CountingAuth()
    preconditions = []

    result = _run(
        scenario,
        driver,
        auth=auth,
        resolve_precondition=lambda ref, session: preconditions.append(ref),
    )

    assert result.skipped == ["multi-step UI polling not supported"]
    assert auth.calls == 0
    assert preconditions == []
    assert driver.open_calls == 0
    assert driver.actions == []


def test_auth_and_preconditions_run_once_in_order_before_one_context():
    events = []
    scenario = _flow(precondition=[Ref("first"), Ref("second")])
    auth = CountingAuth(events)
    driver = LiveStepwiseFake(events=events)

    result = _run(
        scenario,
        driver,
        auth=auth,
        state=LiveState(),
        resolve_precondition=lambda ref, session: events.append(("pre", ref.ref)),
    )

    assert result.status == PASSED
    assert auth.calls == 1
    assert events[:4] == [
        ("auth", "actor"),
        ("pre", "first"),
        ("pre", "second"),
        ("open", "live"),
    ]
    assert driver.open_calls == driver.close_calls == 1


@pytest.mark.parametrize("missing_resolver", [True, False])
def test_precondition_configuration_or_execution_error_blocks_before_context(
    missing_resolver,
):
    scenario = _flow(precondition=[Ref("required")])
    driver = LiveStepwiseFake()
    auth = CountingAuth()

    resolver = None if missing_resolver else (
        lambda ref, session: (_ for _ in ()).throw(RuntimeError("precondition exploded"))
    )
    result = _run(scenario, driver, auth=auth, resolve_precondition=resolver)

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert driver.open_calls == 0
    assert driver.actions == []
    assert result.provider_recordings == []
    assert (auth.calls == 0) if missing_resolver else (auth.calls == 1)


def test_auth_error_blocks_before_context_and_recording():
    driver = LiveStepwiseFake()

    result = _run(_flow(), driver, auth=CountingAuth(error="auth exploded"))

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert driver.open_calls == 0
    assert result.provider_recordings == []


def test_missing_authenticator_is_structured_before_context_or_action():
    driver = LiveStepwiseFake()
    recorder = StrictRecorder()

    result = e2e.run(
        _flow(),
        auth=None,
        ui=driver,
        state=LiveState(),
        recorder=recorder,
        normalizer=EventNormalizer(),
    )

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert "Authenticator" in result.steps[0].detail
    assert driver.open_calls == 0
    assert driver.actions == []
    assert recorder.responses() == []


def test_two_live_steps_share_context_and_have_distinct_correlated_evidence():
    driver = LiveStepwiseFake()
    state = LiveState()

    result = _run(_flow(), driver, state=state)

    assert result.status == PASSED
    assert [step.status for step in result.steps] == [PASSED, PASSED]
    assert driver.open_calls == driver.close_calls == 1
    assert driver.actions[0][1] is driver.actions[1][1]
    assert [step for step, _ in driver.actions] == ["create", "use"]
    assert {permit.mode for permit in driver.permits} == {"live"}
    assert all(permit.mock_response is None for permit in driver.permits)
    assert len({permit.execution_id for permit in driver.permits}) == 1
    assert len({permit.action_id for permit in driver.permits}) == 2
    assert len({permit.request_id for permit in driver.permits}) == 2
    assert len({permit.trace_id for permit in driver.permits}) == 2
    assert state.calls == [permit.trace_id for permit in driver.permits]


def test_frontend_mock_and_e2e_live_run_as_separate_physical_projections(tmp_path):
    scenario_path = tmp_path / "flow.yaml"
    scenario_path.write_text(
        "version: 2\n"
        "scenario: stepwise.e2e\n"
        "grid: {level: regression, module: ui}\n"
        "actor: actor\n"
        "inputs: [{item_id: first-object}]\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n"
        "      frontend: [{check: visible, anchor: result_row}]\n"
        "      response:\n"
        "        - {check: success}\n"
        "        - {check: has, field: item_id}\n"
        "        - {check: field_equals, field: order, value: first}\n"
        "      backend_state: [{check: span_exists, span: item.write}]\n"
        "  - id: use\n"
        "    request: {method: GET, path: 'items/{item_id}'}\n"
        "    bind:\n"
        "      item_id: {from: create, field: item_id}\n"
        "    expect:\n"
        "      frontend:\n"
        "        - check: object_field_equals\n"
        "          anchor: result_row\n"
        "          id: {from_bind: item_id}\n"
        "          field: state\n"
        "          value: ready\n"
        "      response:\n"
        "        - {check: success}\n"
        "        - {check: field_equals, field: order, value: second}\n"
        "      backend_state: [{check: span_exists, span: item.write}]\n",
        encoding="utf-8",
    )
    driver = LiveStepwiseFake()
    adapters = runner.Adapters(
        auth=CountingAuth(),
        api=FakeApi(),
        state=LiveState(),
        ui=driver,
        recorder_factory=StrictRecorder,
        resolve_request=lambda scenario, step, template: ports.RequestSpec(
            template.method, template.path, template.body
        ),
        normalizer=EventNormalizer(),
    )

    report = runner.run_scenario(
        str(scenario_path),
        adapters,
        projections=("frontend", "e2e"),
    )

    assert report.status == PASSED
    assert [domain.projection for domain in report.domains] == ["frontend", "e2e"]
    assert [context["mode"] for context in driver.contexts] == ["mock", "live"]
    assert driver.contexts[0] is not driver.contexts[1]
    assert driver.open_calls == driver.close_calls == 2
    assert [permit.mode for permit in driver.permits] == [
        "mock", "mock", "live", "live",
    ]


def test_core_finishes_normalize_record_state_before_authorizing_next_action():
    events = []
    driver = LiveStepwiseFake(events=events)
    state = LiveState(events=events)
    normalizer = EventNormalizer(events=events)
    recorder = StrictRecorder(events=events)

    result = _run(
        _flow(),
        driver,
        state=state,
        normalizer=normalizer,
        recorder=recorder,
    )

    assert result.status == PASSED
    first_action = events.index(("action", "create"))
    first_normalize = events.index(("normalize", "create"))
    first_record = events.index(("record", "create"))
    first_state = next(i for i, event in enumerate(events) if event[0] == "state")
    second_action = events.index(("action", "use"))
    assert first_action < first_normalize < first_record < first_state < second_action


def test_bind_drives_next_action_body_and_bound_logical_path():
    driver = LiveStepwiseFake()

    result = _run(_flow(), driver, state=LiveState())

    assert result.status == PASSED
    second = driver.permits[1]
    assert second.resolved_bindings == {"item_id": "bound-id"}
    assert second.bound_logical_path == "items/bound-id"
    assert driver.evidence[1].primary_request.path == "items/bound-id"


def test_repeated_endpoint_has_distinct_ordered_live_responses_and_recordings():
    driver = LiveStepwiseFake()

    result = _run(_flow(same_path=True), driver, state=LiveState())

    assert result.status == PASSED
    assert [(p.method, p.bound_logical_path) for p in driver.permits] == [
        ("POST", "items"),
        ("POST", "items"),
    ]
    assert [r.json["data"]["order"] for r in result.provider_recordings] == [
        "first",
        "second",
    ]
    assert [r.step_id for r in result.provider_recordings] == ["create", "use"]
    assert len({r.trace_id for r in result.provider_recordings}) == 2


def test_each_step_has_four_observation_points_from_its_permit_trace():
    driver = LiveStepwiseFake()

    result = _run(_flow(), driver, state=LiveState())

    for step_result, permit, recording in zip(
        result.steps, driver.permits, result.provider_recordings
    ):
        assert {check.point for check in step_result.checks} == {
            "frontend", "request", "response", "backend_state",
        }
        assert step_result.trace_id == permit.trace_id == recording.trace_id
        assert recording.step_id == permit.step_id == step_result.step_id


def test_background_and_same_path_diagnostics_never_enter_recorder_or_assertions():
    driver = LiveStepwiseFake(
        diagnostics=lambda permit: _background(permit, same_path=True),
    )

    result = _run(_flow(), driver, state=LiveState())

    assert result.status == PASSED
    assert len(result.provider_recordings) == 2
    assert all(r.json["data"]["order"] != "background" for r in result.provider_recordings)
    assert all(check.ok for check in result.checks)


def test_delayed_previous_response_is_diagnostic_not_current_primary():
    seen = []

    def diagnostics(permit):
        if not seen:
            seen.append(permit)
            return [], []
        return _background(
            permit,
            same_path=True,
            trace=seen[0].traceparent,
        )

    driver = LiveStepwiseFake(diagnostics=diagnostics)

    result = _run(_flow(same_path=True), driver, state=LiveState())

    assert result.status == PASSED
    assert [recording.trace_id for recording in result.provider_recordings] == [
        permit.trace_id for permit in driver.permits
    ]


def test_diagnostic_reusing_current_trace_is_protocol_error():
    driver = LiveStepwiseFake(
        diagnostics=lambda permit: _background(
            permit,
            correlated=True,
            same_path=True,
        ),
    )

    result = _run(_flow(), driver, state=LiveState())

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert "diagnostic" in result.steps[0].detail
    assert result.provider_recordings == []


def test_matching_background_cannot_rescue_invalid_primary():
    def mutate(result, permit, index):
        outgoing, recorded = _background(permit, same_path=True)
        invalid_primary = dataclasses.replace(
            result.evidence.primary_request,
            path="wrong-primary",
        )
        invalid_response = dataclasses.replace(
            result.evidence.primary_response,
            request=dataclasses.replace(invalid_primary),
        )
        return ports.UiActionResult(evidence=dataclasses.replace(
            result.evidence,
            primary_request=invalid_primary,
            primary_response=invalid_response,
            diagnostic_outgoing=outgoing,
            diagnostic_recorded=recorded,
        ))

    result = _run(_flow(), LiveStepwiseFake(mutate=mutate), state=LiveState())

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert result.provider_recordings == []


def test_logical_and_actual_paths_may_differ_when_internal_evidence_agrees():
    driver = LiveStepwiseFake()

    result = _run(_flow(), driver, state=LiveState())

    assert result.status == PASSED
    assert driver.evidence[0].primary_request.path == "items"
    assert driver.evidence[0].actual_path == "/service/items"
    assert result.provider_recordings[0].actual_path == "/service/items"


@pytest.mark.parametrize("actual", ["", None, "/wrong"])
def test_invalid_or_inconsistent_actual_path_is_error(actual):
    def mutate(result, permit, index):
        evidence = dataclasses.replace(result.evidence, actual_path=actual)
        return ports.UiActionResult(evidence=evidence)

    result = _run(
        _flow(), LiveStepwiseFake(mutate=mutate), state=LiveState()
    )

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert "actual_path" in result.steps[0].detail


def test_equal_but_distinct_request_values_are_accepted():
    driver = LiveStepwiseFake()

    result = _run(_flow(), driver, state=LiveState())

    assert result.status == PASSED
    for evidence in driver.evidence:
        assert evidence.primary_request == evidence.primary_response.request
        assert evidence.primary_request is not evidence.primary_response.request


def _replace_response(evidence, **changes):
    return dataclasses.replace(
        evidence,
        primary_response=dataclasses.replace(evidence.primary_response, **changes),
    )


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("evidence", "execution_id", "wrong"),
        ("evidence", "action_id", "wrong"),
        ("evidence", "request_id", "wrong"),
        ("evidence", "step_id", "wrong"),
        ("evidence", "attempt_index", 1),
        ("evidence", "mode", "mock"),
        ("evidence", "method", "DELETE"),
        ("evidence", "template_path", "wrong"),
        ("evidence", "bound_logical_path", "wrong"),
        ("evidence", "permit_token", "wrong"),
        ("evidence", "is_final", False),
        ("request", "method", "DELETE"),
        ("request", "path", "wrong"),
        ("request", "traceparent", "00-wrong-wrong-01"),
        ("response", "step_id", "wrong"),
        ("response", "attempt_index", 1),
        ("response", "template_path", "wrong"),
        ("response", "bound_logical_path", "wrong"),
        ("response", "trace_id", "wrong"),
        ("response", "is_final", False),
    ],
)
def test_any_live_identity_mismatch_is_error(target, field, value):
    def mutate(result, permit, index):
        evidence = result.evidence
        if target == "response":
            evidence = _replace_response(evidence, **{field: value})
        elif target == "request":
            request = dataclasses.replace(
                evidence.primary_request,
                **{field: value},
            )
            evidence = dataclasses.replace(
                evidence,
                primary_request=request,
                primary_response=dataclasses.replace(
                    evidence.primary_response,
                    request=dataclasses.replace(request),
                ),
            )
        else:
            evidence = dataclasses.replace(evidence, **{field: value})
        return ports.UiActionResult(evidence=evidence)

    result = _run(_flow(), LiveStepwiseFake(mutate=mutate), state=LiveState())

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("evidence", "attempt_index", False),
        ("evidence", "is_final", 1),
        ("response", "attempt_index", False),
        ("response", "is_final", 1),
    ],
)
def test_bool_int_identity_coercion_is_rejected(target, field, value):
    def mutate(result, permit, index):
        evidence = result.evidence
        if target == "response":
            evidence = _replace_response(evidence, **{field: value})
        else:
            evidence = dataclasses.replace(evidence, **{field: value})
        return ports.UiActionResult(evidence=evidence)

    result = _run(_flow(), LiveStepwiseFake(mutate=mutate), state=LiveState())

    assert result.steps[0].status == ERROR


def test_request_body_bool_int_coercion_is_rejected():
    def mutate(result, permit, index):
        request = dataclasses.replace(result.evidence.primary_request, body={"flag": True})
        response = dataclasses.replace(
            result.evidence.primary_response,
            request=dataclasses.replace(request, body={"flag": 1}),
        )
        return ports.UiActionResult(evidence=dataclasses.replace(
            result.evidence,
            primary_request=request,
            primary_response=response,
        ))

    result = _run(_flow(), LiveStepwiseFake(mutate=mutate), state=LiveState())

    assert result.steps[0].status == ERROR
    assert "response.request values differ" in result.steps[0].detail


def test_same_run_replay_and_cross_run_stale_evidence_are_rejected():
    driver = LiveStepwiseFake()

    first = _run(_flow(), driver, state=LiveState())
    stale = ports.UiActionResult(evidence=driver.evidence[0])
    driver.mutate = lambda result, permit, index: stale
    second = _run(_flow(), driver, state=LiveState())

    assert first.status == PASSED
    assert second.steps[0].status == ERROR
    assert "execution_id mismatch" in second.steps[0].detail

    def replay_first(result, permit, index):
        if index == 1:
            return ports.UiActionResult(evidence=same_run.evidence[0])
        return result

    same_run = LiveStepwiseFake(mutate=replay_first)
    replayed = _run(_flow(), same_run, state=LiveState())
    assert [step.status for step in replayed.steps] == [PASSED, ERROR]
    assert "replayed" in replayed.steps[1].detail


def test_state_probe_is_core_owned_and_called_only_for_declared_backend_state():
    driver = LiveStepwiseFake()
    state = LiveState()

    with_state = _run(_flow(), driver, state=state)
    assert with_state.status == PASSED
    assert state.calls == [permit.trace_id for permit in driver.permits]
    assert not any(hasattr(evidence, "state") for evidence in driver.evidence)

    no_state_expectation = _flow(state=False)
    state = LiveState()
    without_state = _run(no_state_expectation, LiveStepwiseFake(), state=state)
    assert without_state.status == PASSED
    assert state.calls == []


@pytest.mark.parametrize(
    "state",
    [
        LiveState(wrong_trace="wrong"),
        LiveState(return_value=ports.StateFacts(True, [ports.Span("item.write")])),
        LiveState(return_value=ports.StateFacts("", [ports.Span("item.write")])),
        LiveState(return_value={"trace_id": "not-state-facts"}),
    ],
)
def test_invalid_state_facts_identity_or_type_is_error(state):
    result = _run(_flow(), LiveStepwiseFake(), state=state)

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]


def test_backend_state_polling_reobserves_without_repeating_ui_action():
    clock = FakeClock()
    driver = LiveStepwiseFake()
    state = LiveState(ready_after=3)

    result = _run(
        _flow(),
        driver,
        state=state,
        now=clock.now,
        sleep=clock.sleep,
    )

    assert result.status == PASSED
    assert len(driver.actions) == 2
    assert len(state.calls) == 4
    assert state.calls[:3] == [driver.permits[0].trace_id] * 3


def test_backend_state_polling_uses_the_existing_poll_config():
    clock = FakeClock()
    driver = LiveStepwiseFake()
    state = LiveState(ready_after=99)

    result = _run(
        _flow(),
        driver,
        state=state,
        poll_config=runner.PollConfig(timeout=0.5, interval=0.25),
        now=clock.now,
        sleep=clock.sleep,
    )

    assert [step.status for step in result.steps] == [FAILED, BLOCKED]
    assert len(driver.actions) == 1
    assert clock.value == 0.5


def test_every_backend_state_poll_observation_revalidates_trace_identity():
    class BecomesMislabeled(LiveState):
        def observe(self, trace_id):
            self.calls.append(trace_id)
            if len(self.calls) == 1:
                return ports.StateFacts(trace_id, [])
            return ports.StateFacts("wrong-on-retry", [ports.Span("item.write")])

    clock = FakeClock()
    driver = LiveStepwiseFake()
    state = BecomesMislabeled()

    result = _run(
        _flow(),
        driver,
        state=state,
        now=clock.now,
        sleep=clock.sleep,
    )

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert len(driver.actions) == 1


def test_backend_state_failure_blocks_later_action():
    clock = FakeClock()
    driver = LiveStepwiseFake()
    state = LiveState(ready_after=100)

    result = _run(
        _flow(),
        driver,
        state=state,
        now=clock.now,
        sleep=clock.sleep,
    )

    assert [step.status for step in result.steps] == [FAILED, BLOCKED]
    assert [step_id for step_id, _ in driver.actions] == ["create"]


@pytest.mark.parametrize("failure", ["frontend", "response"])
def test_failed_frontend_or_response_blocks_later_action(failure):
    driver = LiveStepwiseFake(
        fail_frontend_step="create" if failure == "frontend" else None,
        body_for=(
            (lambda step, permit: {"success": False, "data": {
                "item_id": "bound-id", "order": "first",
            }})
            if failure == "response"
            else None
        ),
    )

    result = _run(_flow(), driver, state=LiveState())

    assert [step.status for step in result.steps] == [FAILED, BLOCKED]
    assert len(driver.actions) == 1


@pytest.mark.parametrize("stage", ["adapter", "normalizer", "record", "responses", "state"])
def test_runtime_errors_are_structured_and_block_later_action(stage):
    driver = LiveStepwiseFake(error_step="create" if stage == "adapter" else None)
    normalizer = EventNormalizer(error_step="create" if stage == "normalizer" else None)
    recorder = StrictRecorder(
        record_error_step="create" if stage == "record" else None,
        responses_error_at=1 if stage == "responses" else None,
    )
    state = (
        LiveState(return_value={"wrong": "type"})
        if stage == "state"
        else LiveState()
    )

    result = _run(
        _flow(),
        driver,
        normalizer=normalizer,
        recorder=recorder,
        state=state,
    )

    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert len(driver.actions) == 1


def test_normalizer_cannot_rewrite_the_verified_recording_identity():
    class IdentityMutatingNormalizer(EventNormalizer):
        def normalize(self, response):
            norm = super().normalize(response)
            response.step_id = "tampered-after-validation"
            response.trace_id = "tampered-trace"
            response.actual_path = "/tampered"
            response.request.path = "tampered"
            return norm

    driver = LiveStepwiseFake()
    recorder = StrictRecorder()

    result = _run(
        _flow(),
        driver,
        normalizer=IdentityMutatingNormalizer(),
        recorder=recorder,
        state=LiveState(),
    )

    assert result.status == PASSED
    assert [response.step_id for response in result.provider_recordings] == [
        "create",
        "use",
    ]
    assert [response.trace_id for response in result.provider_recordings] == [
        permit.trace_id for permit in driver.permits
    ]
    assert [response.request.path for response in result.provider_recordings] == [
        "items",
        "items/bound-id",
    ]
    assert [response.actual_path for response in result.provider_recordings] == [
        "/service/items",
        "/service/items/bound-id",
    ]


@pytest.mark.parametrize(
    "transform",
    [
        lambda responses: list(reversed(responses)),
        lambda responses: responses[:-1],
        lambda responses: [
            dataclasses.replace(responses[0], step_id="wrong"), *responses[1:]
        ],
    ],
)
def test_recorder_results_count_identity_and_order_are_verified(transform):
    result = _run(
        _flow(),
        LiveStepwiseFake(),
        state=LiveState(),
        recorder=StrictRecorder(transform=transform),
    )

    assert ERROR in [step.status for step in result.steps]
    assert len(result.provider_recordings) < 2


def test_adapter_skip_blocks_later_action_without_recording_current_response():
    driver = LiveStepwiseFake(skip_step="create")

    result = _run(_flow(), driver, state=LiveState())

    assert [step.status for step in result.steps] == [SKIPPED, BLOCKED]
    assert result.provider_recordings == []
    assert len(driver.actions) == 1


def test_missing_state_probe_is_visible_degradation_but_flow_continues():
    driver = LiveStepwiseFake()

    result = _run(_flow(), driver, state=None)

    assert result.status == DEGRADED
    assert [step.status for step in result.steps] == [PASSED, PASSED]
    assert all(step.skipped for step in result.steps)
    assert len(driver.actions) == 2


@pytest.mark.parametrize(
    ("terminal", "expected"),
    [
        ("passed", PASSED),
        ("failed", FAILED),
        ("error", ERROR),
        ("skipped", SKIPPED),
    ],
)
def test_c5_bindings_survive_all_post_bind_terminal_states(terminal, expected):
    driver = LiveStepwiseFake(
        fail_frontend_step="use" if terminal == "failed" else None,
        error_step="use" if terminal == "error" else None,
        skip_step="use" if terminal == "skipped" else None,
    )

    result = _run(_flow(), driver, state=LiveState())

    assert result.steps[1].status == expected
    assert result.steps[1].resolved_bindings == {"item_id": "bound-id"}
    assert result.steps[1].resolved_bindings is not driver.permits[1].resolved_bindings


def test_c5_bind_failure_is_atomic_and_blocked_declared_bind_stays_empty():
    scenario = _flow()
    scenario.steps[1].bind = [
        Binding("first", "create", "order"),
        Binding("missing", "create", "missing"),
    ]
    scenario.steps[1].request = RequestTemplate("GET", "items/{first}/{missing}")
    driver = LiveStepwiseFake()

    failed_bind = _run(scenario, driver, state=LiveState())
    assert [step.status for step in failed_bind.steps] == [PASSED, ERROR]
    assert failed_bind.steps[1].resolved_bindings == {}
    assert len(driver.actions) == 1

    blocked_driver = LiveStepwiseFake(fail_frontend_step="create")
    blocked = _run(_flow(), blocked_driver, state=LiveState())
    assert [step.status for step in blocked.steps] == [FAILED, BLOCKED]
    assert blocked.steps[1].resolved_bindings == {}


def test_c5_falsy_bind_values_are_preserved():
    scenario = _flow(state=False)
    scenario.steps[1].bind = [
        Binding("zero", "create", "zero"),
        Binding("empty", "create", "empty"),
        Binding("flag", "create", "flag"),
    ]
    scenario.steps[1].request = RequestTemplate(
        "POST",
        "target",
        {"zero": "{zero}", "empty": "{empty}", "flag": "{flag}"},
    )
    scenario.steps[1].expect.frontend = []
    driver = LiveStepwiseFake()

    result = _run(scenario, driver)

    expected = {"zero": 0, "empty": "", "flag": False}
    assert result.steps[1].status == PASSED
    assert result.steps[1].resolved_bindings == expected
    assert driver.permits[1].resolved_bindings == expected


@pytest.mark.parametrize(
    "terminal",
    ["success", "failed_check", "action_error", "close_error"],
)
def test_context_closes_exactly_once_on_all_opened_paths(terminal):
    driver = LiveStepwiseFake(
        error_step="create" if terminal == "action_error" else None,
        fail_frontend_step="create" if terminal == "failed_check" else None,
        close_error=terminal == "close_error",
    )

    result = _run(_flow(), driver, state=LiveState())

    assert driver.open_calls == driver.close_calls == 1
    if terminal == "close_error":
        assert result.steps[-1].status == ERROR
        assert "context close failed" in result.steps[-1].detail


def test_live_sensitive_payloads_are_hidden_from_domain_and_report_repr():
    sentinel = "LIVE-TOP-SECRET-SENTINEL"

    def body(step, permit):
        if step.id == "create":
            return {
                "success": True,
                "data": {"item_id": sentinel, "order": "first"},
            }
        return {"success": True, "data": {"order": "second", "secret": sentinel}}

    driver = LiveStepwiseFake(body_for=body)
    domain = _run(_flow(), driver, state=LiveState())
    report = RunReport("sensitive", [domain])

    assert sentinel in domain.provider_recordings[0].json["data"]["item_id"]
    assert sentinel in domain.steps[1].resolved_bindings["item_id"]
    assert sentinel not in repr(driver.permits[1])
    assert sentinel not in repr(driver.evidence[0])
    assert sentinel not in repr(domain)
    assert sentinel not in repr(report)
