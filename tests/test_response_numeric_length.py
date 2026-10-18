"""Numeric and actual-list length obligations share strict evidence semantics."""
import copy
import dataclasses
from decimal import Decimal

import pytest

from refracto import ports
from refracto.contract import store
from refracto.declaration import vocabulary
from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import DeclarationError
from refracto.declaration.model import Assertion
from refracto.projection import backend, contract
from refracto.runner import PollConfig
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.test_response_field_comparison import (
    ABSENT, NoCopy, execute, load, malformed_values, request, resolver,
)
from tests.ui_support import response

TERMS = ("field_compare", "collection_length")
OPS = (">", ">=", "<", "<=", "==")
SENTINEL = "numeric-length-sensitive-sentinel"
SECRET_NUMBER = 876543210987654321


def check(term="field_compare", value=1, op="==", field="measured"):
    return {"check": term, "field": field, "op": op, "value": value}


def evaluate(actual, value=1, op="==", term="field_compare"):
    params = check(term, value, op)
    params.pop("check")
    fields = {} if actual is ABSENT else {"measured": actual}
    return backend._eval_response(Assertion(term, params),
        ports.NormalizedResponse(True, fields, 200, None))


@pytest.mark.parametrize("term", TERMS)
def test_vocabulary_is_response_only_and_exact(term):
    assert vocabulary.required_params("response", term) == ("field", "op", "value")
    assert vocabulary.optional_params("response", term) == ()
    assert not vocabulary.is_valid("frontend", term)
    assert not vocabulary.is_valid("backend_state", term)


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("actual", [0, 1, 2])
def test_every_operator_and_boundary_neighbor(term, op, actual):
    expected = {">": actual > 1, ">=": actual >= 1, "<": actual < 1,
                "<=": actual <= 1, "==": actual == 1}[op]
    observed = actual if term == "field_compare" else [None] * actual
    assert evaluate(observed, op=op, term=term).ok is expected
    scenario = load(request(checks=[check(term, op=op)]))
    assert prepare_step(scenario.steps[0], scenario, {})[0].expect.response[0].params["op"] == op


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("missing", ["field", "op", "value"])
def test_missing_parameters_rejected(term, missing):
    declaration = check(term)
    del declaration[missing]
    with pytest.raises(DeclarationError, match="missing required"):
        load(request(checks=[declaration]))


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("key,value", [("extra", 1), ("field", ""), ("field", " "),
    ("field", 1), ("field", []), ("field", {"from_parameter": "name"}),
    ("op", "!="), ("op", "=>"), ("op", None), ("op", 1), ("op", []),
    ("op", {"from_parameter": "operator"})])
def test_invalid_shape_field_and_operator_rejected(term, key, value):
    declaration = check(term)
    declaration[key] = value
    with pytest.raises(DeclarationError):
        load(request(checks=[declaration]), parameters={"name": "measured", "operator": "=="})


@pytest.mark.parametrize("term,value", [
    *((term, value) for term in TERMS for value in
      [None, False, True, "1", "", [], {}, [1], {"v": 1}, float("nan"),
       float("inf"), float("-inf"), (), Decimal("1"), object()]),
    ("collection_length", -1), ("collection_length", 0.0), ("collection_length", 1.0),
])
def test_invalid_literals_and_parameter_defaults_rejected(term, value):
    with pytest.raises(DeclarationError):
        load(request(checks=[check(term, value)]))
    with pytest.raises(DeclarationError):
        load(request(checks=[check(term, {"from_parameter": "threshold"})]),
             parameters={"threshold": value})


@pytest.mark.parametrize("value", [-10**400, -1.5, -1, 0, 0.0, 1, 1.5, 10**400])
def test_finite_numeric_defaults_and_literals_prepare_without_coercion(value):
    for declared in (value, {"from_parameter": "threshold"}):
        scenario = load(request(checks=[check(value=declared)]), parameters={"threshold": value})
        prepared, _ = prepare_step(scenario.steps[0], scenario, {})
        actual = prepared.expect.response[0].params["value"]
        assert type(actual) is type(value) and actual == value


