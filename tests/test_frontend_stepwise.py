import copy
import dataclasses
import inspect
import re

import pytest

from refracto import ports
from refracto.declaration.model import (
    Assertion,
    Binding,
    Expect,
    Grid,
    Input,
    PollPolicy,
    RequestTemplate,
    Scenario,
    Step,
    ValueRef,
)
from refracto.projection import e2e, frontend, ui_stepwise
from refracto.report import (
    BLOCKED,
    DEGRADED,
    ERROR,
    FAILED,
    PASSED,
    SKIPPED,
    RunReport,
)
from tests.fakes import FakeAuth, FakeNormalizer, FakeRecorder, FakeUi


def _input(scenario, name, default=None):
    return next((item.value for item in scenario.inputs if item.kind == name), default)


def _rendered(object_id="object", **fields):
    return {
        "result_row": {
            "identified": [{"id": str(object_id), "fields": fields}],
            "anonymous": [],
        },
    }


class StepwiseFake(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(
        self,
        *,
        mutate=None,
        error_step=None,
        skip_step=None,
        fail_frontend_step=None,
        close_error=False,
        diagnostics=None,
    ):
        self.mutate = mutate
        self.error_step = error_step
        self.skip_step = skip_step
        self.fail_frontend_step = fail_frontend_step
        self.close_error = close_error
        self.diagnostics = diagnostics
        self.run_intent_calls = 0
        self.open_calls = 0
        self.close_calls = 0
        self.actions = []
        self.permits = []
        self.evidence = []
        self.contexts = []

    def run_intent(self, scenario, session=None, mock=None):
        self.run_intent_calls += 1
        step = scenario.steps[0]
        return ports.UiResult(
            rendered=_rendered(_input(scenario, "item_id", "object"), state="ready"),
            outgoing=[ports.RequestSpec(step.request.method, step.request.path)],
        )

    def open_stepwise(self, scenario, session, *, mode):
        self.open_calls += 1
        context = {"mode": mode, "ordinal": self.open_calls}
        self.contexts.append(context)
        return context

    def perform_step(self, scenario, step, context, permit):
        self.actions.append((step.id, context))
        self.permits.append(permit)
        if step.id == self.error_step:
            raise RuntimeError("adapter failed after binding")
        if step.id == self.skip_step:
            return ports.UiActionResult(skip_reason="adapter intentionally skipped")

        object_id = next(iter(permit.resolved_bindings.values()), None)
        if object_id is None:
            object_id = _input(scenario, "item_id", step.id)
        rendered = (
            {"result_row": {"identified": [], "anonymous": []}}
            if step.id == self.fail_frontend_step
            else _rendered(object_id, state=object_id)
        )
        primary = ports.RequestSpec(
            method=permit.method,
            path=permit.bound_logical_path,
            body=copy.deepcopy(step.request.body),
            traceparent=permit.traceparent,
        )
        response_request = dataclasses.replace(primary)
        response = ports.RecordedResponse(
            status=200,
            headers={},
            json=copy.deepcopy(permit.mock_response),
            text="",
            trace_id=permit.trace_id,
            request=response_request,
            step_id=permit.step_id,
            attempt_index=permit.attempt_index,
            is_final=True,
            template_path=permit.template_path,
            bound_logical_path=permit.bound_logical_path,
            actual_path=permit.bound_logical_path,
        )
        diagnostic_outgoing, diagnostic_recorded = [], []
        if self.diagnostics is not None:
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
            actual_path=permit.bound_logical_path,
            is_final=True,
            primary_request=primary,
            primary_response=response,
            rendered=rendered,
            diagnostic_outgoing=diagnostic_outgoing,
            diagnostic_recorded=diagnostic_recorded,
        )
        result = ports.UiActionResult(evidence=evidence)
        if self.mutate is not None:
            result = self.mutate(result, permit, len(self.actions) - 1)
        if result.evidence is not None:
            self.evidence.append(result.evidence)
        return result

    def close_stepwise(self, context):
        self.close_calls += 1
        if self.close_error:
            raise RuntimeError("close exploded")


def _object_from_bind(field="state", key="item_id"):
    return Assertion("object_field_equals", {
        "anchor": "result_row",
        "id": ValueRef("bind", key),
        "field": field,
        "value": ValueRef("bind", key),
    })


