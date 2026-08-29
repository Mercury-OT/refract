"""Contract models and diff logic.

* `consumer_contract` captures what the declaration says a consumer relies on.
* `provider_contract` captures what the real backend returned in recordings.
* `diff` reports fields or success semantics required by the consumer but not
  satisfied by the provider.
"""
from dataclasses import dataclass, field
from typing import Literal

from refracto.declaration import values

StatusExpectation = Literal["requires_success", "requires_failure", "dont_care"]

REQUIRES_SUCCESS: StatusExpectation = "requires_success"
REQUIRES_FAILURE: StatusExpectation = "requires_failure"
DONT_CARE: StatusExpectation = "dont_care"


@dataclass(frozen=True)
class EndpointShape:
    response_fields: frozenset[str]
    response_values: dict = field(default_factory=dict)
    status_expectation: StatusExpectation = DONT_CARE
    succeeded: bool | None = None


@dataclass
class Contract:
    entries: dict = field(default_factory=dict)   # (step_id, method, template_path) -> EndpointShape


@dataclass
class ContractMismatch:
    endpoint: tuple
    missing_fields: frozenset
    note: str = ""
    wrong_values: dict = field(default_factory=dict)
    value_errors: dict = field(default_factory=dict)


def consumer_contract(scenario) -> Contract:
    """Build the consumer-side contract from a scenario declaration.

    Each step contributes one entry keyed by
    `(step.id, step.request.method, step.request.path)`.

    * `status_expectation` is derived from a declared `success` or `failure`
      response assertion; without either assertion, status is not constrained.
    * `response_fields` comes from declared `has` and `field_equals` assertions.
    * `response_values` retains the value side of `field_equals` assertions.
    * A v1-normalized step with no request contributes no entry.
    """
    entries = {}
    for step in scenario.steps:
        if step.request is None:
            continue
        response_checks = {a.check for a in step.expect.response}
        if "success" in response_checks:
            status_expectation = REQUIRES_SUCCESS
        elif "failure" in response_checks:
            status_expectation = REQUIRES_FAILURE
        else:
            status_expectation = DONT_CARE
        fields = frozenset(
            a.params["field"] for a in step.expect.response
            if a.check in ("has", "field_equals")
        )
        response_values = {
            a.params["field"]: a.params["value"]
            for a in step.expect.response if a.check == "field_equals"
        }
        entries[(step.id, step.request.method, step.request.path)] = EndpointShape(
            response_fields=fields,
            response_values=response_values,
            status_expectation=status_expectation,
        )
    return Contract(entries=entries)


def provider_contract(recordings, normalizer) -> Contract:
    """Build the provider-side contract from real recordings.

    Provider entries are keyed on `(step_id, method, template_path)`, not the
    actual resolved path, so provider and consumer contracts match on declared
    transport identity.

    Non-final recordings are skipped. Only the final recording for a step and
    endpoint contributes to the provider contract.
    """
    entries = {}
    for r in recordings:
        if getattr(r, "is_final", True) is False:
            continue
        norm = normalizer.normalize(r)
        step_id = getattr(r, "step_id", None)
        template = getattr(r, "template_path", None) or r.request.path
        entries[(step_id, r.request.method, template)] = EndpointShape(
            response_fields=frozenset(norm.fields.keys()),
            response_values=dict(norm.fields),
            succeeded=norm.succeeded,
        )
    return Contract(entries=entries)


def provider_binding_values(scenario, provider: Contract) -> dict:
    """Resolve each step's bindings from provider response evidence."""
    steps = {step.id: step for step in scenario.steps}
    resolved = {}
    for step in scenario.steps:
        step_values = {}
        for binding in step.bind:
            source = steps.get(binding.from_step)
            if source is None or source.request is None:
                continue
            source_key = (
                source.id,
                source.request.method,
                source.request.path,
            )
            source_shape = provider.entries.get(source_key)
            if source_shape is None or binding.field not in source_shape.response_values:
                continue
            step_values[binding.placeholder] = source_shape.response_values[binding.field]
        resolved[step.id] = step_values
    return resolved


def diff(consumer: Contract, provider: Contract, *, inputs=None, bound_values_by_step=None):
    """Return mismatches between consumer and provider contracts."""
    out = []
    bound_values_by_step = bound_values_by_step or {}
    for key, want in consumer.entries.items():
        have = provider.entries.get(key)
        if have is None:
            out.append(ContractMismatch(endpoint=key, missing_fields=want.response_fields,
                                        note="endpoint not observed in provider recordings"))
            continue
        missing = want.response_fields - have.response_fields
        wrong_values = {}
        value_errors = {}
        step_id = key[0]
        for field_name, declared in want.response_values.items():
            if field_name in missing:
                continue
            if field_name not in have.response_values:
                value_errors[field_name] = "provider field value is unavailable"
                continue
            expected, error = values.resolve(
                declared,
                bound_values=bound_values_by_step.get(step_id),
                inputs=inputs,
            )
            if error is not None:
                value_errors[field_name] = error
                continue
            observed = have.response_values[field_name]
            if not values.equal(observed, expected):
                wrong_values[field_name] = (expected, observed)
        status_note = ""
        if want.status_expectation == REQUIRES_SUCCESS and not have.succeeded:
            status_note = "status mismatch"
        elif want.status_expectation == REQUIRES_FAILURE and have.succeeded:
            status_note = "expected failure, provider succeeded"
        if missing or status_note or wrong_values or value_errors:
            out.append(ContractMismatch(
                endpoint=key,
                missing_fields=missing,
                note=status_note,
                wrong_values=wrong_values,
                value_errors=value_errors,
            ))
    return out
