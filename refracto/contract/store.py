"""Contract models and diff logic.

* `consumer_contract` captures what the declaration says a consumer relies on.
* `provider_contract` captures what the real backend returned in recordings.
* `diff` reports fields or success semantics required by the consumer but not
  satisfied by the provider.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EndpointShape:
    status_ok: bool
    response_fields: frozenset[str]


@dataclass
class Contract:
    entries: dict = field(default_factory=dict)   # (step_id, method, template_path) -> EndpointShape


@dataclass
class ContractMismatch:
    endpoint: tuple
    missing_fields: frozenset
    note: str = ""


def consumer_contract(scenario) -> Contract:
    """Build the consumer-side contract from a scenario declaration.

    Each step contributes one entry keyed by
    `(step.id, step.request.method, step.request.path)`.

    * `status_ok` comes from a declared `success` response assertion.
    * `response_fields` comes from declared `has` response assertions.
    * A v1-normalized step with no request contributes no entry.
    """
    entries = {}
    for step in scenario.steps:
        if step.request is None:
            continue
        wants_success = any(a.check == "success" for a in step.expect.response)
        fields = frozenset(a.params["field"] for a in step.expect.response if a.check == "has")
        entries[(step.id, step.request.method, step.request.path)] = EndpointShape(
            status_ok=wants_success, response_fields=fields)
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
            status_ok=norm.succeeded, response_fields=frozenset(norm.fields.keys()))
    return Contract(entries=entries)


def diff(consumer: Contract, provider: Contract):
    """Return mismatches between consumer and provider contracts."""
    out = []
    for key, want in consumer.entries.items():
        have = provider.entries.get(key)
        if have is None:
            out.append(ContractMismatch(endpoint=key, missing_fields=want.response_fields,
                                        note="endpoint not observed in provider recordings"))
            continue
        missing = want.response_fields - have.response_fields
        if missing or (want.status_ok and not have.status_ok):
            out.append(ContractMismatch(endpoint=key, missing_fields=missing,
                                        note="status mismatch" if want.status_ok and not have.status_ok else ""))
    return out
