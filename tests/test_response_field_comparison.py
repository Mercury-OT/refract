"""Complete response data, strict references and independent contract checks."""
import copy
import dataclasses
import threading
from types import MappingProxyType

import pytest

from refracto import ports
from refracto.contract import store
from refracto.declaration import field_comparison, vocabulary
from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import _references, _values
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.model import Assertion, Input, ValueRef
from refracto.normalization import normalize_response
from refracto.projection import backend, contract
from refracto.report import RunReport
from refracto.runner import PollConfig
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.test_scenario_include import write_bundle
from tests.ui_support import ScriptedUi, response, run as run_ui

SENTINEL = "private-nested-comparison-sentinel"
ABSENT = object()


def check(value, *, unequal=False, field="content"):
    return {"check": "field_not_equals" if unequal else "field_equals", "field": field, "value": value}


def request(sid="read", checks=None, *, ui=False, **extra):
    transport = {"method": "GET", "path": [sid]}
    step = {"id": sid, "expect": {"response": [{"check": "success"}] if checks is None else checks}, **extra}
    if ui:
        step.update(do="click", target="load")
        step["expect"]["request"] = transport
    else:
        step["do"] = {"request": transport}
    return step


def document(*steps, parameters=None, users=None):
    return {"schema_version": 1, "scenario": "comparison.example", "users": users or [],
            "parameters": parameters or {}, "steps": list(steps) or [request()]}


def load(*steps, parameters=None, users=None):
    return _load_document(document(*steps, parameters=parameters, users=users))


def resolver(scenario, step, template):
    return ports.RequestSpec(template.method, template.path, template.body)


def execute(scenario, payloads=None, *, mode="backend", normalizer=None, api=None, **kwargs):
    api = api or FakeApi({("GET", sid): {"json": response(fields)} for sid, fields in (payloads or {}).items()})
    options = dict(api=api, normalizer=normalizer or FakeNormalizer(), recorder=FakeRecorder(),
                   resolve_request=kwargs.pop("resolve_request", resolver), auth=FakeAuth(), **kwargs)
    result = (run_ui(scenario, None, **options) if mode == "e2e" else
              backend.run(scenario, state=None, **options))
    return result, api


def evaluate(actual, expected, *, unequal=False):
    fields = {} if actual is ABSENT else {"content": actual}
    return backend._eval_response(Assertion("field_not_equals" if unequal else "field_equals",
        {"field": "content", "value": expected}), ports.NormalizedResponse(True, fields, 200, None))


@pytest.mark.parametrize("term", ["field_equals", "field_not_equals"])
def test_terms_are_response_only_with_exact_parameters(term):
    assert vocabulary.required_params("response", term) == ("field", "value")
    assert not vocabulary.is_valid("frontend", term)
    assert not vocabulary.is_valid("backend_state", term)


@pytest.mark.parametrize("value", [None, False, True, 0, 1, 1.5, "", "text", {}, [],
    {"x": None, "list": [False, 0, 1.0, {"deep": []}]}, [[], {}, None]])
@pytest.mark.parametrize("unequal", [False, True])
def test_literal_and_parameter_domains_load_and_prepare(value, unequal):
    for declared in (value, {"from_parameter": "expected"}):
        scenario = load(request(checks=[check(declared, unequal=unequal)]), parameters={"expected": value})
        prepared, bound = prepare_step(scenario.steps[0], scenario, {})
        assert bound == {}
        assert type(prepared.expect.response[0].params["value"]) is type(value)
        assert prepared.expect.response[0].params["value"] == value


@pytest.mark.parametrize("key,value", [("field", ""), ("field", " "), ("field", 1),
    ("field", []), ("field", {"from_parameter": "name"}), ("extra", 1)])
@pytest.mark.parametrize("unequal", [False, True])
def test_bad_assertion_shape_rejected(key, value, unequal):
    assertion = check({}, unequal=unequal)
    assertion[key] = value
    with pytest.raises(DeclarationError):
        load(request(checks=[assertion]))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"),
    {"x": float("nan")}, [float("inf")], {1: "wrong"}, {"x": {1: "wrong"}},
    (), {"x": {1, 2}}, object()])
@pytest.mark.parametrize("unequal", [False, True])
def test_invalid_declared_data_rejected(value, unequal):
    with pytest.raises(DeclarationError):
        load(request(checks=[check(value, unequal=unequal)]))
    with pytest.raises(DeclarationError):
        load(request(checks=[check({"from_parameter": "expected"}, unequal=unequal)]),
             parameters={"expected": value})


