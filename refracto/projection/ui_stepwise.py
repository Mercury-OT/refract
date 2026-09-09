"""Shared core-owned orchestration for multi-step UI projections.

Frontend mock and e2e live execution use the same fail-fast step loop. The
adapter receives one authenticated permit at a time; only evidence that passes
the core's identity checks may be normalized, recorded, asserted, or exposed to
later bindings.
"""
import copy
import dataclasses
import hashlib
import hmac
import json
import secrets

from refracto import asyncwait, ports
from refracto.contract import store
from refracto.declaration import binding, values
from refracto.declaration.loader import DeclarationError
from refracto.projection import backend as backend_proj
from refracto.report import (
    BLOCKED,
    ERROR,
    FAILED,
    PASSED,
    SKIPPED,
    DomainResult,
    StepResult,
)


_MOCK = "mock"
_LIVE = "live"


def _new_traceparent() -> tuple[str, str]:
    trace_id = secrets.token_hex(16)
    parent_id = secrets.token_hex(8)
    return f"00-{trace_id}-{parent_id}-01", trace_id


def _signature_payload(permit_values: dict) -> bytes:
    payload = [
        permit_values[name]
        for name in (
            "execution_id",
            "action_id",
            "request_id",
            "step_id",
            "attempt_index",
            "mode",
            "method",
            "template_path",
            "bound_logical_path",
            "traceparent",
        )
    ]
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _issue_permit(
    *, secret, execution_id, step, template, bound_values, mode, mock_response
):
    if mode == _MOCK and not isinstance(mock_response, dict):
        raise TypeError("frontend mock permit requires a dict mock_response")
    if mode == _LIVE and mock_response is not None:
        raise TypeError("e2e live permit requires mock_response=None")
    traceparent, trace_id = _new_traceparent()
    values_to_sign = {
        "execution_id": execution_id,
        "action_id": secrets.token_hex(16),
        "request_id": secrets.token_hex(16),
        "step_id": step.id,
        "attempt_index": 0,
        "mode": mode,
        "method": template.method,
        "template_path": step.request.path,
        "bound_logical_path": template.path,
        "traceparent": traceparent,
    }
    token = hmac.new(
        secret,
        _signature_payload(values_to_sign),
        hashlib.sha256,
    ).hexdigest()
    return ports.UiActionPermit(
        **values_to_sign,
        trace_id=trace_id,
        token=token,
        resolved_bindings=dict(bound_values),
        mock_response=(
            copy.deepcopy(mock_response) if mock_response is not None else None
        ),
    )


def _build_step_mock(scenario, step, bound_values, normalizer, consumer):
    key = (step.id, step.request.method, step.request.path)
    shape = consumer.entries[key]
    concrete = {}
    for field_name, declared in shape.response_values.items():
        resolved, error = values.resolve(
            declared,
            bound_values=bound_values,
            inputs=scenario.inputs,
        )
        if error is not None:
            raise DeclarationError(error)
        concrete[field_name] = resolved
    if concrete:
        return normalizer.synthesize(shape.response_fields, concrete)
    return normalizer.synthesize(shape.response_fields)


def _strict_equal(actual, expected):
    """Compare protocol values recursively without Python bool/int coercion."""
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        if len(actual) != len(expected):
            return False
        unmatched = list(expected.items())
        for actual_key, actual_value in actual.items():
            for index, (expected_key, expected_value) in enumerate(unmatched):
                if _strict_equal(actual_key, expected_key):
                    if not _strict_equal(actual_value, expected_value):
                        return False
                    unmatched.pop(index)
                    break
            else:
                return False
        return not unmatched
    if isinstance(actual, (list, tuple)):
        return len(actual) == len(expected) and all(
            _strict_equal(a, e) for a, e in zip(actual, expected)
        )
    return actual == expected


def _require_equal(name, actual, expected):
    if not _strict_equal(actual, expected):
        raise ValueError(f"UI action evidence {name} mismatch")


def _request_values_equal(actual, expected):
    if not isinstance(actual, ports.RequestSpec) or not isinstance(
        expected, ports.RequestSpec
    ):
        return False
    return all(
        _strict_equal(getattr(actual, name), getattr(expected, name))
        for name in ("method", "path", "body", "traceparent")
    )


def _recording_values_equal(actual, expected):
    if not isinstance(actual, ports.RecordedResponse) or not isinstance(
        expected, ports.RecordedResponse
    ):
        return False
    return all(
        _request_values_equal(actual.request, expected.request)
        if field.name == "request"
        else _strict_equal(getattr(actual, field.name), getattr(expected, field.name))
        for field in dataclasses.fields(ports.RecordedResponse)
    )


