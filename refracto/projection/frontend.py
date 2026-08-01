"""Frontend projection.

Drive the UI against a mock backend generated from the consumer contract and
assert frontend rendering plus outgoing-request shape. This projection does not
use a real backend or a state probe.
"""
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED
from refracto.contract import store


def build_mock(scenario, normalizer) -> dict:
    consumer = store.consumer_contract(scenario)
    # Consumer contract entries are keyed on (step_id, method, template_path).
    # The mock presented to UI drivers is keyed on (method, path). Frontend and
    # e2e projections only run single-step scenarios, so this key shape remains
    # sufficient here.
    return {(method, path): normalizer.synthesize(shape.response_fields)
            for (_step_id, method, path), shape in consumer.entries.items()}


def _eval_frontend(assertion, rendered):
    anchor = assertion.params["anchor"]
    r = rendered.get(anchor, {})
    if assertion.check == "visible":
        ok = bool(r.get("visible"))
        return CheckResult("frontend", "visible", ok, "" if ok else f"{anchor} not visible")
    if assertion.check == "count_gt":
        n = assertion.params["n"]
        ok = r.get("count", 0) > n
        return CheckResult("frontend", "count_gt", ok,
                           "" if ok else f"{anchor} count {r.get('count',0)} !> {n}")
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
    checks = [_eval_frontend(a, result.rendered) for a in step.expect.frontend]
    if step.request is not None:
        checks.append(_eval_request_shape(step.request, result.outgoing))
    for c in checks:
        c.step = step.id
    status = FAILED if any(not c.ok for c in checks) else PASSED
    return DomainResult(projection="frontend",
                        steps=[StepResult(step.id, status, checks=checks)])