@pytest.mark.parametrize("unequal", [False, True])
def test_duplicate_and_presence_conflicts_rejected(unequal):
    assertion = check({}, unequal=unequal)
    with pytest.raises(DeclarationError, match="duplicate"):
        load(request(checks=[assertion, copy.deepcopy(assertion)]))
    with pytest.raises(DeclarationError, match="field_absent conflicts"):
        load(request(checks=[assertion, {"check": "field_absent", "field": "content"}]))
    assert len(load(request(checks=[check({}), check([], unequal=True)])).steps[0].expect.response) == 2


@pytest.mark.parametrize("assertion,point", [
    ({"check": "object_field_equals", "anchor": "rows", "id": {"from_parameter": "id"}, "field": "x", "value": {}}, "ui"),
    ({"check": "objects_matching_count", "anchor": "rows", "field": "x", "value": [], "count": 1}, "ui"),
    ({"check": "span_attr", "span": "save", "attr": "x", "op": "==", "value": {}}, "backend_state"),
    ({"check": "collection_matching_count", "field": "rows", "matching": {"x": []}, "count": 1}, "response"),
])
def test_unrelated_assertions_do_not_gain_container_domain(assertion, point):
    step = request(checks=[])
    step["expect"][point] = [assertion]
    with pytest.raises(DeclarationError):
        load(step, parameters={"id": "one"})


@pytest.mark.parametrize("location", ["path", "query", "headers"])
def test_transport_value_domains_unchanged(location):
    step = request()
    step["do"]["request"][location] = [{}] if location == "path" else {"x": {}}
    with pytest.raises(DeclarationError):
        load(step)


@pytest.mark.parametrize("actual,expected,equal", [
    ({"x": [1, {"a": None, "b": False}]}, {"x": [1, {"b": False, "a": None}]}, True),
    ({"x": 1, "extra": 2}, {"x": 1}, False), ({"x": 1}, {"x": 1, "extra": 2}, False),
    ({"x": [1, 2]}, {"x": [2, 1]}, False), ([1, 2], [1], False),
    ({"x": False}, {"x": 0}, False), ({"x": True}, {"x": 1}, False),
    ([0], [False], False), ([1], [True], False), ([1], [1.0], False),
    ([1.0], [1], False), (["1"], [1], False), ({}, [], False), ([], {}, False),
    (None, None, True), ([], [], True), ({}, {}, True), ("", None, False),
    (0, False, False), (False, 0, False), (True, 1, False), (1, True, False),
    (1, 1.0, False), (1.0, 1, False), (None, {}, False), ([], None, False),
])
def test_complete_type_strict_comparison_and_complement(actual, expected, equal):
    assert evaluate(actual, expected).ok is equal
    assert evaluate(actual, expected, unequal=True).ok is not equal


@pytest.mark.parametrize("expected", [None, False, "", [], {}, {"secret": SENTINEL}])
@pytest.mark.parametrize("unequal", [False, True])
def test_missing_current_field_never_satisfies_comparison(expected, unequal):
    result = evaluate(ABSENT, expected, unequal=unequal)
    assert not result.ok and "missing" in result.detail
    assert SENTINEL not in repr(result)


def malformed_values():
    cycle_list = []
    cycle_list.append(cycle_list)
    cycle_dict = {}
    cycle_dict["secret"] = cycle_dict
    return [float("nan"), float("inf"), {"nested": float("inf")}, {1: SENTINEL},
            (), object(), {"nested": {1, 2}}, cycle_list, cycle_dict]


@pytest.mark.parametrize("actual", malformed_values())
@pytest.mark.parametrize("unequal", [False, True])
def test_invalid_observation_errors_before_type_mismatch(actual, unequal):
    with pytest.raises(ValueError) as error:
        evaluate(actual, "different-type", unequal=unequal)
    assert SENTINEL not in str(error.value)


