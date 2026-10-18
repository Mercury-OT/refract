"""Contract models and diff logic.

* `consumer_contract` captures what the declaration says a consumer relies on.
* `provider_contract` captures what the real backend returned in recordings.
* `diff` reports fields or success semantics required by the consumer but not
  satisfied by the provider.
"""
from dataclasses import dataclass, field
import copy
from typing import Literal

from refracto.declaration import values
from refracto.declaration import collections
from refracto.declaration import http_status
from refracto.declaration import field_comparison
from refracto.declaration import numeric_comparison
from refracto.declaration.model import Assertion
from refracto.declaration.binding import prepare_step
from refracto.ports import NormalizedResponse
from refracto.normalization import normalize_response
from refracto import headers as header_ops

StatusExpectation = Literal["requires_success", "requires_failure", "dont_care"]

REQUIRES_SUCCESS: StatusExpectation = "requires_success"
REQUIRES_FAILURE: StatusExpectation = "requires_failure"
DONT_CARE: StatusExpectation = "dont_care"


@dataclass(frozen=True)
class EndpointShape:
    response_fields: frozenset[str]
    response_values: dict = field(default_factory=dict, repr=False, metadata={"sensitive": True})
    status_expectation: StatusExpectation = DONT_CARE
    succeeded: bool | None = None
    forbidden_fields: frozenset[str] = field(
        default_factory=frozenset,
        kw_only=True,
    )
    collection_constraints: list = field(
        default_factory=list, kw_only=True, repr=False, metadata={"sensitive": True})
    allowed_http_statuses: frozenset[int] | None = field(default=None, kw_only=True)
    http_status: int | None = field(default=None, kw_only=True)
    header_constraints: list = field(default_factory=list, kw_only=True, repr=False, metadata={"sensitive": True})
    header_items: list | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})
    field_constraints: list = field(default_factory=list, kw_only=True, repr=False, metadata={"sensitive": True})
    numeric_constraints: list = field(default_factory=list, kw_only=True, repr=False, metadata={"sensitive": True})


@dataclass
class Contract:
    entries: dict = field(default_factory=dict)   # (step_id, method, template_path) -> EndpointShape


@dataclass
class ContractMismatch:
    endpoint: tuple
    missing_fields: frozenset
    note: str = ""
    wrong_values: dict = field(default_factory=dict, repr=False, metadata={"sensitive": True})
    value_errors: dict = field(default_factory=dict)
    unexpected_fields: frozenset[str] = field(
        default_factory=frozenset,
        kw_only=True,
    )
    collection_errors: list[str] = field(default_factory=list, kw_only=True)
    header_errors: list[str] = field(default_factory=list, kw_only=True)
    field_errors: list[str] = field(default_factory=list, kw_only=True)