@pytest.mark.parametrize("term", TERMS)
def test_duplicates_absence_conflicts_and_ranges(term):
    with pytest.raises(DeclarationError, match="duplicate"):
        load(request(checks=[check(term, 1, ">="), check(term, 2, ">=")]))
    with pytest.raises(DeclarationError, match="field_absent conflicts"):
        load(request(checks=[check(term), {"check": "field_absent", "field": "measured"}]))
    scenario = load(request(checks=[check(term, 1, ">="), check(term, 2, "<="),
        {"check": "has", "field": "measured"}, {"check": "field_equals", "field": "measured", "value": 1}]))
    assert len(scenario.steps[0].expect.response) == 4


def test_punctuation_is_literal_and_legacy_reference_limits_stay_unchanged():
    scenario = load(request(checks=[check(field="stats.total[0]")]))
    result, _ = execute(scenario, {"read": {"stats.total[0]": 1}})
    assert result.status == "PASSED"
    step = request(checks=[])
    step["expect"]["backend_state"] = [{"check": "span_attr", "span": "read",
        "attr": "count", "op": ">", "value": {"from_parameter": "threshold"}}]
    with pytest.raises(DeclarationError, match="reference requires equality"):
        load(step, parameters={"threshold": 1})


@pytest.mark.parametrize("observed,expected,op,ok", [
    (1, 1.0, "==", False), (1.0, 1, "==", False), (1, 1.0, ">=", True),
    (1.0, 1, "<=", True), (-1.5, -1, "<", True), (-1, -1.5, ">", True),
    (2**53 + 1, float(2**53), ">", True), (float(2**53), 2**53 + 1, "<", True),
    (10**400, 1e308, ">", True), (-10**400, -1e308, "<", True),
    (1e308, 10**400, "<", True), (-1e308, -10**400, ">", True),
    (10**400, 10**400, "==", True), (-0.0, 0.0, "==", True),
])
def test_exact_numeric_comparison_has_no_float_rounding(observed, expected, op, ok):
    assert evaluate(observed, expected, op).ok is ok


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("observed", [ABSENT, None, False, True, "1", "", {}])
def test_missing_null_and_valid_wrong_types_are_failures(term, observed):
    result = evaluate(observed, 0, ">=", term)
    assert not result.ok
    assert "missing" in result.detail if observed is ABSENT else "not a" in result.detail


def test_list_length_counts_heterogeneous_duplicate_and_shared_members_without_mutation():
    shared = {"x": [None, True, 1, 1.0]}
    observed = [shared, shared, None, False, "text", [], 3.5]
    before = copy.deepcopy(observed)
    assert evaluate(observed, 7, "==", "collection_length").ok
    assert observed == before and observed[0] is observed[1]
    assert evaluate([], 0, "==", "collection_length").ok
    assert not evaluate([None], 0, "==", "collection_length").ok
    assert not evaluate([], 0, ">=", "field_compare").ok
    assert not evaluate(0, 0, ">=", "collection_length").ok


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("observed", [*malformed_values(), [float("nan")],
    [{"secret": object()}], Decimal("1"), NoCopy()])
def test_malformed_examined_evidence_errors_even_for_permissive_bound(term, observed):
    with pytest.raises(ValueError) as error:
        evaluate(observed, 0, ">=", term)
    assert SENTINEL not in str(error.value)


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("mode", ["backend", "e2e"])
@pytest.mark.parametrize("observed,expected_status", [(ABSENT, "FAILED"), (None, "FAILED"),
    ("wrong", "FAILED"), (float("nan"), "ERROR"), ([float("inf")], "ERROR")])