def _flow(*, same_path=False, third=False):
    second_path = "items" if same_path else "items/{item_id}"
    steps = [
        Step(
            id="create",
            request=RequestTemplate("POST", "items"),
            expect=Expect(response=[
                Assertion("has", {"field": "item_id"}),
                Assertion("field_equals", {"field": "order", "value": "first"}),
            ]),
        ),
        Step(
            id="use",
            request=RequestTemplate(
                "POST" if same_path else "GET",
                second_path,
                {"source": "{item_id}"} if same_path else None,
            ),
            bind=[Binding("item_id", "create", "item_id")],
            expect=Expect(
                frontend=[_object_from_bind()],
                response=[Assertion("field_equals", {"field": "order", "value": "second"})],
            ),
        ),
    ]
    if third:
        steps.append(Step(
            id="after",
            request=RequestTemplate("GET", "after"),
            expect=Expect(),
        ))
    return Scenario(
        id="stepwise.flow",
        grid=Grid("regression", "ui"),
        actor="actor",
        precondition=[],
        inputs=[],
        intent="exercise safe stepwise frontend orchestration",
        steps=steps,
    )


def _run(scenario, driver, normalizer=None):
    return frontend.run(
        scenario,
        ui=driver,
        auth=FakeAuth(),
        normalizer=normalizer or FakeNormalizer(),
    )


def test_legacy_ui_driver_remains_instantiable():
    assert isinstance(FakeUi(), ports.UiDriver)
    assert not isinstance(FakeUi(), ports.StepwiseUiDriver)


def test_single_step_always_uses_legacy_run_intent_once():
    scenario = _flow()
    scenario.steps = scenario.steps[:1]
    driver = StepwiseFake()

    result = _run(scenario, driver)

    assert result.status == PASSED
    assert driver.run_intent_calls == 1
    assert driver.open_calls == 0
    assert driver.actions == []


def test_legacy_multistep_degrades_before_any_ui_action():
    class CountingLegacy(FakeUi):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def run_intent(self, scenario, session=None, mock=None):
            self.calls += 1
            return super().run_intent(scenario, session, mock)

    driver = CountingLegacy()

    result = _run(_flow(), driver)

    assert result.status == DEGRADED
    assert result.steps == []
    assert result.skipped == ["multi-step UI capability not supported"]
    assert driver.calls == 0


def test_capability_detection_does_not_accept_accidental_duck_typing():
    class DuckOnly(FakeUi):
        def __init__(self):
            super().__init__()
            self.opened = 0

        def open_stepwise(self, scenario, session, *, mode):
            self.opened += 1

        def perform_step(self, scenario, step, context, permit):
            raise AssertionError("must not be called")

        def close_stepwise(self, context):
            raise AssertionError("must not be called")

    driver = DuckOnly()
    result = _run(_flow(), driver)

    assert result.status == DEGRADED
    assert driver.opened == 0


def test_multistep_polling_is_rejected_before_context_or_action():
    scenario = _flow()
    scenario.steps[1].poll = PollPolicy("FAIL")
    driver = StepwiseFake()

    result = _run(scenario, driver)

    assert result.status == DEGRADED
    assert result.skipped == ["multi-step UI polling not supported"]
    assert driver.open_calls == 0
    assert driver.actions == []


def test_two_steps_pass_in_one_context_and_ordered_actions():
    driver = StepwiseFake()

    result = _run(_flow(), driver)

    assert [step.status for step in result.steps] == [PASSED, PASSED]
    assert driver.open_calls == driver.close_calls == 1
    assert [step_id for step_id, _ in driver.actions] == ["create", "use"]
    assert driver.actions[0][1] is driver.actions[1][1]
    assert len({permit.action_id for permit in driver.permits}) == 2
    assert len({permit.request_id for permit in driver.permits}) == 2
    assert {permit.attempt_index for permit in driver.permits} == {0}
    assert {permit.mode for permit in driver.permits} == {"mock"}
    assert len({permit.execution_id for permit in driver.permits}) == 1
    for permit in driver.permits:
        assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-01", permit.traceparent)
        assert permit.trace_id == permit.traceparent.split("-")[1]
        assert re.fullmatch(r"[0-9a-f]{64}", permit.token)


def test_first_response_binding_drives_second_path_action_and_frontend_assertion():
    driver = StepwiseFake()

    result = _run(_flow(), driver)

    bound = "<stub:item_id>"
    assert driver.permits[1].bound_logical_path == "items/%3Cstub%3Aitem_id%3E"
    assert driver.permits[1].resolved_bindings == {"item_id": bound}
    assert result.steps[1].resolved_bindings == {"item_id": bound}
    assert any(c.point == "frontend" and c.ok for c in result.steps[1].checks)