@pytest.mark.parametrize("mode", ["backend", "e2e"])
@pytest.mark.parametrize("unequal,actual,status", [
    (False, {"nested": [None, False]}, "PASSED"),
    (False, {"nested": [None, 0]}, "FAILED"),
    (True, {"nested": [None, False]}, "FAILED"),
    (True, {"nested": [None, 0]}, "PASSED"),
])
def test_runtime_contract_and_failure_continuation_agree(mode, unequal, actual, status):
    scenario = load(request("read", [check({"nested": [None, False]}, unequal=unequal)]), request("later"))
    result, api = execute(scenario, {"read": {"content": actual}, "later": {}}, mode=mode)
    assert [s.status for s in result.steps] == [status, "PASSED"]
    assert result.steps[1].after_failures == (["read"] if status == "FAILED" else [])
    assert len(api.sent) == 2
    checked = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert checked.status == status


@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_explicit_stop_retains_failure_and_blocks_following(mode):
    scenario = load(request("read", [check({})], on_failure="stop"), request("later"))
    result, api = execute(scenario, {"read": {"content": {"changed": True}}}, mode=mode)
    assert [s.status for s in result.steps] == ["FAILED", "BLOCKED"]
    assert len(api.sent) == 1


@pytest.mark.parametrize("mode", ["backend", "e2e"])
@pytest.mark.parametrize("source", [ABSENT, None, *malformed_values()])
def test_unavailable_response_reference_blocks_atomically_without_send(source, mode):
    scenario = load(request("source", []), request("consumer", [check(
        {"from_step": "source", "response_field": "content"}, unequal=True)]), request("independent"))
    class SourceNormalizer(FakeNormalizer):
        def normalize(self, raw):
            norm = super().normalize(raw)
            if raw.request.path == "source":
                norm.fields = {} if source is ABSENT else {"content": source}
            return norm
    result, api = execute(scenario, mode=mode, normalizer=SourceNormalizer())
    assert [s.status for s in result.steps] == ["COMPLETED", "BLOCKED", "PASSED"]
    assert result.steps[1].resolved_bindings == {}
    assert [s.path for s in api.sent] == ["source", "independent"]


@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_failed_source_assertion_retains_response_and_nested_references(mode):
    reference = {"from_step": "source", "response_field": "content"}
    scenario = load(request("source", [check("unexpected", field="label")]),
        request("consumer", [check({"wrapped": [reference, {"from_parameter": "extra"}]})]),
        parameters={"extra": {"tags": [None, False]}})
    payloads = {"source": {"content": {"name": "actual"}, "label": "wrong"},
        "consumer": {"content": {"wrapped": [{"name": "actual"}, {"tags": [None, False]}]}}}
    result, _ = execute(scenario, payloads, mode=mode)
    assert [s.status for s in result.steps] == ["FAILED", "PASSED"]
    assert result.steps[1].after_failures == ["source"]
    assert list(result.steps[1].resolved_bindings.values()) == [{"name": "actual"}]
    checked = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert checked.status == "FAILED"
    assert len(checked.checks) == 1 and checked.checks[0].step == "source"


@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_reference_shaped_runtime_dictionary_is_only_data(mode):
    data = {"from_step": "not-executable", "response_field": "secret", "nested": {"from_parameter": "missing"}}
    scenario = load(request("source", []), request("consumer", [check(
        {"from_step": "source", "response_field": "content"})]))
    result, _ = execute(scenario, {"source": {"content": data}, "consumer": {"content": data}}, mode=mode)
    assert result.status == "PASSED"
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"


def test_contract_retains_both_terms_and_hides_nested_values():
    expected = {SENTINEL: [SENTINEL, None]}
    scenario = load(request(checks=[check(expected), check(expected, unequal=True)]))
    consumer = store.consumer_contract(scenario)
    shape = next(iter(consumer.entries.values()))
    assert [a.check for a in shape.field_constraints] == ["field_equals", "field_not_equals"]
    result, _ = execute(scenario, {"read": {"content": expected}})
    provider = store.provider_contract(result.provider_recordings, FakeNormalizer())
    mismatches = store.diff(consumer, provider)
    assert len(mismatches) == 1 and len(mismatches[0].field_errors) == 1
    report = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert report.status == "FAILED"
    assert SENTINEL not in repr(consumer) + repr(provider) + repr(mismatches) + repr(result) + repr(report)
    assert SENTINEL not in "".join(c.detail for c in report.checks + result.checks)