def test_runtime_and_contract_share_evidence_classification(term, mode, observed, expected_status):
    scenario = load(request(checks=[check(term, 0, ">=")]), request("independent"))
    class Normalizer(FakeNormalizer):
        def normalize(self, raw):
            norm = super().normalize(raw)
            if raw.request.path == "read":
                norm.fields = {} if observed is ABSENT else {"measured": observed}
            return norm
    result, api = execute(scenario, mode=mode, normalizer=Normalizer())
    assert result.steps[0].status == expected_status
    assert result.steps[1].status == ("PASSED" if expected_status == "FAILED" else "BLOCKED")
    assert len(api.sent) == (2 if expected_status == "FAILED" else 1)
    replay = contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=result.steps)
    assert replay.steps[0].status == expected_status


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("mode", ["backend", "e2e"])
@pytest.mark.parametrize("source", [ABSENT, None, True, "1", [], {}, float("inf"), NoCopy()])
def test_unusable_response_threshold_blocks_atomically_and_independent_continues(term, mode, source):
    scenario = load(request("source", []), request("consumer", [check(term,
        {"from_step": "source", "response_field": "threshold"})]), request("independent"))
    class Normalizer(FakeNormalizer):
        def normalize(self, raw):
            norm = super().normalize(raw)
            if raw.request.path == "source":
                norm.fields = {} if source is ABSENT else {"threshold": source}
            return norm
    result, api = execute(scenario, mode=mode, normalizer=Normalizer())
    assert [step.status for step in result.steps] == ["COMPLETED", "BLOCKED", "PASSED"]
    assert result.steps[1].blocked_by == ["source"]
    assert result.steps[1].resolved_bindings == {}
    assert [item.path for item in api.sent] == ["source", "independent"]
    replay = contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=result.steps)
    assert replay.steps[0].status == "ERROR"