def test_repeated_endpoint_gets_distinct_ordered_permit_mock_responses():
    driver = StepwiseFake()

    result = _run(_flow(same_path=True), driver)

    assert result.status == PASSED
    assert [(p.method, p.bound_logical_path) for p in driver.permits] == [
        ("POST", "items"),
        ("POST", "items"),
    ]
    assert driver.permits[0].mock_response["data"]["order"] == "first"
    assert driver.permits[1].mock_response["data"]["order"] == "second"
    assert driver.permits[0].mock_response != driver.permits[1].mock_response


def test_failed_step_blocks_every_later_action():
    driver = StepwiseFake(fail_frontend_step="create")
    scenario = _flow(third=True)
    scenario.steps[0].expect.frontend = [Assertion("visible", {"anchor": "result_row"})]

    result = _run(scenario, driver)

    assert [step.status for step in result.steps] == [FAILED, BLOCKED, BLOCKED]
    assert result.steps[1].resolved_bindings == {}
    assert [step_id for step_id, _ in driver.actions] == ["create"]


def test_adapter_error_blocks_every_later_action():
    driver = StepwiseFake(error_step="create")

    result = _run(_flow(third=True), driver)

    assert [step.status for step in result.steps] == [ERROR, BLOCKED, BLOCKED]
    assert [step_id for step_id, _ in driver.actions] == ["create"]


def test_adapter_skip_blocks_every_later_action():
    driver = StepwiseFake(skip_step="create")

    result = _run(_flow(third=True), driver)

    assert [step.status for step in result.steps] == [SKIPPED, BLOCKED, BLOCKED]
    assert result.steps[0].skipped == ["adapter intentionally skipped"]
    assert [step_id for step_id, _ in driver.actions] == ["create"]


def test_atomic_bind_failure_exposes_no_partial_values():
    scenario = _flow()
    scenario.steps[1].bind = [
        Binding("first", "create", "order"),
        Binding("second", "create", "missing"),
    ]
    scenario.steps[1].request = RequestTemplate("GET", "consume/{first}/{second}")
    driver = StepwiseFake()

    result = _run(scenario, driver)

    assert result.steps[1].status == ERROR
    assert result.steps[1].resolved_bindings == {}
    assert len(driver.actions) == 1


@pytest.mark.parametrize("stage", ["adapter", "normalizer", "identity"])
def test_error_after_successful_bind_keeps_diagnostics(stage):
    def corrupt(result, permit, index):
        if stage == "identity" and index == 1:
            return ports.UiActionResult(evidence=dataclasses.replace(
                result.evidence,
                request_id="wrong-request",
            ))
        return result

    driver = StepwiseFake(
        error_step="use" if stage == "adapter" else None,
        mutate=corrupt,
    )

    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            if stage == "normalizer" and response.request.path.startswith("items/"):
                raise RuntimeError("normalizer failed after binding")
            return super().normalize(response)

    result = _run(_flow(), driver, Normalizer())

    assert result.steps[1].status == ERROR
    assert result.steps[1].resolved_bindings == {"item_id": "<stub:item_id>"}


@pytest.mark.parametrize(
    ("terminal", "expected"),
    [("failed", FAILED), ("skipped", SKIPPED)],
)
def test_bound_step_keeps_bindings_for_failed_and_skipped_terminal_states(terminal, expected):
    driver = StepwiseFake(
        fail_frontend_step="use" if terminal == "failed" else None,
        skip_step="use" if terminal == "skipped" else None,
    )

    result = _run(_flow(), driver)

    assert result.steps[1].status == expected
    assert result.steps[1].resolved_bindings == {"item_id": "<stub:item_id>"}


def test_falsy_bind_values_are_preserved():
    scenario = Scenario(
        id="stepwise.falsy",
        grid=Grid("regression", "ui"),
        actor="actor",
        precondition=[],
        inputs=[],
        intent="preserve falsy binding values",
        steps=[
            Step(
                "source",
                RequestTemplate("POST", "source"),
                Expect(response=[
                    Assertion("field_equals", {"field": "zero", "value": 0}),
                    Assertion("field_equals", {"field": "empty", "value": ""}),
                    Assertion("field_equals", {"field": "flag", "value": False}),
                ]),
            ),
            Step(
                "target",
                RequestTemplate("POST", "target", {
                    "zero": "{zero}", "empty": "{empty}", "flag": "{flag}",
                }),
                Expect(),
                bind=[
                    Binding("zero", "source", "zero"),
                    Binding("empty", "source", "empty"),
                    Binding("flag", "source", "flag"),
                ],
            ),
        ],
    )
    driver = StepwiseFake()

    result = _run(scenario, driver)

    expected = {"zero": 0, "empty": "", "flag": False}
    assert result.steps[1].status == PASSED
    assert result.steps[1].resolved_bindings == expected
    assert driver.permits[1].resolved_bindings == expected


