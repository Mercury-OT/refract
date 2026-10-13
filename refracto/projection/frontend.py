"""Frontend projection.

Drive the UI against an explicitly supplied mock plan and
assert frontend rendering plus outgoing-request shape. This projection does not
use a real backend or a state probe.
"""
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED
from refracto.declaration import values
from refracto.projection import ui_stepwise


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
        n = assertion.params["count"]
        ok = count > n
        return CheckResult("frontend", "count_gt", ok,
                           "" if ok else f"{anchor} count {count} !> {n}")
    if assertion.check == "objects_matching_count":
        expected, value_error = values.resolve(
            assertion.params["value"], bound_values=bound_values, inputs=inputs)
        if value_error is not None:
            return CheckResult(
                "frontend", "objects_matching_count", False, value_error)
        field = assertion.params["field"]
        matched = sum(
            1
            for obj in (*identified, *anonymous)
            if isinstance(obj.get("fields"), dict)
            and field in obj["fields"]
            and values.equal(obj["fields"][field], expected)
        )
        n = assertion.params["count"]
        ok = matched == n
        return CheckResult(
            "frontend", "objects_matching_count", ok,
            "" if ok else (
                f"anchor {anchor!r} field {field!r} matched {matched} object(s), "
                f"expected {n}"
            ),
        )
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
    ok = len(outgoing) == 1 and (
        outgoing[0].method == request.method
        and outgoing[0].path == request.path
        and (request.body is None or ui_stepwise._subset(outgoing[0].body, request.body))
    )
    return CheckResult("request", "request", ok,
                       "" if ok else "associated UI request violates its declaration")


def run(scenario, *, ui, normalizer, auth=None, mock_plan=None, now=None, sleep=None):
    return ui_stepwise.run(
        scenario, ui=ui, normalizer=normalizer, auth=auth,
        eval_frontend=_eval_frontend, eval_request_shape=_eval_request_shape,
        mock_plan=mock_plan, now=now, sleep=sleep,
    )