def test_invalid_threshold_precedes_new_consumer_authentication_and_request_resolution():
    scenario = load(request("source", [], user="reader"), request("consumer", [check(
        value={"from_step": "source", "response_field": "threshold"})], user="writer"),
        request("independent", user="reader"), users=["reader", "writer"])
    class Auth(FakeAuth):
        sessions = []
        def session(self, user):
            self.sessions.append(user)
            return super().session(user)
    auth, resolved = Auth(), []
    def resolve(scenario, step, template):
        resolved.append(step.id)
        return resolver(scenario, step, template)
    api = FakeApi({("GET", "source"): {"json": response({"threshold": "invalid"})}})
    result = backend.run(scenario, auth=auth, api=api, state=None,
        recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert [step.status for step in result.steps] == ["COMPLETED", "BLOCKED", "PASSED"]
    assert auth.sessions == ["reader"] and resolved == ["source", "independent"]


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("stop", [False, True])
def test_failed_source_can_supply_actual_threshold_unless_explicit_stop(term, stop):
    scenario = load(request("source", [check(value=0)], **({"on_failure": "stop"} if stop else {})),
        request("consumer", [check(term, {"from_step": "source", "response_field": "measured"})]))
    actual = 2 if term == "field_compare" else ["a", "b"]
    result, api = execute(scenario, {"source": {"measured": 2}, "consumer": {"measured": actual}})
    assert [step.status for step in result.steps] == ["FAILED", "BLOCKED" if stop else "PASSED"]
    assert len(api.sent) == (1 if stop else 2)
    if not stop:
        assert result.steps[1].after_failures == ["source"]
        replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
        assert [item.step for item in replay.checks] == ["source"]


@pytest.mark.parametrize("term", TERMS)
def test_contract_retains_ordered_bounds_and_uses_actual_provider_thresholds(term):
    ref = {"from_step": "source", "response_field": "threshold"}
    scenario = load(request("source", []), request("read", [check(term, 1, ">="), check(term, ref, "<=")]))
    observed = 2 if term == "field_compare" else ["a", "b"]
    result, _ = execute(scenario, {"source": {"threshold": 2}, "read": {"measured": observed}})
    consumer = store.consumer_contract(scenario)
    constraints = consumer.entries[("read", "GET", "read")].numeric_constraints
    assert [item.params["op"] for item in constraints] == [">=", "<="]
    assert [item.check for item in constraints] == [term, term]
    def inspect(recordings):
        return contract.run(scenario, recordings, FakeNormalizer(), execution_steps=result.steps)
    assert inspect(list(reversed(result.provider_recordings))).status == "PASSED"
    altered = copy.deepcopy(result.provider_recordings)
    altered[0].json["data"]["threshold"] = 1
    assert inspect(altered).status == "FAILED"
    assert inspect(result.provider_recordings[1:]).steps[0].status == "ERROR"
    altered[0].json["data"]["threshold"] = "2"
    assert inspect(altered).steps[0].status == "ERROR"
    assert inspect([*result.provider_recordings, result.provider_recordings[0]]).steps[0].status == "ERROR"
    assert inspect(result.provider_recordings[:1]).status == "FAILED"
    # Both sides of an impossible range survive, with no range solver.
    impossible = load(request(checks=[check(term, 3, ">="), check(term, 1, "<=")]))
    provider = store.provider_contract([result.provider_recordings[-1]], FakeNormalizer())
    mismatch = store.diff(store.consumer_contract(impossible), provider)
    assert len(mismatch[0].field_errors) == 2


@pytest.mark.parametrize("term", TERMS)
def test_default_representations_and_diagnostics_hide_values_and_members(term):
    observed = SECRET_NUMBER - 1 if term == "field_compare" else [{SENTINEL: SENTINEL}]
    scenario = load(request(checks=[check(term, SECRET_NUMBER)]))
    result, _ = execute(scenario, {"read": {"measured": observed}})
    consumer = store.consumer_contract(scenario)
    provider = store.provider_contract(result.provider_recordings, FakeNormalizer())
    mismatches = store.diff(consumer, provider)
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    rendered = repr((scenario, consumer, provider, mismatches, result, replay))
    rendered += "".join(item.detail for item in result.checks + replay.checks)
    assert str(SECRET_NUMBER) not in rendered and str(SECRET_NUMBER - 1) not in rendered
    assert SENTINEL not in rendered
    assert term in result.checks[0].detail and "op='=='" in result.checks[0].detail


@pytest.mark.parametrize("term", TERMS)
def test_only_examined_fields_are_validated_and_prior_snapshot_stays_owned(term):
    class Normalizer(FakeNormalizer):
        def __init__(self):
            self.fields = {}
        def normalize(self, raw):
            self.fields.update(threshold=2 if raw.request.path == "source" else 1,
                measured=2 if term == "field_compare" else [None, None], unrelated=NoCopy())
            return dataclasses.replace(super().normalize(raw), fields=self.fields)
    scenario = load(request("source", []), request("read", [check(term,
        {"from_step": "source", "response_field": "threshold"})]))
    result, _ = execute(scenario, normalizer=Normalizer())
    assert result.status == "PASSED"
    assert list(result.steps[1].resolved_bindings.values()) == [2]
    assert contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=result.steps).status == "PASSED"


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("policy,status", [("FAIL", "FAILED"), ("SKIP", "SKIPPED")])
def test_polling_timeout_preserves_policy(term, policy, status):
    scenario = load(request("poll", [check(term)], poll={"on_timeout": policy}), request("later"))
    clock = [0.0]
    result, _ = execute(scenario, {"poll": {"measured": 0 if term == "field_compare" else []}},
        poll_config=PollConfig(timeout=2, interval=1), now=lambda: clock[0],
        sleep=lambda amount: clock.__setitem__(0, clock[0] + amount))
    assert result.steps[0].status == status
    assert result.steps[1].status == ("PASSED" if policy == "FAIL" else "BLOCKED")
    assert not any(item.is_final for item in result.provider_recordings if item.step_id == "poll")


@pytest.mark.parametrize("term", TERMS)
def test_polling_success_uses_actual_attempts_and_marks_only_final(term):
    scenario = load(request("poll", [check(term)], poll={"on_timeout": "FAIL"}))
    class ChangingApi(FakeApi):
        def send(self, spec, session):
            raw = super().send(spec, session)
            count = min(len(self.sent) - 1, 1)
            raw.json = response({"measured": count if term == "field_compare" else [None] * count})
            return raw
    clock = [0.0]
    result, _ = execute(scenario, api=ChangingApi(), poll_config=PollConfig(timeout=2, interval=1),
        now=lambda: clock[0], sleep=lambda amount: clock.__setitem__(0, clock[0] + amount))
    assert result.status == "PASSED" and result.steps[0].attempts == 2
    assert [item.is_final for item in result.provider_recordings] == [False, True]
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"
