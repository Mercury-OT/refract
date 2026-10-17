"""Backend projection.

Authenticate, resolve and send declared request steps, evaluate response
assertions, and evaluate backend-state assertions through the StateProbe port.
If no StateProbe is wired, declared backend-state assertions degrade visibly
instead of reading as a full pass.
"""
import dataclasses
import copy
import secrets
import time
from refracto import asyncwait
from refracto.normalization import normalize_response
from refracto.declaration import binding
from refracto.declaration import values
from refracto.declaration import collections
from refracto.declaration import http_status
from refracto.report import CheckResult, DomainResult, StepResult, ResponseOrigin, PASSED, FAILED, SKIPPED, BLOCKED, ERROR
from refracto.projection.continuation import FlowState

_NO_SESSION = object()


def gen_traceparent() -> str:
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def _eval_response(assertion, norm, bound_values=None, inputs=None, *, observed_status=None):
    if assertion.check in http_status.CHECKS:
        observed = http_status.require_observed(observed_status)
        expected = http_status.allowed(assertion)
        ok = observed in expected
        return CheckResult("response", assertion.check, ok,
                           "" if ok else http_status.mismatch(expected, observed))
    if assertion.check == "collection_matching_count":
        params = assertion.params
        ok, detail = collections.evaluate(
            norm.fields, params["field"], params["matching"], params["count"],
            bound_values=bound_values, inputs=inputs)
        return CheckResult("response", assertion.check, ok, detail)
    if assertion.check == "success":
        ok = norm.succeeded
        return CheckResult("response", "success", ok, "" if ok else f"not succeeded (status {norm.status})")
    if assertion.check == "failure":
        ok = not norm.succeeded
        return CheckResult(
            "response",
            "failure",
            ok,
            "" if ok else f"expected failure but succeeded (status {norm.status})",
        )
    if assertion.check == "has":
        field = assertion.params["field"]
        present = field in norm.fields
        return CheckResult("response", "has", present, "" if present else f"missing field {field!r}")
    if assertion.check == "field_absent":
        field = assertion.params["field"]
        absent = field not in norm.fields
        return CheckResult(
            "response",
            "field_absent",
            absent,
            "" if absent else f"unexpected field {field!r} present",
        )
    if assertion.check == "field_equals":
        field = assertion.params["field"]
        expected, ref_error = values.resolve(
            assertion.params["value"], bound_values=bound_values, inputs=inputs)
        if ref_error is not None:
            return CheckResult("response", "field_equals", False, ref_error)
        present = field in norm.fields
        observed = norm.fields.get(field)
        ok = present and values.equal(observed, expected)
        if ok:
            detail = ""
        elif present:
            detail = f"field={field!r} expected={expected!r} observed={observed!r}"
        else:
            detail = f"field={field!r} expected={expected!r} observed=<missing>"
        return CheckResult("response", "field_equals", ok, detail)
    return CheckResult("response", assertion.check, False, "unknown response check")


def _eval_span(assertion, facts, bound_values=None, inputs=None):
    # Consider every matching span with the requested name. A repeated operation,
    # parent/child pair, or retry must not collapse into one observation.
    name = assertion.params["span"]
    matching = [s for s in facts.spans if s.name == name]
    if assertion.check == "span_exists":
        ok = bool(matching)
        return CheckResult("backend_state", "span_exists", ok,
                           "" if ok else f"no span {name!r}")
    if assertion.check == "span_attr":
        if not matching:
            return CheckResult("backend_state", "span_attr", False, f"no span {name!r}")
        attr, op = assertion.params["attr"], assertion.params["op"]
        val, ref_error = values.resolve(
            assertion.params["value"], bound_values=bound_values, inputs=inputs)
        if ref_error is not None:
            return CheckResult("backend_state", "span_attr", False, ref_error)
        observed = [s.attributes.get(attr) for s in matching]
        try:
            ok = any(a is not None and _cmp(a, op, val) for a in observed)
        except TypeError:
            return CheckResult("backend_state", "span_attr", False,
                               f"{name}.{attr} in {observed} cannot be compared with {op} {val!r}")
        return CheckResult("backend_state", "span_attr", ok,
                           "" if ok else f"no {name!r} span with {attr} {op} {val} (observed {attr}={observed})")
    return CheckResult("backend_state", assertion.check, False, "unknown state check")


