"""Backend projection.

Authenticate, resolve and send declared request steps, evaluate response
assertions, and evaluate backend-state assertions through the StateProbe port.
If no StateProbe is wired, declared backend-state assertions degrade visibly
instead of reading as a full pass.
"""
import dataclasses
import secrets
from refracto import asyncwait
from refracto.declaration import binding
from refracto.declaration import values
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED, SKIPPED, BLOCKED, ERROR


def gen_traceparent() -> str:
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def _eval_response(assertion, norm, bound_values=None, inputs=None):
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
        return a == b
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
            skipped.append(f"{a.check}({a.params}) — no StateProbe (product has no OTel here)")
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
    except TimeoutError:
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
    if type(declared) is not type(actual):
        return False
    return declared == actual


def _check_option_b(step, template, spec):
    """Enforce request ownership.

    A resolver may augment undeclared transport details, but it must not change
    the declared method or override/drop a declared body field. Actual-path
    mapping remains an adapter-conformance concern, not a core concern.
    """
    if step.request.method.upper() != spec.method.upper():
        raise ValueError(
            f"resolver changed declared method {step.request.method!r} -> {spec.method!r}")
    if template.body is not None and not _subset(template.body, spec.body or {}):
        raise ValueError(
            f"resolver overrode/dropped a declared body field: "
            f"declared={template.body!r} actual={spec.body!r}")


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

        resp.step_id = step.id
        resp.attempt_index = attempts["n"]
        resp.is_final = False
        resp.template_path = step.request.path
        resp.bound_logical_path = template.path
        resp.actual_path = attempt_spec.path
        recorder.record(resp)

        norm = normalizer.normalize(resp)
        attempts["n"] += 1
        last["resp"], last["norm"], last["traceparent"] = resp, norm, traceparent

        ok = all(
            _eval_response(a, norm, bound_values, inputs).ok
            for a in step.expect.response
        )
        return ok, (resp, norm, traceparent)

    timeout = poll_config.timeout if poll_config else 30
    interval = poll_config.interval if poll_config else 1
    on_timeout = asyncwait.FAIL if step.poll.on_timeout == "FAIL" else asyncwait.SKIP

    try:
        result = asyncwait.wait_until(_attempt, timeout=timeout, interval=interval,
                                       on_timeout=on_timeout, now=now, sleep=sleep)
    except TimeoutError:
        resp, norm, traceparent = last["resp"], last["norm"], last["traceparent"]
        response_checks = [
            _eval_response(a, norm, bound_values, inputs) for a in step.expect.response
        ]
        for c in response_checks:
            c.step = step.id
        trace_id = resp.trace_id or traceparent.split("-")[1]
        return StepResult(step.id, FAILED, checks=response_checks,
                          attempts=attempts["n"], trace_id=trace_id), norm

    if result.skipped:
        resp, norm, traceparent = last["resp"], last["norm"], last["traceparent"]
        trace_id = resp.trace_id or traceparent.split("-")[1]
        return StepResult(step.id, SKIPPED, skipped=["poll timed out (SKIP)"],
                          attempts=attempts["n"], trace_id=trace_id), norm

    winning_resp, winning_norm, winning_traceparent = result.value
    winning_resp.is_final = True

    response_checks = [
        _eval_response(a, winning_norm, bound_values, inputs)
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

    # Record the step identity and the three path identities used by the run.
    resp.step_id = step.id
    resp.attempt_index = 0
    resp.is_final = True
    resp.template_path = step.request.path
    resp.bound_logical_path = template.path
    resp.actual_path = spec.path
    recorder.record(resp)

    norm = normalizer.normalize(resp)

    response_checks = [
        _eval_response(a, norm, bound_values, inputs) for a in step.expect.response
    ]
    for c in response_checks:
        c.step = step.id

    trace_id = resp.trace_id or spec.traceparent.split("-")[1]

    # Business polling and backend-state polling use independent timing budgets.
    state_checks, skips = assert_backend_state_for(
        step, state, trace_id, now=now, sleep=sleep,
        bound_values=bound_values, inputs=inputs)
    for c in state_checks:
        c.step = step.id

    status = FAILED if any(not c.ok for c in response_checks + state_checks) else PASSED
    return StepResult(step.id, status, checks=response_checks + state_checks,
                      skipped=skips, attempts=1, trace_id=trace_id), norm


def run(scenario, *, auth, api, state, recorder, resolve_request, normalizer,
        resolve_precondition=None, poll_config=None, now=None, sleep=None):
    session = auth.session(scenario.actor)
    if resolve_precondition:
        for ref in scenario.precondition:
            resolve_precondition(ref, session)

    step_results = []
    prior_norms = {}
    stopped = False
    for step in scenario.steps:
        if stopped:
            step_results.append(StepResult(step.id, BLOCKED,
                detail="a prior step stopped the flow"))
            continue
        norm = None
        try:
            bound_values = binding.resolve_bindings(step, prior_norms)
            template = binding.substitute(step.request, bound_values)
            spec = resolve_request(scenario, step, template)
            _check_option_b(step, template, spec)
            sr, norm = _run_step(step, template, spec, api, session, recorder,
                                  normalizer, state, poll_config, now, sleep,
                                  bound_values, scenario.inputs)
        except Exception as exc:
            sr = StepResult(step.id, ERROR, detail=str(exc))
        step_results.append(sr)
        if norm is not None:
            prior_norms[step.id] = norm
        if sr.status in (FAILED, ERROR, SKIPPED):
            stopped = True

    return DomainResult(projection="backend", steps=step_results,
                        provider_recordings=recorder.responses())
