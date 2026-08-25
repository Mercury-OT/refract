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
    mismatches = store.diff(consumer, provider)

    if not mismatches:
        checks = [CheckResult("contract", "diff", True, "no drift", step="contract")]
        status = PASSED
    else:
        checks = [CheckResult("contract", "diff", False,
                              f"{m.endpoint}: missing {set(m.missing_fields)} {m.note}",
                              step=m.endpoint[0] or "contract")
                  for m in mismatches]
        status = FAILED

    return DomainResult(projection="contract",
                        steps=[StepResult(step_id="contract", status=status, checks=checks)])