@pytest.mark.parametrize("close_error", [False, True])
def test_context_closes_exactly_once_on_success_and_close_failure_is_structured(close_error):
    driver = StepwiseFake(close_error=close_error)

    result = _run(_flow(), driver)

    assert driver.close_calls == 1
    if close_error:
        assert result.steps[-1].status == ERROR
        assert "context close failed" in result.steps[-1].detail
        assert result.steps[-1].checks
    else:
        assert result.status == PASSED


def test_context_closes_exactly_once_after_action_exception():
    driver = StepwiseFake(error_step="create")

    _run(_flow(), driver)

    assert driver.open_calls == driver.close_calls == 1


def test_equal_but_distinct_primary_request_instances_are_accepted():
    driver = StepwiseFake()

    result = _run(_flow(), driver)

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
    "mismatch",
    [
        "request_id",
        "step_id",
        "execution_id",
        "action_id",
        "template_path",
        "bound_logical_path",
        "actual_path",
        "permit_token",
        "attempt_index",
        "attempt_index_bool",
        "mode",
        "method",
        "traceparent",
        "trace_id",
        "is_final",
    ],
)
def test_identity_mismatch_is_structured_error(mismatch):
    def mutate(result, permit, index):
        if index:
            return result
        evidence = result.evidence
        field_name = mismatch
        if mismatch in {
            "request_id", "step_id", "execution_id", "action_id",
            "template_path", "bound_logical_path", "actual_path", "permit_token",
            "attempt_index", "attempt_index_bool", "mode", "method", "is_final",
        }:
            if mismatch == "is_final":
                value = False
            elif mismatch == "attempt_index_bool":
                field_name = "attempt_index"
                value = False
            elif mismatch == "attempt_index":
                value = 99
            else:
                value = "wrong"
            evidence = dataclasses.replace(evidence, **{field_name: value})
        elif mismatch == "traceparent":
            request = dataclasses.replace(
                evidence.primary_request,
                traceparent="00-wrong-wrong-01",
            )
            response = dataclasses.replace(
                evidence.primary_response,
                request=dataclasses.replace(request),
            )
            evidence = dataclasses.replace(
                evidence,
                primary_request=request,
                primary_response=response,
            )
        else:
            evidence = _replace_response(evidence, trace_id="wrong")
        return ports.UiActionResult(evidence=evidence)

    result = _run(_flow(), StepwiseFake(mutate=mutate))

    assert result.steps[0].status == ERROR
    assert result.steps[1].status == BLOCKED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("step_id", "wrong"),
        ("attempt_index", 99),
        ("attempt_index", False),
        ("template_path", "wrong"),
        ("bound_logical_path", "wrong"),
        ("actual_path", "wrong"),
        ("trace_id", "wrong"),
        ("is_final", False),
        ("is_final", 1),
    ],
)
def test_primary_response_identity_mismatch_is_structured_error(field, value):
    def mutate(result, permit, index):
        return ports.UiActionResult(evidence=_replace_response(
            result.evidence,
            **{field: value},
        ))

    result = _run(_flow(), StepwiseFake(mutate=mutate))

    assert result.steps[0].status == ERROR
    assert result.steps[1].status == BLOCKED


def test_stale_evidence_replayed_across_runs_is_rejected():
    driver = StepwiseFake()
    first = _run(_flow(), driver)
    stale = ports.UiActionResult(evidence=driver.evidence[0])
    driver.mutate = lambda result, permit, index: stale if index == 2 else result

    second = _run(_flow(), driver)

    assert first.status == PASSED
    assert second.steps[0].status == ERROR
    assert second.steps[1].status == BLOCKED
    assert "execution_id mismatch" in second.steps[0].detail
    assert driver.permits[0].execution_id != driver.permits[2].execution_id