def _cmp(a, op, b):
    """Compare two values with the given operator."""
    if op == ">":
        return a > b
    elif op == ">=":
        return a >= b
    elif op == "<":
        return a < b
    elif op == "<=":
        return a <= b
    elif op == "==":
        return values.equal(a, b)
    else:
        raise ValueError(f"unknown comparison operator: {op!r}")


def assert_backend_state_for(step, state, trace_id, *, state_timeout=30, interval=1,
                              now=None, sleep=None, bound_values=None, inputs=None):
    """Evaluate a step's backend-state assertions.

    * `state is None` -> visible degradation
    * `trace_id is None` with declared expectations -> failing check
    * otherwise poll on the assertion predicate until it holds or times out

    `bound_values` carries this step's already-resolved `bind` values, used to
    resolve any `span_attr.value` that references a bound placeholder.
    """
    checks, skipped = [], []
    if not step.expect.backend_state:
        return checks, skipped
    if state is None:
        for a in step.expect.backend_state:
            # Resolved assertion parameters can contain sensitive binding values.
            # Preserve the unmet check and degradation without echoing its data.
            skipped.append(f"{a.check} — no StateProbe (backend-state evidence unavailable)")
        return checks, skipped
    if trace_id is None:
        checks.append(CheckResult(point="backend_state", check="_no_trace_id", ok=False,
            detail="backend_state declared but no trace id was captured from the execution"))
        return checks, skipped

    # Poll on the full backend-state predicate, not merely on span-name presence.
    def _poll():
        facts = state.observe(trace_id)
        ok = all(_eval_span(a, facts, bound_values, inputs).ok for a in step.expect.backend_state)
        return (ok, facts)

    try:
        res = asyncwait.wait_until(_poll, timeout=state_timeout, interval=interval,
                                   on_timeout=asyncwait.FAIL, now=now, sleep=sleep)
    except asyncwait.WaitTimeout:
        # On timeout, report the specific failing assertions against the most
        # recent observation rather than a generic timeout marker.
        facts = state.observe(trace_id)
        for a in step.expect.backend_state:
            checks.append(_eval_span(a, facts, bound_values, inputs))
    else:
        for a in step.expect.backend_state:
            checks.append(_eval_span(a, res.value, bound_values, inputs))
    return checks, skipped


def _subset(declared, actual):
    """Return whether `declared` is contained within `actual`.

    Maps: every declared key must exist in `actual` with a subset value.
    Lists and scalars: exact, type-strict equality.

    This protects the declared transport contract while still allowing an
    adapter resolver to add undeclared request details.
    """
    if isinstance(declared, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _subset(v, actual[k]) for k, v in declared.items())
    if isinstance(declared, list):
        return isinstance(actual, list) and len(declared) == len(actual) and all(
            _subset(a, b) for a, b in zip(declared, actual))
    return values.equal(declared, actual)


def _check_option_b(step, template, spec):
    """Enforce request ownership.

    A resolver may augment undeclared transport details, but it must not change
    the declared method or override/drop a declared body field. Actual-path
    mapping remains an adapter-conformance concern, not a core concern.
    """
    if step.request.method.upper() != spec.method.upper():
        raise ValueError(
            f"resolver changed declared method {step.request.method!r} -> {spec.method!r}")
    if not values.equal(template.body or {}, spec.body or {}):
        raise ValueError(
            "resolver changed declared business body; transport mapping must not invent values")


