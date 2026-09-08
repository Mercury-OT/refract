"""Core-owned orchestration for multi-step frontend mock execution.

The adapter receives one authenticated permit at a time. Only evidence that
matches that permit is normalized and made available to later bindings.
"""
import copy
import hashlib
import hmac
import json
import secrets

from refracto import ports
from refracto.contract import store
from refracto.declaration import binding, values
from refracto.declaration.loader import DeclarationError
from refracto.report import (
    BLOCKED,
    ERROR,
    FAILED,
    PASSED,
    SKIPPED,
    DomainResult,
    StepResult,
)


_MODE = "mock"


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


def _issue_permit(*, secret, execution_id, step, template, bound_values, mock_response):
    traceparent, trace_id = _new_traceparent()
    values_to_sign = {
        "execution_id": execution_id,
        "action_id": secrets.token_hex(16),
        "request_id": secrets.token_hex(16),
        "step_id": step.id,
        "attempt_index": 0,
        "mode": _MODE,
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
        mock_response=copy.deepcopy(mock_response),
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


def _require_equal(name, actual, expected):
    if not _strict_equal(actual, expected):
        raise ValueError(f"UI action evidence {name} mismatch")


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


def _request_values_equal(actual, expected):
    if not isinstance(actual, ports.RequestSpec) or not isinstance(expected, ports.RequestSpec):
        return False
    return all(
        _strict_equal(getattr(actual, name), getattr(expected, name))
        for name in ("method", "path", "body", "traceparent")
    )


def _validate_diagnostics(evidence, permit):
    for request in evidence.diagnostic_outgoing:
        if request.traceparent == permit.traceparent:
            raise ValueError("diagnostic outgoing request reused the primary trace correlation")
    for response in evidence.diagnostic_recorded:
        if (
            response.trace_id == permit.trace_id
            or response.request.traceparent == permit.traceparent
        ):
            raise ValueError("diagnostic response reused the primary trace correlation")


def _validate_evidence(result, permit, secret, retained_mock, accepted_tokens):
    if not isinstance(result, ports.UiActionResult):
        raise TypeError("StepwiseUiDriver.perform_step() must return UiActionResult")
    if result.evidence is None:
        return None

    expected_token = hmac.new(
        secret,
        _signature_payload({
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
        }),
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
    _require_equal("actual_path", evidence.actual_path, permit.bound_logical_path)

    request = evidence.primary_request
    response = evidence.primary_response
    _require_equal("primary request method", request.method, permit.method)
    _require_equal("primary request path", request.path, permit.bound_logical_path)
    _require_equal("primary request traceparent", request.traceparent, permit.traceparent)
    if not _request_values_equal(response.request, request):
        raise ValueError("primary request and response.request values differ")
    _require_equal("response step_id", response.step_id, permit.step_id)
    _require_equal("response attempt_index", response.attempt_index, permit.attempt_index)
    _require_equal("response template_path", response.template_path, permit.template_path)
    _require_equal(
        "response bound_logical_path",
        response.bound_logical_path,
        permit.bound_logical_path,
    )
    _require_equal("response actual_path", response.actual_path, evidence.actual_path)
    _require_equal("response trace_id", response.trace_id, permit.trace_id)
    _require_equal("response is_final", response.is_final, True)
    if not _strict_equal(response.json, retained_mock):
        raise ValueError("primary response body does not match the permitted mock response")
    _validate_diagnostics(evidence, permit)
    accepted_tokens.add(permit.token)
    return evidence


def _mark_close_error(step_results, exc):
    for result in reversed(step_results):
        if result.status != BLOCKED:
            result.status = ERROR
            suffix = f"UI context close failed: {exc}"
            result.detail = f"{result.detail}; {suffix}" if result.detail else suffix
            return


def run(scenario, *, ui, normalizer, auth, eval_frontend, eval_request_shape):
    """Run a multi-step frontend scenario using one core-controlled context."""
    if any(step.poll is not None for step in scenario.steps):
        return DomainResult(
            projection="frontend",
            skipped=["multi-step UI polling not supported"],
        )
    if not isinstance(ui, ports.StepwiseUiDriver):
        return DomainResult(
            projection="frontend",
            skipped=["multi-step UI capability not supported"],
        )

    session = auth.session(scenario.actor) if auth else None
    execution_id = secrets.token_hex(16)
    secret = secrets.token_bytes(32)
    consumer = store.consumer_contract(scenario)
    step_results = []
    prior_norms = {}
    accepted_tokens = set()
    stopped = False

    try:
        context = ui.open_stepwise(scenario, session, mode=_MODE)
    except Exception as exc:
        step_results.append(StepResult(scenario.steps[0].id, ERROR, detail=str(exc)))
        step_results.extend(
            StepResult(step.id, BLOCKED, detail="a prior step stopped the flow")
            for step in scenario.steps[1:]
        )
        return DomainResult(projection="frontend", steps=step_results)

    try:
        for step in scenario.steps:
            if stopped:
                step_results.append(StepResult(
                    step.id,
                    BLOCKED,
                    detail="a prior step stopped the flow",
                ))
                continue

            norm = None
            bound_values = {}
            resolved_bindings = {}
            permit = None
            try:
                bound_values = binding.resolve_bindings(step, prior_norms)
                resolved_bindings = dict(bound_values)
                template = binding.substitute(step.request, bound_values)
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
                    norm = normalizer.normalize(evidence.primary_response)
                    checks = [
                        eval_frontend(
                            assertion,
                            evidence.rendered,
                            bound_values=bound_values,
                            inputs=scenario.inputs,
                        )
                        for assertion in step.expect.frontend
                    ]
                    checks.append(eval_request_shape(template, [evidence.primary_request]))
                    for check in checks:
                        check.step = step.id
                    status = FAILED if any(not check.ok for check in checks) else PASSED
                    sr = StepResult(
                        step.id,
                        status,
                        checks=checks,
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

    return DomainResult(projection="frontend", steps=step_results)