def test_prior_step_evidence_replayed_within_run_is_rejected():
    first_evidence = {}

    def replay(result, permit, index):
        if index == 0:
            first_evidence["result"] = result
            return result
        return first_evidence["result"]

    result = _run(_flow(), StepwiseFake(mutate=replay))

    assert result.steps[0].status == PASSED
    assert result.steps[1].status == ERROR
    assert "replayed" in result.steps[1].detail


def _background(permit, *, correlated=False, path=None):
    traceparent = permit.traceparent if correlated else None
    trace_id = permit.trace_id if correlated else None
    specs = [
        ports.RequestSpec(
            permit.method,
            path or permit.bound_logical_path,
            traceparent=traceparent,
        ),
        ports.RequestSpec("GET", "background/refresh", traceparent=traceparent),
    ]
    responses = [
        ports.RecordedResponse(
            200, {}, {"success": True}, "", trace_id, dataclasses.replace(spec))
        for spec in specs
    ]
    return specs, responses


def test_uncorrelated_background_requests_are_diagnostics_only():
    driver = StepwiseFake(diagnostics=lambda permit: _background(permit))

    result = _run(_flow(), driver)

    assert result.status == PASSED
    assert all(len(e.diagnostic_outgoing) == 2 for e in driver.evidence)
    assert all(c.ok for step in result.steps for c in step.checks if c.point == "request")


def test_matching_background_request_cannot_replace_invalid_primary():
    def mutate(result, permit, index):
        evidence = result.evidence
        bad_request = dataclasses.replace(evidence.primary_request, path="not-the-primary")
        bad_response = dataclasses.replace(
            evidence.primary_response,
            request=dataclasses.replace(bad_request),
            actual_path="not-the-primary",
            bound_logical_path="not-the-primary",
        )
        return ports.UiActionResult(evidence=dataclasses.replace(
            evidence,
            actual_path="not-the-primary",
            primary_request=bad_request,
            primary_response=bad_response,
        ))

    driver = StepwiseFake(
        mutate=mutate,
        diagnostics=lambda permit: _background(permit),
    )

    result = _run(_flow(), driver)

    assert result.steps[0].status == ERROR
    assert result.steps[1].status == BLOCKED


def test_diagnostic_reusing_primary_trace_is_protocol_error():
    driver = StepwiseFake(
        diagnostics=lambda permit: _background(permit, correlated=True),
    )

    result = _run(_flow(), driver)

    assert result.steps[0].status == ERROR
    assert "diagnostic" in result.steps[0].detail


def test_tampered_mock_response_body_is_protocol_error():
    def mutate(result, permit, index):
        response = dataclasses.replace(
            result.evidence.primary_response,
            json={"success": True, "data": {"forged": True}},
        )
        return ports.UiActionResult(evidence=dataclasses.replace(
            result.evidence,
            primary_response=response,
        ))

    result = _run(_flow(), StepwiseFake(mutate=mutate))

    assert result.steps[0].status == ERROR
    assert "mock response" in result.steps[0].detail


def test_nested_mock_bool_int_coercion_is_rejected():
    scenario = _flow()
    scenario.steps[0].expect.response.append(
        Assertion("field_equals", {"field": "enabled", "value": True}))

    def mutate(result, permit, index):
        body = copy.deepcopy(result.evidence.primary_response.json)
        body["data"]["enabled"] = 1
        return ports.UiActionResult(evidence=dataclasses.replace(
            result.evidence,
            primary_response=dataclasses.replace(
                result.evidence.primary_response,
                json=body,
            ),
        ))

    result = _run(scenario, StepwiseFake(mutate=mutate))

    assert result.steps[0].status == ERROR
    assert "mock response" in result.steps[0].detail


def test_request_body_bool_int_coercion_is_rejected():
    def mutate(result, permit, index):
        primary = dataclasses.replace(
            result.evidence.primary_request,
            body={"flag": True},
        )
        recorded_request = dataclasses.replace(primary, body={"flag": 1})
        response = dataclasses.replace(
            result.evidence.primary_response,
            request=recorded_request,
        )
        return ports.UiActionResult(evidence=dataclasses.replace(
            result.evidence,
            primary_request=primary,
            primary_response=response,
        ))

    result = _run(_flow(), StepwiseFake(mutate=mutate))

    assert result.steps[0].status == ERROR
    assert "response.request values differ" in result.steps[0].detail


def test_each_executed_step_has_exactly_one_semantic_action():
    driver = StepwiseFake()
    scenario = _flow(third=True)

    result = _run(scenario, driver)

    assert result.status == PASSED
    assert len(driver.actions) == len(scenario.steps) == 3
    assert [step_id for step_id, _ in driver.actions] == [s.id for s in scenario.steps]