def _run_poll_step(step, template, spec, api, session, recorder, normalizer, state,
                    poll_config, now, sleep, bound_values=None, inputs=None):
    """Poll a step until its response assertions pass.

    The stop condition is response-only. Once the step becomes ready, evaluate
    the full expectation set against the final attempt. Each attempt gets its
    own trace identity and its own recorded RequestSpec.
    """
    attempts = {"n": 0}
    last = {}

    def _attempt():
        traceparent = gen_traceparent()
        # Each attempt gets its own RequestSpec instance so earlier recordings
        # keep their original trace identity.
        attempt_spec = dataclasses.replace(spec, traceparent=traceparent)
        resp = api.send(attempt_spec, session)
        _require_live_response(resp)

        resp.step_id = step.id
        resp.attempt_index = attempts["n"]
        resp.is_final = False
        resp.template_path = step.request.declared_path or step.request.path
        resp.bound_logical_path = template.path
        resp.actual_path = attempt_spec.path
        try:
            observed_status = _capture_status(step, resp)
            norm = normalize_response(normalizer, resp)
            ok = all(_eval_response(a, norm, bound_values, inputs, observed_status=observed_status).ok
                     for a in step.expect.response)
        except Exception:
            recorder.record(copy.deepcopy(resp))
            raise
        resp.is_final = bool(ok)
        recorder.record(copy.deepcopy(resp))
        attempts["n"] += 1
        last["resp"], last["norm"], last["traceparent"] = resp, norm, traceparent
        last["status"] = observed_status
        return ok, (resp, norm, traceparent, observed_status)

    timeout = poll_config.timeout if poll_config else 30
    interval = poll_config.interval if poll_config else 1
    on_timeout = asyncwait.FAIL if step.poll.on_timeout == "FAIL" else asyncwait.SKIP

    try:
        result = asyncwait.wait_until(_attempt, timeout=timeout, interval=interval,
                                       on_timeout=on_timeout, now=now, sleep=sleep)
    except asyncwait.WaitTimeout:
        resp, norm, traceparent = last["resp"], last["norm"], last["traceparent"]
        response_checks = [
            _eval_response(a, norm, bound_values, inputs, observed_status=last["status"])
            for a in step.expect.response
        ]
        for c in response_checks:
            c.step = step.id
        trace_id = resp.trace_id or traceparent.split("-")[1]
        return StepResult(step.id, FAILED, checks=response_checks,
                          attempts=attempts["n"], trace_id=trace_id,
                          response_origin=ResponseOrigin(step.id, attempts["n"] - 1, False, True)), norm

    if result.skipped:
        resp, norm, traceparent = last["resp"], last["norm"], last["traceparent"]
        trace_id = resp.trace_id or traceparent.split("-")[1]
        return StepResult(step.id, SKIPPED, skipped=["poll timed out (SKIP)"],
                          attempts=attempts["n"], trace_id=trace_id,
                          response_origin=ResponseOrigin(step.id, attempts["n"] - 1, False, True)), norm

    winning_resp, winning_norm, winning_traceparent, winning_status = result.value
    winning_resp.is_final = True

    response_checks = [
        _eval_response(a, winning_norm, bound_values, inputs, observed_status=winning_status)
        for a in step.expect.response
    ]
    for c in response_checks:
        c.step = step.id

    final_trace_id = winning_resp.trace_id or winning_traceparent.split("-")[1]
    # Business polling and backend-state polling use independent timing budgets.
    state_checks, skips = assert_backend_state_for(
        step, state, final_trace_id, now=now, sleep=sleep,
        bound_values=bound_values, inputs=inputs)
    for c in state_checks:
        c.step = step.id

    status = FAILED if any(not c.ok for c in response_checks + state_checks) else PASSED
    return StepResult(step.id, status, checks=response_checks + state_checks,
                      skipped=skips, attempts=attempts["n"],
                      trace_id=final_trace_id), winning_norm


def _run_step(step, template, spec, api, session, recorder, normalizer, state,
              poll_config, now, sleep, bound_values=None, inputs=None):
    """Send one step request and evaluate its expectation set."""
    if step.poll is not None:
        return _run_poll_step(step, template, spec, api, session, recorder,
                               normalizer, state, poll_config, now, sleep,
                               bound_values, inputs)

    spec.traceparent = gen_traceparent()
    resp = api.send(spec, session)
    _require_live_response(resp)

    # Record the step identity and the three path identities used by the run.
    resp.step_id = step.id
    resp.attempt_index = 0
    resp.is_final = True
    resp.template_path = step.request.declared_path or step.request.path
    resp.bound_logical_path = template.path
    resp.actual_path = spec.path
    recorder.record(copy.deepcopy(resp))

    observed_status = _capture_status(step, resp)
    norm = normalize_response(normalizer, resp)

    response_checks = [
        _eval_response(a, norm, bound_values, inputs, observed_status=observed_status)
        for a in step.expect.response
    ]
    if step.request_asserted:
        response_checks.insert(0, CheckResult("request", "request", True,
            "declared transport request sent; UI behavior is not checked"))
    for c in response_checks:
        c.step = step.id

    trace_id = resp.trace_id or spec.traceparent.split("-")[1]

    # Business polling and backend-state polling use independent timing budgets.
    state_checks, skips = assert_backend_state_for(
        step, state, trace_id, now=now, sleep=sleep,
        bound_values=bound_values, inputs=inputs)
    for c in state_checks:
        c.step = step.id

    status = FAILED if any(not c.ok for c in response_checks + state_checks) else (PASSED if response_checks + state_checks else "COMPLETED")
    return StepResult(step.id, status, checks=response_checks + state_checks,
                      skipped=skips, attempts=1, trace_id=trace_id), norm