@pytest.mark.parametrize("observed", [ABSENT, *malformed_values()])
def test_contract_missing_or_invalid_observed_evidence_never_passes(observed):
    scenario = load(request(checks=[check({}, unequal=True)]))
    fields = {} if observed is ABSENT else {"content": observed}
    class FixedNormalizer(FakeNormalizer):
        def normalize(self, raw):
            return dataclasses.replace(super().normalize(raw), fields=fields)
    result, _ = execute(load(request()))
    checked = contract.run(scenario, result.provider_recordings, FixedNormalizer(), execution_steps=result.steps)
    assert checked.steps[0].status == ("FAILED" if observed is ABSENT else "ERROR")
    assert checked.status == "FAILED"
    assert SENTINEL not in repr(checked)


@pytest.mark.parametrize("missing", [False, True])
def test_contract_missing_and_null_source_cannot_be_inequality_evidence(missing):
    scenario = load(request("source", []), request("consumer", [check(
        {"from_step": "source", "response_field": "content"}, unequal=True)]))
    result, _ = execute(load(request("source"), request("consumer")),
        {"source": {} if missing else {"content": None}, "consumer": {"content": {}}})
    checked = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert checked.status == "FAILED"


@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_reused_normalizer_buffer_cannot_rewrite_prior_baseline(mode):
    scenario = load(request("source", [check({"name": "before"})]), request("consumer", [check(
        {"from_step": "source", "response_field": "content"})]))
    class ReusingNormalizer(FakeNormalizer):
        def __init__(self):
            self.buffer = {"name": "before"}
        def normalize(self, raw):
            self.buffer["name"] = "before" if raw.request.path == "source" else "after"
            return dataclasses.replace(super().normalize(raw), fields={"content": self.buffer})
    result, _ = execute(scenario, mode=mode, normalizer=ReusingNormalizer())
    assert [s.status for s in result.steps] == ["PASSED", "FAILED"]
    assert list(result.steps[1].resolved_bindings.values()) == [{"name": "before"}]
    checked = contract.run(scenario, result.provider_recordings, ReusingNormalizer(), execution_steps=result.steps)
    assert checked.status == "FAILED" and checked.checks[0].step == "consumer"


@pytest.mark.parametrize("mode", ["mock", "live"])
def test_ui_mutation_cannot_rewrite_prior_or_current_expected_containers(mode):
    reference = {"from_step": "source", "response_field": "content"}
    scenario = load(request("source", [check({"name": "before"})], ui=True),
        request("consumer", [check(reference)], ui=True), request("again", [check(reference)], ui=True))
    class MutatingUi(ScriptedUi):
        def perform_step(self, scenario, step, context, permit):
            if step.id == "consumer":
                step.expect.response[0].params["value"]["name"] = "after"
                for value in permit.resolved_bindings.values():
                    value["name"] = "after"
            return super().perform_step(scenario, step, context, permit)
    ui = MutatingUi(count=3, payloads=[response({"content": {"name": name}}) for name in ("before", "after", "before")],
        requests=[[ports.RequestSpec("GET", sid)] for sid in ("source", "consumer", "again")])
    result = run_ui(scenario, ui, mode=mode)
    assert [s.status for s in result.steps] == ["PASSED", "FAILED", "PASSED"]
    assert list(result.steps[2].resolved_bindings.values()) == [{"name": "before"}]
    # C-5 keeps its documented shallow diagnostic relationship within a step.
    key = next(iter(result.steps[1].resolved_bindings))
    assert result.steps[1].resolved_bindings[key] is ui.permits[1].resolved_bindings[key]


def test_normalization_does_not_validate_unrelated_field_domains():
    opaque = object()
    class Normalizer(FakeNormalizer):
        def normalize(self, raw):
            return dataclasses.replace(super().normalize(raw), fields={"unrelated": opaque})
    result, _ = execute(load(request()), normalizer=Normalizer())
    assert result.status == "PASSED"


def test_named_result_include_nested_values_and_review_rendering(tmp_path):
    child = document(request("read", [check({"from_parameter": "expected"})]),
        parameters={"expected": {"name": "before"}}, users=["child_user"])
    child["scenario"] = "shared.read"
    child["results"] = {"content": {"from_step": "read", "response_field": "content"}}
    root = document({"id": "setup", "do": {"include": "shared.read"},
        "with": {"expected": {"from_parameter": "expected"}}},
        request("consumer", [check({"wrapped": [{"from_step": "setup", "result": "content"}]}),
                             check({"from_parameter": "other"}, unequal=True)]),
        parameters={"expected": {"name": "before"}, "other": []}, users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child)
    scenario = load_scenario(path)
    result, _ = execute(scenario, {"read": {"content": {"name": "before"}},
        "consumer": {"content": {"wrapped": [{"name": "before"}]}}})
    assert result.status == "PASSED"
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"
    expanded = expansion_view(scenario)
    value = expanded["steps"][1]["expect"]["response"][0]["value"]
    assert value["entries"]["wrapped"]["items"][0]["from_step"] == "setup/read"
    positions = list(_values(root["steps"][1], 1))
    assert any(list(_references(value, location)) for location, value in positions)


