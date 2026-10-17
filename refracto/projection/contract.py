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
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED, ERROR, BLOCKED, NOT_APPLICABLE


def run(scenario, provider_recordings, normalizer, *, execution_steps=None) -> DomainResult:
    consumer = store.consumer_contract(scenario)
    if not consumer.entries or not any(step.request and step.expect.response for step in scenario.steps):
        return DomainResult(projection="contract", steps=[])
    try:
        if execution_steps is None:
            if any(step.session == "new" for step in scenario.steps):
                raise ValueError("session replacement requires backend execution provenance for contract checking")
            generations = {step.id: 0 if scenario.effective_user(step) is None else 1
                           for step in scenario.steps}
        else:
            declarations = {step.id: step for step in scenario.steps}
            generations = {}
            seen_steps = set()
            for result in execution_steps:
                declaration = declarations.get(result.step_id)
                if declaration is None:
                    continue
                if result.step_id in seen_steps:
                    raise ValueError("duplicate backend execution provenance")
                seen_steps.add(result.step_id)
                if result.status in (BLOCKED, NOT_APPLICABLE):
                    continue
                if result.user != scenario.effective_user(declaration):
                    raise ValueError("backend execution user differs from declaration")
                if result.session_generation is not None:
                    if (type(result.session_generation) is not int
                            or (result.session_generation != 0 if result.user is None else result.session_generation < 1)):
                        raise ValueError("invalid backend session generation provenance")
                    generations[result.step_id] = result.session_generation
        provider = store.provider_contract(provider_recordings, normalizer,
            required_status_keys=frozenset(key for key, shape in consumer.entries.items()
                                           if shape.allowed_http_statuses is not None),
            required_users={(step.id, step.request.method, step.request.path): scenario.effective_user(step)
                            for step in scenario.steps if step.request is not None},
            required_sessions=generations)
    except Exception as exc:
        return DomainResult("contract", steps=[StepResult("contract", ERROR, detail=str(exc))])
    bound_values = store.provider_binding_values(scenario, provider)
    mismatches = store.diff(
        consumer,
        provider,
        inputs=scenario.inputs,
        bound_values_by_step=bound_values,
    )

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
            checks.append(CheckResult(
                "contract",
                "diff",
                False,
                " ".join(details),
                step=mismatch.endpoint[0] or "contract",
            ))
        status = FAILED

    return DomainResult(projection="contract",
                        steps=[StepResult(step_id="contract", status=status, checks=checks)])
