"""E2E projection.

Drive the real UI once against the real backend and derive all four observation
points from that single execution. The UiDriver injects a trace identity into
outgoing declared requests and captures request/response pairs so frontend,
request, response, and backend-state assertions describe the same run.
"""
from refracto.projection import backend as backend_proj
from refracto.projection.frontend import _eval_frontend, _eval_request_shape
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED


def _match_recorded(recorded, request):
    return next((r for r in recorded
                 if r.request.method == request.method and r.request.path == request.path), None)


def run(scenario, *, auth, ui, state, recorder, normalizer, resolve_precondition=None,
        poll_config=None, now=None, sleep=None):
    if len(scenario.steps) != 1:
        return DomainResult(projection="e2e",
                            skipped=["multi-step UI not supported"])
    step = scenario.steps[0]
    session = auth.session(scenario.actor)
    if resolve_precondition:
        for ref in scenario.precondition:
            resolve_precondition(ref, session)

    result = ui.run_intent(scenario, session, None)   # mock=None => real backend, single drive
    for r in result.recorded:
        recorder.record(r)

    checks = [_eval_frontend(a, result.rendered) for a in step.expect.frontend]
    if step.request is not None:
        checks.append(_eval_request_shape(step.request, result.outgoing))

    resp = None
    if step.request is not None:
        resp = _match_recorded(result.recorded, step.request)
    if step.expect.response:
        if resp is None:
            checks.append(CheckResult(point="response", check="_no_ui_traffic", ok=False,
                detail="declared response expectations but the UI produced no matching recorded response"))
        else:
            norm = normalizer.normalize(resp)
            checks += [
                backend_proj._eval_response(a, norm, inputs=scenario.inputs)
                for a in step.expect.response
            ]

    trace_id = resp.trace_id if resp else None
    # Business polling and backend-state polling use independent timing budgets.
    state_checks, skipped = backend_proj.assert_backend_state_for(
        step, state, trace_id, now=now, sleep=sleep, inputs=scenario.inputs)
    checks += state_checks

    for c in checks:
        c.step = step.id
    status = FAILED if any(not c.ok for c in checks) else PASSED
    return DomainResult(projection="e2e",
                        steps=[StepResult(step.id, status, checks=checks, skipped=skipped)],
                        provider_recordings=recorder.responses())
