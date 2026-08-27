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
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED


def run(scenario, provider_recordings, normalizer) -> DomainResult:
    consumer = store.consumer_contract(scenario)
    provider = store.provider_contract(provider_recordings, normalizer)
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
            if mismatch.note:
                details.append(mismatch.note)
            for field_name, (expected, observed) in mismatch.wrong_values.items():
                details.append(
                    f"field={field_name!r} expected={expected!r} observed={observed!r}")
            for field_name, error in mismatch.value_errors.items():
                details.append(f"field={field_name!r} {error}")
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