def consumer_contract(scenario) -> Contract:
    """Build the consumer-side contract from a scenario declaration.

    Each step contributes one entry keyed by
    `(step.id, step.request.method, step.request.path)`.

    * `status_expectation` is derived from a declared `success` or `failure`
      response assertion; without either assertion, normalized success is not
      constrained. `allowed_http_statuses` independently constrains the recorded
      HTTP status when `status_equals` or `status_in` is declared.
    * `response_fields` comes from declared presence, equality, and collection
      assertions.
    * `response_values` retains the value side of `field_equals` assertions.
    * `collection_constraints` retains every collection predicate in order;
      several predicates on the same field must not overwrite one another.
    * `forbidden_fields` comes from declared `field_absent` assertions.
    * A step with no request contributes no entry.
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
            if a.check in ("has", "field_equals", "field_not_equals", "collection_matching_count")
            or a.check in numeric_comparison.CHECKS
        )
        response_values = {
            a.params["field"]: a.params["value"]
            for a in step.expect.response if a.check == "field_equals"
        }
        forbidden_fields = frozenset(
            a.params["field"] for a in step.expect.response
            if a.check == "field_absent"
        )
        entries[(step.id, step.request.method, step.request.path)] = EndpointShape(
            response_fields=fields,
            response_values=response_values,
            status_expectation=status_expectation,
            forbidden_fields=forbidden_fields,
            collection_constraints=[
                {"field": a.params["field"], "matching": dict(a.params["matching"]),
                 "count": a.params["count"]}
                for a in step.expect.response if a.check == "collection_matching_count"
            ],
            allowed_http_statuses=next((http_status.allowed(a) for a in step.expect.response
                                       if a.check in http_status.CHECKS), None),
            header_constraints=[copy.deepcopy(a) for a in step.expect.response if a.check in header_ops.CHECKS],
            field_constraints=[copy.deepcopy(a) for a in step.expect.response if a.check in field_comparison.CHECKS],
            numeric_constraints=[copy.deepcopy(a) for a in step.expect.response if a.check in numeric_comparison.CHECKS],
        )
    return Contract(entries=entries)


def provider_contract(recordings, normalizer, *, required_status_keys=frozenset(), required_users=None,
                      required_sessions=None) -> Contract:
    """Build the provider-side contract from real recordings.

    Provider entries are keyed on `(step_id, method, template_path)`, not the
    actual resolved path, so provider and consumer contracts match on declared
    transport identity.

    Non-final recordings are skipped. Only the final recording for a step and
    endpoint contributes to the provider contract. For endpoints requiring HTTP
    status evidence, invalid or missing status is unavailable evidence, without
    asking a normalizer to interpret that malformed transport value.
    """
    entries = {}
    for r in recordings:
        step_id = getattr(r, "step_id", None)
        template = getattr(r, "template_path", None) or r.request.path
        key = (step_id, r.request.method, template)
        if required_users is not None and key in required_users:
            user = required_users[key]
            generation = getattr(r, "session_generation", None)
            if (getattr(r, "user", None) != user or type(generation) is not int
                    or (generation != 0 if user is None else generation < 1)):
                raise ValueError("provider recording user/session attribution is unavailable or mismatched")
            if required_sessions is not None and generation != required_sessions.get(step_id):
                raise ValueError("provider recording session generation does not match execution provenance")
        if getattr(r, "is_final", True) is False:
            continue
        if required_users is not None and key in entries:
            raise ValueError("multiple final provider recordings have the same declared identity")
        observed_status = getattr(r, "status", None)
        observed_headers = copy.deepcopy(r.header_items)
        observed_status = observed_status if http_status.valid(observed_status) else None
        if observed_status is None and key in required_status_keys:
            entries[key] = EndpointShape(response_fields=frozenset(), header_items=observed_headers)
            continue
        norm = normalize_response(normalizer, r)
        entries[key] = EndpointShape(
            response_fields=frozenset(norm.fields.keys()),
            response_values=dict(norm.fields),
            succeeded=norm.succeeded,
            http_status=observed_status,
            header_items=observed_headers,
        )
    return Contract(entries=entries)


def provider_binding_values(scenario, provider: Contract) -> dict:
    """Resolve each step's bindings from provider response evidence."""
    steps = {step.id: step for step in scenario.steps}
    resolved = {}
    observations = {}
    for source in scenario.steps:
        if source.request is not None:
            shape = provider.entries.get((source.id, source.request.method, source.request.path))
            if shape is not None:
                observations[source.id] = NormalizedResponse(shape.succeeded, shape.response_values, shape.http_status, None)
    for step in scenario.steps:
        if any(binding.key is not None or binding.matching is not None for binding in step.bind):
            # Selection must also be legal at its declared use site. Otherwise
            # successful downstream recordings could mask a value that could
            # never have produced that request under the execution rules.
            _, resolved[step.id] = prepare_step(step, scenario, observations)
            continue
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
            if (source_shape is None or binding.field not in source_shape.response_values
                    or source_shape.response_values[binding.field] is None):
                continue
            value = source_shape.response_values[binding.field]
            field_comparison.require_data(value)
            step_values[binding.placeholder] = copy.deepcopy(value)
        resolved[step.id] = step_values
    return resolved


