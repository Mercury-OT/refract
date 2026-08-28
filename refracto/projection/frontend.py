"""Frontend projection.

Drive the UI against a mock backend generated from the consumer contract and
assert frontend rendering plus outgoing-request shape. This projection does not
use a real backend or a state probe.
"""
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED
from refracto.contract import store
from refracto.declaration import values
from refracto.declaration.loader import DeclarationError


def build_mock(scenario, normalizer) -> dict:
    consumer = store.consumer_contract(scenario)
    # Consumer contract entries are keyed on (step_id, method, template_path).
    # The mock presented to UI drivers is keyed on (method, path). Frontend and
    # e2e projections only run single-step scenarios, so this key shape remains
    # sufficient here.
    mocks = {}
    for (_step_id, method, path), shape in consumer.entries.items():
        concrete = {}
        for field, declared in shape.response_values.items():
            resolved, error = values.resolve(declared, inputs=scenario.inputs)
            if error is not None:
                raise DeclarationError(error)
            concrete[field] = resolved
        if concrete:
            mocks[(method, path)] = normalizer.synthesize(shape.response_fields, concrete)
        else:
            # Preserve compatibility for adapters implementing the original
            # one-argument synthesizer until they opt into value assertions.
            mocks[(method, path)] = normalizer.synthesize(shape.response_fields)
    return mocks


def _objects_at(rendered, anchor):
    anchor_result = rendered.get(anchor, {})
    identified = anchor_result.get("identified", [])
    anonymous = anchor_result.get("anonymous", [])
    return identified, anonymous


def _eval_frontend(assertion, rendered, bound_values=None, inputs=None):
    anchor = assertion.params["anchor"]
    identified, anonymous = _objects_at(rendered, anchor)
    count = len(identified) + len(anonymous)
    if assertion.check == "visible":
        ok = count > 0
        return CheckResult("frontend", "visible", ok, "" if ok else f"{anchor} not visible")
    if assertion.check == "count_gt":
        n = assertion.params["n"]
        ok = count > n
        return CheckResult("frontend", "count_gt", ok,
                           "" if ok else f"{anchor} count {count} !> {n}")
    if assertion.check == "object_field_equals":
        object_id, id_error = values.resolve(
            assertion.params["id"], bound_values=bound_values, inputs=inputs)
        if id_error is not None:
            return CheckResult("frontend", "object_field_equals", False, id_error)
        target = next((
            obj for obj in identified
            if values.equal(obj.get("id"), object_id)
        ), None)
        if target is None:
            return CheckResult(
                "frontend", "object_field_equals", False,
                f"no identified object id={object_id!r} at anchor {anchor!r}")
        expected, value_error = values.resolve(
            assertion.params["value"], bound_values=bound_values, inputs=inputs)
        if value_error is not None:
            return CheckResult("frontend", "object_field_equals", False, value_error)
        fields = target["fields"]
        present = assertion.params["field"] in fields
        observed = fields.get(assertion.params["field"])
        ok = present and values.equal(observed, expected)
        if ok:
            detail = ""
        elif present:
            detail = (
                f"id={object_id!r} field={assertion.params['field']!r} "
                f"expected={expected!r} observed={observed!r}"
            )
        else:
            detail = (
                f"id={object_id!r} field={assertion.params['field']!r} "
                f"expected={expected!r} observed=<missing>"
            )
        return CheckResult("frontend", "object_field_equals", ok, detail)
    if assertion.check == "no_anonymous":
        ok = not anonymous
        return CheckResult(
            "frontend", "no_anonymous", ok,
            "" if ok else f"anchor {anchor!r} has {len(anonymous)} anonymous object(s)")
    return CheckResult("frontend", assertion.check, False, "unknown frontend check")


def _eval_request_shape(request, outgoing):
    ok = any(o.method == request.method and o.path == request.path for o in outgoing)
    return CheckResult("request", "request", ok,
                       "" if ok else f"UI did not send {request.method} {request.path}")


def run(scenario, *, ui, normalizer, auth=None):
    if len(scenario.steps) != 1:
        return DomainResult(projection="frontend",
                            skipped=["multi-step UI not supported"])
    step = scenario.steps[0]
    session = auth.session(scenario.actor) if auth else None
    mock = build_mock(scenario, normalizer)
    result = ui.run_intent(scenario, session, mock)
    checks = [
        _eval_frontend(a, result.rendered, inputs=scenario.inputs)
        for a in step.expect.frontend
    ]
    if step.request is not None:
        checks.append(_eval_request_shape(step.request, result.outgoing))
    for c in checks:
        c.step = step.id
    status = FAILED if any(not c.ok for c in checks) else PASSED
    return DomainResult(projection="frontend",
                        steps=[StepResult(step.id, status, checks=checks)])