def _capture_status(step, response):
    """Capture the transport value before normalization, when it is required."""
    observed = getattr(response, "status", None)
    if any(a.check in http_status.CHECKS for a in step.expect.response):
        return http_status.require_observed(observed)
    return observed


def _require_live_response(response):
    """Never promote an explicitly marked fixture into live provider evidence."""
    if response.mock_fixture_id is not None:
        raise ValueError("live API response cannot contain a mock fixture marker")


def execute_api_step(scenario, step, *, api, state, recorder, resolve_request,
                     normalizer, auth=None, session=_NO_SESSION, poll_config=None,
                     now=None, sleep=None, bound_values=None):
    """Execute a prepared explicit request (also reused by the e2e loop)."""
    if step.action == "request" and step.expect.frontend:
        raise ValueError("direct API action with UI assertions is not supported")
    if session is _NO_SESSION:
        if auth is None:
            raise ValueError("Authenticator is required")
        session = auth.session(scenario.actor)
    template = step.request
    if template is None:
        raise ValueError("request action has no request")
    # The mapper receives an independent value and cannot mutate the declaration
    # to make its own changed output compare equal.
    spec = resolve_request(scenario, copy.deepcopy(step), copy.deepcopy(template))
    _check_option_b(step, template, spec)
    return _run_step(step, template, spec, api, session, recorder, normalizer,
                     state, poll_config, now, sleep, bound_values, scenario.inputs)


def run(scenario, *, auth, api, state, recorder, resolve_request, normalizer,
        poll_config=None, now=None, sleep=None):

    step_results = []
    prior_norms = {}
    flow = FlowState()
    session = _NO_SESSION
    # Validate the complete flow before authentication, waits, mapping or sends.
    # A later unsupported step must not allow earlier steps to have side effects.
    unsupported = None
    if any(s.action == "request" and s.expect.frontend for s in scenario.steps):
        unsupported = "direct API action with UI assertions is not supported"
    elif any(s.request is None and (s.expect.backend_state or s.expect.response) for s in scenario.steps):
        unsupported = "requestless backend_state has no correlation source"
    for step in scenario.steps:
        blocked = flow.blocked(step)
        if blocked is not None:
            step_results.append(blocked)
            continue
        norm = None
        bound_values = {}
        resolved_bindings = {}
        prepared_ok = False
        try:
            if unsupported:
                raise ValueError(unsupported)
            if step.action == "wait":
                (sleep or time.sleep)(step.duration / 1000)
                sr = StepResult(step.id, "COMPLETED", not_checked=(
                    ["UI checks are outside backend projection"] if step.expect.frontend else []))
                flow.finish(step, sr)
                step_results.append(sr)
                continue
            if step.request is None:
                sr = StepResult(step.id, "NOT_APPLICABLE",
                    not_checked=["UI action/checks are outside backend projection"])
                flow.finish(step, sr)
                step_results.append(sr)
                continue
            prepared, bound_values = binding.prepare_step(step, scenario, prior_norms)
            prepared_ok = True
            resolved_bindings = dict(bound_values)
            if session is _NO_SESSION:
                if auth is None:
                    raise ValueError("Authenticator is required")
                session = auth.session(scenario.actor)
            sr, norm = execute_api_step(scenario, prepared, api=api, state=state,
                recorder=recorder, resolve_request=resolve_request, normalizer=normalizer,
                session=session, poll_config=poll_config, now=now, sleep=sleep,
                bound_values=bound_values)
            if step.action != "request" or step.expect.frontend:
                sr.not_checked.append("UI actions/checks are outside backend projection")
        except binding.DependencyUnavailable as exc:
            sr = (StepResult(step.id, ERROR, detail=str(exc)) if prepared_ok else
                  StepResult(step.id, BLOCKED, detail=str(exc), blocked_by=exc.sources))
            norm = None
        except Exception as exc:
            sr = StepResult(step.id, ERROR, detail=str(exc))
            norm = None
        sr.resolved_bindings = resolved_bindings
        flow.finish(step, sr, norm)
        step_results.append(sr)
        if norm is not None:
            prior_norms[step.id] = norm

    try:
        recordings = recorder.responses()
    except Exception as exc:
        step_results.append(StepResult("_recorder", ERROR, detail=str(exc)))
        recordings = []
    return DomainResult(projection="backend", steps=step_results,
                        provider_recordings=recordings)