def diff(consumer: Contract, provider: Contract, *, inputs=None, bound_values_by_step=None):
    """Return mismatches between consumer and provider contracts."""
    out = []
    bound_values_by_step = bound_values_by_step or {}
    for key, want in consumer.entries.items():
        numeric_expected = [numeric_comparison.resolve_expected(
            constraint.check, constraint.params["value"],
            bound_values=bound_values_by_step.get(key[0]), inputs=inputs)
            for constraint in want.numeric_constraints]
        have = provider.entries.get(key)
        if have is None:
            if want.header_constraints:
                raise ValueError("response header evidence is unavailable for contract checking")
            out.append(ContractMismatch(endpoint=key, missing_fields=want.response_fields,
                                        note="endpoint not observed in provider recordings"))
            continue
        missing = want.response_fields - have.response_fields
        unexpected = want.forbidden_fields & have.response_fields
        wrong_values = {}
        value_errors = {}
        collection_errors = []
        header_errors = []
        field_errors = []
        step_id = key[0]
        for constraint, expected in zip(want.numeric_constraints, numeric_expected):
            params = constraint.params
            ok, detail = numeric_comparison.evaluate(
                constraint.check, have.response_values, params["field"], params["op"], expected)
            if not ok:
                field_errors.append(detail)
        for constraint in want.header_constraints:
            expected = None
            if constraint.check == "header_equals":
                expected, error = values.resolve(constraint.params["value"],
                    bound_values=bound_values_by_step.get(step_id), inputs=inputs)
                if error is not None:
                    raise ValueError("response header reference is unavailable for contract checking")
            ok, detail = header_ops.evaluate(constraint.check, constraint.params["header"],
                                             expected, have.header_items)
            if not ok:
                header_errors.append(detail)
        for constraint in want.collection_constraints:
            ok, detail = collections.evaluate(
                have.response_values, constraint["field"], constraint["matching"],
                constraint["count"], bound_values=bound_values_by_step.get(step_id), inputs=inputs)
            if not ok:
                collection_errors.append(detail)
        constraints = want.field_constraints or [
            Assertion("field_equals", {"field": name, "value": declared})
            for name, declared in want.response_values.items()]
        for constraint in constraints:
            field_name, declared = constraint.params["field"], constraint.params["value"]
            if field_name in missing:
                continue
            if field_name not in have.response_values:
                value_errors[field_name] = "provider field value is unavailable"
                continue
            expected, error = field_comparison.resolve_expected(
                declared,
                bound_values=bound_values_by_step.get(step_id),
                inputs=inputs,
            )
            if error is not None:
                value_errors[field_name] = error
                continue
            observed = have.response_values[field_name]
            ok, detail = field_comparison.evaluate(constraint.check, have.response_values, field_name, expected)
            if not ok:
                if (constraint.check == "field_equals" and type(expected) not in (list, dict)
                        and type(observed) not in (list, dict)):
                    wrong_values[field_name] = (expected, observed)
                else:
                    field_errors.append(detail)
        status_note = ""
        if want.status_expectation == REQUIRES_SUCCESS and not have.succeeded:
            status_note = "status mismatch"
        elif want.status_expectation == REQUIRES_FAILURE and have.succeeded:
            status_note = "expected failure, provider succeeded"
        if want.allowed_http_statuses is not None and (
                not http_status.valid(have.http_status) or have.http_status not in want.allowed_http_statuses):
            status_note = "; ".join(filter(None, [status_note,
                http_status.mismatch(want.allowed_http_statuses, have.http_status)]))
        if missing or unexpected or status_note or wrong_values or value_errors or collection_errors or header_errors or field_errors:
            out.append(ContractMismatch(
                endpoint=key,
                missing_fields=missing,
                note=status_note,
                wrong_values=wrong_values,
                value_errors=value_errors,
                unexpected_fields=unexpected,
                collection_errors=collection_errors,
                header_errors=header_errors,
                field_errors=field_errors,
            ))
    return out