@pytest.mark.parametrize("policy,status", [("FAIL", "FAILED"), ("SKIP", "SKIPPED")])
def test_polling_uses_complete_comparison_and_preserves_timeout_semantics(policy, status):
    scenario = load(request("poll", [check({"ready": [True]})], poll={"on_timeout": policy}), request("after"))
    clock = [0.0]
    result, _ = execute(scenario, {"poll": {"content": {"ready": [1]}}},
        poll_config=PollConfig(timeout=2, interval=1), now=lambda: clock[0],
        sleep=lambda delay: clock.__setitem__(0, clock[0] + delay))
    assert result.steps[0].status == status
    assert result.steps[1].status == ("BLOCKED" if policy == "SKIP" else "PASSED")
    assert result.status == ("DEGRADED" if policy == "SKIP" else "FAILED")
    assert sum(r.is_final for r in result.provider_recordings if r.step_id == "poll") == 0


def test_polling_inequality_waits_for_genuine_valid_difference():
    scenario = load(request("poll", [check({"ready": [False]}, unequal=True)], poll={"on_timeout": "FAIL"}))
    class ChangingApi(FakeApi):
        def send(self, spec, session):
            raw = super().send(spec, session)
            raw.json = response({"content": {"ready": [len(self.sent) > 1]}})
            return raw
    clock = [0.0]
    result, _ = execute(scenario, api=ChangingApi(), poll_config=PollConfig(timeout=2, interval=1),
        now=lambda: clock[0], sleep=lambda delay: clock.__setitem__(0, clock[0] + delay))
    assert result.status == "PASSED" and result.steps[0].attempts == 2
    assert [r.is_final for r in result.provider_recordings] == [False, True]


def test_scalar_equality_diagnostic_stays_compatible_and_inequality_is_value_free():
    assert evaluate(2, 1).detail == "field='content' expected=1 observed=2"
    assert evaluate(ABSENT, 1).detail == "field='content' expected=1 observed=<missing>"
    assert SENTINEL not in evaluate(SENTINEL, SENTINEL, unequal=True).detail
    assert SENTINEL not in evaluate({SENTINEL: SENTINEL}, {}).detail
    assert SENTINEL not in evaluate({}, {SENTINEL: SENTINEL}).detail


@pytest.mark.parametrize("missing", ["field", "value"])
@pytest.mark.parametrize("unequal", [False, True])
def test_comparison_requires_both_parameters(missing, unequal):
    assertion = check({}, unequal=unequal)
    del assertion[missing]
    with pytest.raises(DeclarationError, match="missing required"):
        load(request(checks=[assertion]))


@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_cross_user_reference_keeps_actual_source_identity(mode):
    scenario = load(request("source", [check([{"v": 1}])], user="creator"),
        request("consumer", [check({"from_step": "source", "response_field": "content"})], user="peer"),
        users=["creator", "peer"])
    result, _ = execute(scenario, {sid: {"content": [{"v": 1}]} for sid in ("source", "consumer")}, mode=mode)
    assert result.status == "PASSED"
    assert result.steps[1].user == "peer"
    assert next(iter(result.steps[1].binding_sources.values())).origin.user == "creator"
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"


def test_contract_order_duplicate_missing_and_changed_recording_controls():
    scenario = load(request("source", [check({"name": "before"})]),
        request("consumer", [check({"from_step": "source", "response_field": "content"}),
                             check({"name": "after"}, unequal=True)]))
    result, _ = execute(scenario, {sid: {"content": {"name": "before"}} for sid in ("source", "consumer")})
    def inspect(recordings):
        return contract.run(scenario, recordings, FakeNormalizer(), execution_steps=result.steps)
    assert inspect(list(reversed(result.provider_recordings))).status == "PASSED"
    duplicate = [*result.provider_recordings, copy.deepcopy(result.provider_recordings[0])]
    assert inspect(duplicate).steps[0].status == "ERROR"
    assert inspect(result.provider_recordings[1:]).status == "FAILED"
    changed = copy.deepcopy(result.provider_recordings)
    changed[1].json["data"]["content"]["name"] = "after"
    assert inspect(changed).status == "FAILED"
    changed[0].user = "forged"
    assert inspect(changed).steps[0].status == "ERROR"


