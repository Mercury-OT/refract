"""Contract projection.

Diff the declaration's consumer contract against the provider contract built
from real recordings.

This projection issues no requests of its own: it only reads recordings the
backend projection already produced, so it needs no browser and no network. It
is therefore not runnable on its own — see `runner.run_scenario`.

Multi-step and templated requests are matched by their declared transport
identity: `(step_id, method, template_path)`. Bound and adapter-resolved paths
remain recording evidence, but do not change which declared endpoint a provider
response satisfies.
"""
from refracto.contract import store
from refracto.declaration.run_values import ensure_bound_run_values
from refracto.report import (CheckResult, DomainResult, StepResult, PASSED, FAILED,
                            ERROR, BLOCKED, NOT_APPLICABLE, SKIPPED, COMPLETED)


def _execution_provenance(scenario, recordings, execution_steps):
    """Validate core execution metadata before trusting an unexecuted outcome."""
    if execution_steps is None:
        if any(step.session == "new" for step in scenario.steps):
            raise ValueError("session replacement requires backend execution provenance for contract checking")
        return ({step.id: 0 if scenario.effective_user(step) is None else 1
                 for step in scenario.steps}, {})
    declarations = {step.id: step for step in scenario.steps}
    positions = {step.id: index for index, step in enumerate(scenario.steps)}
    outcomes = {}
    generations, unexecuted, seen_steps = {}, {}, set()
    recorded_steps = {record.step_id for record in recordings}
    statuses = {PASSED, FAILED, ERROR, BLOCKED, NOT_APPLICABLE, SKIPPED, COMPLETED}
    for result in execution_steps:
        declaration = declarations.get(result.step_id)
        if declaration is None or result.step_id in seen_steps or result.status not in statuses:
            raise ValueError("missing, duplicate or invalid backend execution provenance")
        seen_steps.add(result.step_id)
        outcomes[result.step_id] = result
        if result.user != scenario.effective_user(declaration):
            raise ValueError("backend execution user differs from declaration")
        if result.status in (BLOCKED, NOT_APPLICABLE):
            if (result.step_id in recorded_steps or result.session_generation is not None
                    or result.response_origin is not None or result.trace_id is not None
                    or result.checks or result.resolved_bindings):
                raise ValueError("unexecuted backend provenance contradicts recorded execution")
            if result.status == NOT_APPLICABLE and declaration.request is not None:
                raise ValueError("request-bearing step cannot have not-applicable backend provenance")
            if declaration.request is not None:
                unexecuted[result.step_id] = StepResult(
                    result.step_id, BLOCKED, user=result.user,
                    detail="backend step was not executed; no provider response was evaluated",
                    blocked_by=list(result.blocked_by))
            continue
        if result.session_generation is not None:
            if (type(result.session_generation) is not int
                    or (result.session_generation != 0 if result.user is None else result.session_generation < 1)):
                raise ValueError("invalid backend session generation provenance")
            generations[result.step_id] = result.session_generation
    if seen_steps != set(declarations):
        raise ValueError("missing backend execution provenance")
    for step_id in unexecuted:
        causes = outcomes[step_id].blocked_by
        if (type(causes) is not list or not causes
                or any(type(cause) is not str or cause not in declarations
                       or positions[cause] >= positions[step_id] for cause in causes)):
            raise ValueError("blocked backend provenance has no valid earlier cause")
        stopped = len(causes) == 1 and (
            outcomes[causes[0]].status in (ERROR, SKIPPED)
            or (outcomes[causes[0]].status == FAILED
                and declarations[causes[0]].on_failure == "stop"))
        dependencies = {binding.from_step for binding in declarations[step_id].bind}
        if not stopped and not set(causes).issubset(dependencies):
            raise ValueError("blocked backend provenance contradicts continuation policy")
    return generations, unexecuted


def run(scenario, provider_recordings, normalizer, *, execution_steps=None) -> DomainResult:
    not_checked = [f"{step.id}: object_field_equals is outside contract scope"
                   for step in scenario.steps
                   if any(a.check == "object_field_equals" for a in step.expect.backend_state)]
    try:
        ensure_bound_run_values(scenario)
    except ValueError as exc:
        return DomainResult("contract", steps=[StepResult("contract", ERROR, detail=str(exc))],
                            not_checked=not_checked)
    consumer = store.consumer_contract(scenario)
    if not consumer.entries or not any(step.request and step.expect.response for step in scenario.steps):
        return DomainResult(projection="contract", steps=[], not_checked=not_checked)
    try:
        generations, unexecuted = _execution_provenance(scenario, provider_recordings, execution_steps)
        provider = store.provider_contract(provider_recordings, normalizer,
            required_status_keys=frozenset(key for key, shape in consumer.entries.items()
                                           if shape.allowed_http_statuses is not None),
            required_users={(step.id, step.request.method, step.request.path): scenario.effective_user(step)
                            for step in scenario.steps if step.request is not None},
            required_sessions=generations)
    except Exception as exc:
        return DomainResult("contract", steps=[StepResult("contract", ERROR, detail=str(exc))],
                            not_checked=not_checked)
    mismatches, errors, evaluated = [], [], 0
    for key, requirement in consumer.entries.items():
        if key[0] in unexecuted:
            continue
        try:
            bound_values = store.provider_binding_values(scenario, provider, step_ids={key[0]})
            mismatches.extend(store.diff(
                store.Contract({key: requirement}), provider, inputs=scenario.inputs,
                bound_values_by_step=bound_values))
            evaluated += 1
        except Exception:
            # This consumer cannot be evaluated honestly. Preserve its error,
            # but do not discard independent observations from other endpoints.
            errors.append(StepResult(key[0], ERROR,
                detail="provider response dependency or evidence is unavailable for contract checking"))

    if not mismatches:
        checks = [CheckResult("contract", "diff", True, "no drift", step="contract")]
        status = PASSED
    else:
        checks = []
        for mismatch in mismatches:
            details = [f"{mismatch.endpoint}:"]
            if mismatch.missing_fields:
                details.append(f"missing {set(mismatch.missing_fields)}")
            if mismatch.unexpected_fields:
                details.append(
                    f"unexpected fields {sorted(mismatch.unexpected_fields)}")
            if mismatch.note:
                details.append(mismatch.note)
            for field_name, (expected, observed) in mismatch.wrong_values.items():
                details.append(
                    f"field={field_name!r} expected={expected!r} observed={observed!r}")
            for field_name, error in mismatch.value_errors.items():
                details.append(f"field={field_name!r} {error}")
            details.extend(mismatch.collection_errors)
            details.extend(mismatch.header_errors)
            details.extend(mismatch.field_errors)
            checks.append(CheckResult(
                "contract",
                "diff",
                False,
                " ".join(details),
                step=mismatch.endpoint[0] or "contract",
            ))
        status = FAILED

    summary = [StepResult(step_id="contract", status=status, checks=checks)] if evaluated else []
    return DomainResult(projection="contract",
                        steps=errors + summary + list(unexecuted.values()),
                        not_checked=not_checked)