def test_sensitive_payloads_do_not_appear_in_default_representations():
    sentinel = "TOP-SECRET-SENTINEL"
    scenario = _flow()
    scenario.steps[0].expect.response[0] = Assertion(
        "field_equals", {"field": "item_id", "value": sentinel})
    driver = StepwiseFake()

    domain = _run(scenario, driver)
    report = RunReport("sensitive", [domain])

    assert sentinel in driver.permits[0].mock_response["data"]["item_id"]
    assert sentinel in domain.steps[1].resolved_bindings["item_id"]
    assert sentinel not in repr(driver.permits[0])
    assert sentinel not in repr(driver.evidence[0])
    assert sentinel not in repr(report)


def test_binding_views_use_distinct_top_level_mappings():
    driver = StepwiseFake()

    result = _run(_flow(), driver)

    assert result.steps[1].resolved_bindings == driver.permits[1].resolved_bindings
    assert result.steps[1].resolved_bindings is not driver.permits[1].resolved_bindings


def test_ui_action_result_enforces_completed_or_skipped_exclusivity():
    with pytest.raises(ValueError, match="exactly one"):
        ports.UiActionResult()
    with pytest.raises(ValueError, match="exactly one"):
        ports.UiActionResult(skip_reason="")
    evidence = StepwiseFake()
    completed = _run(_flow(), evidence)
    with pytest.raises(ValueError, match="exactly one"):
        ports.UiActionResult(
            evidence=evidence.evidence[0],
            skip_reason="also skipped",
        )
    assert completed.status == PASSED


def test_new_action_models_are_keyword_only_and_sensitive_fields_are_tagged():
    assert ports.UiActionPermit.__match_args__ == ()
    assert ports.UiActionEvidence.__match_args__ == ()
    assert ports.UiActionResult.__match_args__ == ()
    permit_fields = {field.name: field for field in dataclasses.fields(ports.UiActionPermit)}
    evidence_fields = {field.name: field for field in dataclasses.fields(ports.UiActionEvidence)}
    for name in ("token", "bound_logical_path", "resolved_bindings", "mock_response"):
        assert permit_fields[name].repr is False
        assert permit_fields[name].metadata["sensitive"] is True
    assert permit_fields["resolved_bindings"].compare is False
    assert permit_fields["mock_response"].compare is False
    for name in (
        "permit_token", "bound_logical_path", "actual_path", "primary_request",
        "primary_response",
        "rendered", "diagnostic_outgoing", "diagnostic_recorded",
    ):
        assert evidence_fields[name].repr is False
        assert evidence_fields[name].metadata["sensitive"] is True
    permit = StepwiseFake()
    _run(_flow(), permit)
    altered = dataclasses.replace(
        permit.permits[0],
        resolved_bindings={"different": "value"},
        mock_response={"different": "value"},
    )
    assert altered == permit.permits[0]


def test_stepwise_port_signatures_and_random_secret_size(monkeypatch):
    open_signature = inspect.signature(ports.StepwiseUiDriver.open_stepwise)
    assert list(open_signature.parameters) == [
        "self", "scenario", "session", "mode",
    ]
    assert open_signature.parameters["mode"].kind is inspect.Parameter.KEYWORD_ONLY
    assert list(inspect.signature(ports.StepwiseUiDriver.perform_step).parameters) == [
        "self", "scenario", "step", "context", "permit",
    ]
    assert list(inspect.signature(ports.StepwiseUiDriver.close_stepwise).parameters) == [
        "self", "context",
    ]
    sizes = []
    original = ui_stepwise.secrets.token_bytes

    def token_bytes(size):
        sizes.append(size)
        return original(size)

    monkeypatch.setattr(ui_stepwise.secrets, "token_bytes", token_bytes)
    result = _run(_flow(), StepwiseFake())

    assert result.status == PASSED
    assert sizes.count(32) == 1


def test_e2e_multistep_remains_unsupported_even_for_stepwise_driver():
    driver = StepwiseFake()

    result = e2e.run(
        _flow(),
        auth=FakeAuth(),
        ui=driver,
        state=None,
        recorder=FakeRecorder(),
        normalizer=FakeNormalizer(),
    )

    assert result.status == DEGRADED
    assert result.skipped == ["multi-step UI not supported"]
    assert driver.open_calls == 0
    assert driver.actions == []