def test_include_with_nested_response_reference_is_resolved_in_contract(tmp_path):
    child = document(request("child_read", [check({"from_parameter": "expected"})]),
        parameters={"expected": {}}, users=["child_user"])
    child["scenario"] = "shared.compare"
    root = document(request("source", [check({"nested": [None, False]})]),
        {"id": "included", "do": {"include": "shared.compare"}, "with": {"expected": {
            "wrapped": {"from_step": "source", "response_field": "content"}}}}, users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child)
    scenario = load_scenario(path)
    result, _ = execute(scenario, {"source": {"content": {"nested": [None, False]}},
        "child_read": {"content": {"wrapped": {"nested": [None, False]}}}})
    assert result.status == "PASSED"
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"


def test_prepared_expectation_does_not_alias_diagnostic_binding_or_prior():
    scenario = load(request("source", []), request("consumer", [check(
        {"from_step": "source", "response_field": "content"})]))
    observed = {"name": "before"}
    prior = {"source": ports.NormalizedResponse(True, {"content": observed}, 200, None)}
    prepared, bound = prepare_step(scenario.steps[1], scenario, prior)
    value = next(iter(bound.values()))
    assert value is not observed
    assert prepared.expect.response[0].params["value"] is not value
    value["name"] = "after"
    assert observed == {"name": "before"}
    assert prepared.expect.response[0].params["value"] == {"name": "before"}


@pytest.mark.parametrize("unequal", [False, True])
def test_shared_acyclic_members_are_ordinary_data_not_cycles(unequal):
    member = {"name": "one"}
    observed = [member, member]
    expected = [{"name": "one"}, {"name": "one"}]
    assert evaluate(observed, expected, unequal=unequal).ok is not unequal


class NoCopy:
    def __copy__(self):
        raise AssertionError(SENTINEL)

    def __deepcopy__(self, memo):
        raise AssertionError(SENTINEL)

    def __reduce__(self):
        raise AssertionError(SENTINEL)


@pytest.mark.parametrize("opaque", [threading.Lock(), MappingProxyType({"secret": SENTINEL}), NoCopy()])
@pytest.mark.parametrize("nested", [False, True])
def test_opaque_normalized_values_preserve_old_checks_and_reject_new_comparisons(opaque, nested):
    value = {"nested": [opaque]} if nested else opaque
    class Normalizer(FakeNormalizer):
        def normalize(self, raw):
            return dataclasses.replace(super().normalize(raw), fields={"content": value})
    normalizer = Normalizer()
    scenario = load(request(checks=[{"check": "success"}, {"check": "has", "field": "content"}]))
    result, _ = execute(scenario, normalizer=normalizer)
    assert result.status == "PASSED"
    assert contract.run(scenario, result.provider_recordings, normalizer,
                        execution_steps=result.steps).status == "PASSED"
    for unequal in (False, True):
        comparison = load(request(checks=[check("different", unequal=unequal)]))
        actual, _ = execute(comparison, normalizer=normalizer)
        assert actual.steps[0].status == "ERROR"
        inspected = contract.run(comparison, result.provider_recordings, normalizer,
                                 execution_steps=result.steps)
        assert inspected.steps[0].status == "ERROR"
        assert SENTINEL not in actual.steps[0].detail + inspected.steps[0].detail


@pytest.mark.parametrize("opaque", [threading.Lock(), MappingProxyType({"secret": SENTINEL}), NoCopy()])
def test_opaque_response_dependency_is_structured_blocked_or_contract_error(opaque):
    scenario = load(request("source", [{"check": "has", "field": "content"}]),
        request("consumer", [check({"from_step": "source", "response_field": "content"}, unequal=True)]))
    class Normalizer(FakeNormalizer):
        def normalize(self, raw):
            return dataclasses.replace(super().normalize(raw), fields={"content": opaque})
    result, api = execute(scenario, normalizer=Normalizer())
    assert [step.status for step in result.steps] == ["PASSED", "BLOCKED"]
    assert len(api.sent) == 1 and result.steps[1].resolved_bindings == {}
    inspected = contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=result.steps)
    assert inspected.steps[0].status == "ERROR"
    assert SENTINEL not in inspected.steps[0].detail