def _validate_diagnostics(evidence, permit):
    if not isinstance(evidence.diagnostic_outgoing, list) or not isinstance(
        evidence.diagnostic_recorded, list
    ):
        raise TypeError("UI action diagnostics must be lists")
    for request in evidence.diagnostic_outgoing:
        if not isinstance(request, ports.RequestSpec):
            raise TypeError("diagnostic outgoing item must be RequestSpec")
        if _strict_equal(request.traceparent, permit.traceparent):
            raise ValueError(
                "diagnostic outgoing request reused the primary trace correlation"
            )
    for response in evidence.diagnostic_recorded:
        if not isinstance(response, ports.RecordedResponse):
            raise TypeError("diagnostic recorded item must be RecordedResponse")
        if _strict_equal(response.trace_id, permit.trace_id) or _strict_equal(
            response.request.traceparent, permit.traceparent
        ):
            raise ValueError(
                "diagnostic response reused the primary trace correlation"
            )


def _validate_evidence(result, permit, secret, retained_mock, accepted_tokens):
    if not isinstance(result, ports.UiActionResult):
        raise TypeError("StepwiseUiDriver.perform_step() must return UiActionResult")
    if result.evidence is None:
        return None

    expected_token = hmac.new(
        secret,
        _signature_payload(
            {
                "execution_id": permit.execution_id,
                "action_id": permit.action_id,
                "request_id": permit.request_id,
                "step_id": permit.step_id,
                "attempt_index": permit.attempt_index,
                "mode": permit.mode,
                "method": permit.method,
                "template_path": permit.template_path,
                "bound_logical_path": permit.bound_logical_path,
                "traceparent": permit.traceparent,
            }
        ),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(permit.token, expected_token):
        raise ValueError("UI action permit token is invalid")

    evidence = result.evidence
    if evidence.permit_token in accepted_tokens:
        raise ValueError("UI action evidence replayed an already accepted permit")
    for name in (
        "execution_id",
        "action_id",
        "request_id",
        "step_id",
        "attempt_index",
        "mode",
        "method",
        "template_path",
        "bound_logical_path",
    ):
        _require_equal(name, getattr(evidence, name), getattr(permit, name))
    if not hmac.compare_digest(evidence.permit_token, permit.token):
        raise ValueError("UI action evidence permit_token mismatch")
    _require_equal("is_final", evidence.is_final, True)
    if not isinstance(evidence.actual_path, str) or not evidence.actual_path:
        raise ValueError("UI action evidence actual_path must be a non-empty string")

    request = evidence.primary_request
    response = evidence.primary_response
    if not isinstance(request, ports.RequestSpec):
        raise TypeError("UI action evidence primary_request must be RequestSpec")
    if not isinstance(response, ports.RecordedResponse):
        raise TypeError("UI action evidence primary_response must be RecordedResponse")
    _require_equal("primary request method", request.method, permit.method)
    _require_equal("primary request path", request.path, permit.bound_logical_path)
    _require_equal(
        "primary request traceparent", request.traceparent, permit.traceparent
    )
    if not _request_values_equal(response.request, request):
        raise ValueError("primary request and response.request values differ")
    _require_equal("response step_id", response.step_id, permit.step_id)
    _require_equal(
        "response attempt_index", response.attempt_index, permit.attempt_index
    )
    _require_equal(
        "response template_path", response.template_path, permit.template_path
    )
    _require_equal(
        "response bound_logical_path",
        response.bound_logical_path,
        permit.bound_logical_path,
    )
    _require_equal("response actual_path", response.actual_path, evidence.actual_path)
    _require_equal("response trace_id", response.trace_id, permit.trace_id)
    _require_equal("response is_final", response.is_final, True)
    if permit.mode == _MOCK:
        if not isinstance(retained_mock, dict):
            raise TypeError("frontend mock validation requires a retained mock response")
        if not _strict_equal(response.json, retained_mock):
            raise ValueError(
                "primary response body does not match the permitted mock response"
            )
    elif permit.mode == _LIVE:
        if retained_mock is not None or permit.mock_response is not None:
            raise ValueError("e2e live evidence carried a mock response")
    else:
        raise ValueError(f"unsupported stepwise UI mode {permit.mode!r}")
    _validate_diagnostics(evidence, permit)
    accepted_tokens.add(permit.token)
    return evidence


def _record_verified_primary(recorder, response, expected_recordings):
    if recorder is None:
        raise ValueError("e2e live execution requires a Recorder")
    expected = copy.deepcopy(response)
    recorder.record(copy.deepcopy(expected))
    observed = recorder.responses()
    if not isinstance(observed, list):
        raise TypeError("Recorder.responses() must return a list")
    wanted = [*expected_recordings, expected]
    if len(observed) != len(wanted):
        raise ValueError(
            "Recorder response count does not match verified primary recordings"
        )
    for index, (actual, planned) in enumerate(zip(observed, wanted)):
        if not _recording_values_equal(actual, planned):
            raise ValueError(
                f"Recorder response identity/order mismatch at index {index}"
            )
    return copy.deepcopy(observed)


def _validate_state_facts(facts, trace_id):
    if not isinstance(facts, ports.StateFacts):
        raise TypeError("StateProbe.observe() must return StateFacts")
    if not isinstance(facts.trace_id, str) or not facts.trace_id:
        raise ValueError("StateFacts.trace_id must be a non-empty string")
    if not _strict_equal(facts.trace_id, trace_id):
        raise ValueError("StateFacts.trace_id does not match the current action trace")
    return facts


def _assert_live_backend_state_for(
    step,
    state,
    trace_id,
    *,
    state_timeout=30,
    interval=1,
    now=None,
    sleep=None,
    bound_values=None,
    inputs=None,
):
    """Strictly correlate multi-step e2e StateProbe evidence to one action."""
    checks, skipped = [], []
    if not step.expect.backend_state:
        return checks, skipped
    if state is None:
        for assertion in step.expect.backend_state:
            skipped.append(
                f"{assertion.check}({assertion.params}) — no StateProbe "
                "(product has no OTel here)"
            )
        return checks, skipped
    if not isinstance(trace_id, str) or not trace_id:
        raise ValueError("current action trace_id must be a non-empty string")

    def _observe():
        facts = _validate_state_facts(state.observe(trace_id), trace_id)
        ok = all(
            backend_proj._eval_span(
                assertion,
                facts,
                bound_values,
                inputs,
            ).ok
            for assertion in step.expect.backend_state
        )
        return ok, facts

    try:
        result = asyncwait.wait_until(
            _observe,
            timeout=state_timeout,
            interval=interval,
            on_timeout=asyncwait.FAIL,
            now=now,
            sleep=sleep,
        )
        facts = result.value
    except TimeoutError:
        facts = _validate_state_facts(state.observe(trace_id), trace_id)
    checks.extend(
        backend_proj._eval_span(assertion, facts, bound_values, inputs)
        for assertion in step.expect.backend_state
    )
    return checks, skipped


def _mark_close_error(step_results, exc):
    for result in reversed(step_results):
        if result.status != BLOCKED:
            result.status = ERROR
            suffix = f"UI context close failed: {exc}"
            result.detail = f"{result.detail}; {suffix}" if result.detail else suffix
            return


def _blocked_results(steps):
    return [
        StepResult(step.id, BLOCKED, detail="a prior step stopped the flow")
        for step in steps
    ]


def _before_context_error(scenario, projection, exc):
    first, *remaining = scenario.steps
    return DomainResult(
        projection=projection,
        steps=[StepResult(first.id, ERROR, detail=str(exc)), *_blocked_results(remaining)],
    )


def _unsupported_reason(projection):
    if projection == "e2e":
        return "multi-step e2e live capability not supported"
    return "multi-step UI capability not supported"


def run(
    scenario,
    *,
    ui,
    normalizer,
    auth,
    eval_frontend,
    eval_request_shape,
    projection="frontend",
    mode=_MOCK,
    eval_response=None,
    state=None,
    recorder=None,
    resolve_precondition=None,
    poll_config=None,
    now=None,
    sleep=None,
):
    """Run one supported multi-step UI projection in one core-controlled context."""
    if any(step.poll is not None for step in scenario.steps):
        return DomainResult(
            projection=projection,
            skipped=["multi-step UI polling not supported"],
        )
    if not isinstance(ui, ports.StepwiseUiDriver):
        return DomainResult(
            projection=projection,
            skipped=[_unsupported_reason(projection)],
        )
    try:
        supported = ui.supports_stepwise_mode(mode)
    except Exception as exc:
        return _before_context_error(scenario, projection, exc)
    if supported is not True:
        return DomainResult(
            projection=projection,
            skipped=[_unsupported_reason(projection)],
        )
    if projection == "e2e" and scenario.precondition and resolve_precondition is None:
        return _before_context_error(
            scenario,
            projection,
            ValueError("multi-step e2e preconditions require resolve_precondition"),
        )
    if projection == "e2e" and auth is None:
        return _before_context_error(
            scenario,
            projection,
            ValueError("multi-step e2e live execution requires an Authenticator"),
        )

    try:
        session = auth.session(scenario.actor) if auth else None
        if projection == "e2e":
            for ref in scenario.precondition:
                resolve_precondition(ref, session)
    except Exception as exc:
        return _before_context_error(scenario, projection, exc)

    execution_id = secrets.token_hex(16)
    secret = secrets.token_bytes(32)
    consumer = store.consumer_contract(scenario) if mode == _MOCK else None
    step_results = []
    prior_norms = {}
    accepted_tokens = set()
    verified_recordings = []
    stopped = False

    try:
        context = ui.open_stepwise(scenario, session, mode=mode)
    except Exception as exc:
        return _before_context_error(scenario, projection, exc)

    try:
        for step in scenario.steps:
            if stopped:
                step_results.append(
                    StepResult(
                        step.id,
                        BLOCKED,
                        detail="a prior step stopped the flow",
                    )
                )
                continue

            norm = None
            bound_values = {}
            resolved_bindings = {}
            permit = None
            try:
                bound_values = binding.resolve_bindings(step, prior_norms)
                resolved_bindings = dict(bound_values)
                template = binding.substitute(step.request, bound_values)
                mock_response = None
                retained_mock = None
                if mode == _MOCK:
                    mock_response = _build_step_mock(
                        scenario,
                        step,
                        bound_values,
                        normalizer,
                        consumer,
                    )
                    retained_mock = copy.deepcopy(mock_response)
                permit = _issue_permit(
                    secret=secret,
                    execution_id=execution_id,
                    step=step,
                    template=template,
                    bound_values=bound_values,
                    mode=mode,
                    mock_response=mock_response,
                )
                action_result = ui.perform_step(scenario, step, context, permit)
                evidence = _validate_evidence(
                    action_result,
                    permit,
                    secret,
                    retained_mock,
                    accepted_tokens,
                )
                if evidence is None:
                    sr = StepResult(
                        step.id,
                        SKIPPED,
                        skipped=[action_result.skip_reason],
                        trace_id=permit.trace_id,
                    )
                else:
                    # Isolate the identity-validated recording from mutable
                    # normalizer input. The normalizer receives its own copy;
                    # Recorder integrity is checked against the protected one.
                    protected_response = copy.deepcopy(evidence.primary_response)
                    norm = normalizer.normalize(copy.deepcopy(protected_response))
                    if mode == _LIVE:
                        verified_recordings = _record_verified_primary(
                            recorder,
                            protected_response,
                            verified_recordings,
                        )

                    checks = [
                        eval_frontend(
                            assertion,
                            evidence.rendered,
                            bound_values=bound_values,
                            inputs=scenario.inputs,
                        )
                        for assertion in step.expect.frontend
                    ]
                    checks.append(
                        eval_request_shape(template, [evidence.primary_request])
                    )
                    skipped = []
                    if mode == _LIVE:
                        if eval_response is None:
                            raise ValueError(
                                "e2e live execution requires a response evaluator"
                            )
                        checks.extend(
                            eval_response(
                                assertion,
                                norm,
                                bound_values=bound_values,
                                inputs=scenario.inputs,
                            )
                            for assertion in step.expect.response
                        )
                        state_checks, skipped = _assert_live_backend_state_for(
                            step,
                            state,
                            permit.trace_id,
                            state_timeout=(
                                poll_config.timeout if poll_config is not None else 30
                            ),
                            interval=(
                                poll_config.interval if poll_config is not None else 1
                            ),
                            now=now,
                            sleep=sleep,
                            bound_values=bound_values,
                            inputs=scenario.inputs,
                        )
                        checks.extend(state_checks)
                    for check in checks:
                        check.step = step.id
                    status = FAILED if any(not check.ok for check in checks) else PASSED
                    sr = StepResult(
                        step.id,
                        status,
                        checks=checks,
                        skipped=skipped,
                        trace_id=permit.trace_id,
                    )
            except Exception as exc:
                sr = StepResult(
                    step.id,
                    ERROR,
                    detail=str(exc),
                    trace_id=permit.trace_id if permit is not None else None,
                )

            sr.resolved_bindings = resolved_bindings
            step_results.append(sr)
            if norm is not None:
                prior_norms[step.id] = norm
            if sr.status in (FAILED, ERROR, SKIPPED):
                stopped = True
    finally:
        try:
            ui.close_stepwise(context)
        except Exception as exc:
            _mark_close_error(step_results, exc)

    return DomainResult(
        projection=projection,
        steps=step_results,
        provider_recordings=verified_recordings if mode == _LIVE else [],
    )
