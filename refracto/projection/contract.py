"""Contract projection.

Diff the declaration's consumer contract against the provider contract built
from real recordings.

This projection issues no requests of its own: it only reads recordings the
backend projection already produced, so it needs no browser and no network. It
is therefore not runnable on its own — see `runner.run_scenario`.

Scenarios with templated step paths currently degrade the contract domain
instead of partially diffing only their static steps.
"""
from refracto.contract import store
from refracto.report import CheckResult, DomainResult, StepResult, PASSED, FAILED

_TEMPLATED_SKIP = "multi-step contract with templated paths is not currently supported"


def run(scenario, provider_recordings, normalizer) -> DomainResult:
    if any(step.request is not None and "{" in step.request.path for step in scenario.steps):
        return DomainResult(projection="contract", steps=[], skipped=[_TEMPLATED_SKIP])

    consumer = store.consumer_contract(scenario)
    provider = store.provider_contract(provider_recordings, normalizer)
    mismatches = store.diff(consumer, provider)

    if not mismatches:
        checks = [CheckResult("contract", "diff", True, "no drift", step="contract")]
        status = PASSED
    else:
        checks = [CheckResult("contract", "diff", False,
                              f"{m.endpoint}: missing {set(m.missing_fields)} {m.note}",
                              step="contract")
                  for m in mismatches]
        status = FAILED

    return DomainResult(projection="contract",
                        steps=[StepResult(step_id="contract", status=status, checks=checks)])
