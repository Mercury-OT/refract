"""One bounded response predicate across declarations, execution and contracts."""
import copy
import dataclasses

import pytest
import yaml

from refracto import ports
from refracto.contract import store
from refracto.declaration import vocabulary
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.model import Assertion, Input, ValueRef
from refracto.projection import backend, contract
from refracto.report import RunReport
from refracto.runner import PollConfig
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.ui_support import ScriptedUi, response, run as run_ui


def check(matching=None, count=1, field="records"):
    return {"check": "collection_matching_count", "field": field,
            "matching": {"id": "wanted"} if matching is None else matching, "count": count}


def request(sid="list", checks=None, **extra):
    return {"id": sid, "do": {"request": {"method": "GET", "path": [sid]}},
            "expect": {"response": [check()] if checks is None else checks}, **extra}


def load(tmp_path, steps=None, **extra):
    raw = {"schema_version": 1, "scenario": "collection.check", "actor": "reader",
           "steps": [request()] if steps is None else steps, **extra}
    path = tmp_path / "collection.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return load_scenario(path)


def evaluate(fields, matching=None, count=1, **kwargs):
    raw = check(matching, count)
    return backend._eval_response(
        Assertion(raw.pop("check"), raw), ports.NormalizedResponse(True, fields, 200, None), **kwargs)


def execute(scenario, payloads=None, **kwargs):
    api = kwargs.pop("api", None) or FakeApi({
        ("GET", sid): {"json": response(data)} for sid, data in (payloads or {}).items()})
    result = backend.run(scenario, auth=FakeAuth(), api=api, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer(),
        resolve_request=lambda s, st, t: ports.RequestSpec(t.method, t.path, t.body), **kwargs)
    return result, api


def test_vocabulary_and_default_loading(tmp_path):
    assert vocabulary.required_params("response", "collection_matching_count") == ("field", "matching", "count")
    assert not vocabulary.is_valid("frontend", "collection_matching_count")
    assert load(tmp_path).steps[0].expect.response[0].params == {
        "field": "records", "matching": {"id": "wanted"}, "count": 1}


@pytest.mark.parametrize("key,value", [
    ("field", ""), ("field", "  "), ("field", 1), ("field", []),
    ("matching", {}), ("matching", []), ("matching", None),
    ("matching", {"": "x"}), ("matching", {1: "x"}),
    ("matching", {"id": []}), ("matching", {"id": {"literal": 1}}),
    ("matching", {"id": float("inf")}), ("matching", {"id": float("nan")}),
    ("count", True), ("count", False), ("count", -1), ("count", 1.0),
    ("count", "1"), ("count", {"from_parameter": "n"}), ("unknown", 1),
])
def test_loader_rejects_invalid_shape(tmp_path, key, value):
    assertion = check()
    assertion[key] = value
    with pytest.raises(DeclarationError):
        load(tmp_path, [request(checks=[assertion])], parameters={"n": 1})


@pytest.mark.parametrize("key", ["field", "matching", "count"])
def test_loader_requires_all_three_parameters(tmp_path, key):
    assertion = check()
    del assertion[key]
    with pytest.raises(DeclarationError, match="missing required"):
        load(tmp_path, [request(checks=[assertion])])


def test_duplicate_yaml_matching_key_rejected(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text("""schema_version: 1
scenario: collection.duplicate
actor: reader
steps:
  - id: list
    do: {request: {method: GET, path: [records]}}
    expect:
      response:
        - check: collection_matching_count
          field: records
          matching: {id: one, id: two}
          count: 1
""", encoding="utf-8")
    with pytest.raises(DeclarationError, match="duplicate"):
        load_scenario(path)


@pytest.mark.parametrize("reference", [
    {"from_parameter": "missing"}, {"from_parameter": "name", "extra": 0},
    {"from_step": "later", "response_field": "id"},
    {"from_step": "source", "response_field": "id"},
    {"from_input": "name"}, {"from_step": "source", "response_field": ""},
])
def test_reference_validation(tmp_path, reference):
    with pytest.raises(DeclarationError):
        load(tmp_path, [{"id": "source", "do": "open", "target": "page"},
                        request(checks=[check({"id": reference})])], parameters={"name": "x"})


@pytest.mark.parametrize("parameter", [[], {}, [1], {"id": 1}])
def test_known_container_parameter_rejected_at_load(tmp_path, parameter):
    with pytest.raises(DeclarationError, match="parameter must be a finite scalar"):
        load(tmp_path, [request(checks=[check({"id": {"from_parameter": "value"}})])],
             parameters={"value": parameter})


@pytest.mark.parametrize("value", [None, False, 0, "", True, 1, 1.5, "text"])
def test_scalar_parameters_and_literals_are_valid(tmp_path, value):
    scenario = load(tmp_path, [request(checks=[check({"id": {"from_parameter": "value"}, "other": value})])],
                    parameters={"value": value})
    result, _ = execute(scenario, {"list": {"records": [{"id": value, "other": value}]}})
    assert result.status == "PASSED"


def test_multiple_constraints_preserved_and_absence_conflicts_even_zero(tmp_path):
    checks = [check(), check({"name": "x"}), check(), {"check": "has", "field": "records"}]
    assert len(load(tmp_path, [request(checks=checks)]).steps[0].expect.response) == 4
    for count in (0, 1):
        with pytest.raises(DeclarationError, match="field_absent conflicts"):
            load(tmp_path, [request(checks=[check(count=count), {"check": "field_absent", "field": "records"}])])


@pytest.mark.parametrize("rows,matching,count,passed", [
    ([{"id": "other"}, {"id": "wanted", "extra": "allowed"}], {"id": "wanted"}, 1, True),
    ([{"id": "wanted"}, {"id": "other"}], {"id": "wanted"}, 1, True),
    ([{"id": "wanted"}, {"name": "right"}], {"id": "wanted", "name": "right"}, 1, False),
    ([{"id": "wanted"}, {"id": "wanted"}], {"id": "wanted"}, 1, False),
    ([{"id": "wanted"}, {"id": "wanted"}], {"id": "wanted"}, 2, True),
    ([{"id": False}], {"id": 0}, 1, False), ([{"id": 0}], {"id": False}, 1, False),
    ([{"id": True}], {"id": 1}, 1, False), ([{"id": 1}], {"id": True}, 1, False),
    ([{"id": "1"}], {"id": 1}, 1, False), ([{"id": 1}], {"id": 1.0}, 1, False),
    ([{}], {"id": None}, 1, False), ([{"id": None}], {"id": None}, 1, True),
    ([], {"id": "wanted"}, 0, True), ([], {"id": "wanted"}, 1, False),
    ([{"id": "other"}], {"id": "wanted"}, 0, True),
    ([{"id": "wanted"}, None], {"id": "wanted"}, 1, False),
    ([{}, None], {"id": "wanted"}, 0, False),
    ([False], {"id": "wanted"}, 0, False), ([[]], {"id": "wanted"}, 0, False),
])
def test_exact_content_matching(rows, matching, count, passed):
    original = copy.deepcopy(rows)
    assert evaluate({"records": rows}, matching, count).ok is passed
    assert rows == original


@pytest.mark.parametrize("fields,reason", [
    ({}, "missing"), ({"records": None}, "not a list"),
    ({"records": {}}, "not a list"), ({"records": "[]"}, "not a list"),
    ({"records": ()}, "not a list"), ({"records": [None]}, "non-object"),
])
def test_malformed_collection_never_counts_as_zero(fields, reason):
    result = evaluate(fields, count=0)
    assert not result.ok and reason in result.detail


@pytest.mark.parametrize("value", [False, 0, "", True, 1, "wanted"])
def test_backend_actual_prior_response_and_parameter_resolution(tmp_path, value):
    scenario = load(tmp_path, [request("create", checks=[]), request(checks=[check({
        "id": {"from_step": "create", "response_field": "id"},
        "name": {"from_parameter": "name"}})])], parameters={"name": "chosen"})
    result, api = execute(scenario, {"create": {"id": value}, "list": {"records": [
        {"id": "noise", "name": "chosen"}, {"id": value, "name": "chosen"}]}})
    assert [s.status for s in result.steps] == ["COMPLETED", "PASSED"]
    assert list(result.steps[1].resolved_bindings.values()) == [value]
    assert len(api.sent) == 2
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer()).status == "PASSED"


@pytest.mark.parametrize("source", [{}, {"id": None}, {"id": []}, {"id": {}}, {"id": float("inf")}])
def test_missing_null_or_nonscalar_source_blocks_before_action_atomically(tmp_path, source):
    scenario = load(tmp_path, [request("create", checks=[]), request(checks=[check({
        "valid": {"from_step": "create", "response_field": "valid"},
        "id": {"from_step": "create", "response_field": "id"}})]), request("blocked")])
    result, api = execute(scenario, {"create": {"valid": "secret-first", **source}})
    assert [s.status for s in result.steps] == ["COMPLETED", "BLOCKED", "FAILED"]
    assert result.steps[1].resolved_bindings == {}
    assert len(api.sent) == 2
    assert "secret-first" not in result.steps[1].detail


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("correct", [True, False])
def test_ui_and_e2e_reuse_response_content_semantics(tmp_path, mode, correct):
    steps = [
        {"id": "create", "do": "click", "target": "create", "expect": {
            "request": {"method": "POST", "path": ["records"]}, "response": [{"check": "has", "field": "id"}]}},
        {"id": "list", "do": "click", "target": "refresh", "expect": {
            "request": {"method": "GET", "path": ["records"]}, "response": [check({
                "id": {"from_step": "create", "response_field": "id"},
                "name": {"from_parameter": "name"}})]}},
        {"id": "after", "do": "click", "target": "after"},
    ]
    scenario = load(tmp_path, steps, parameters={"name": "right"})
    ui = ScriptedUi(count=3, payloads=[response({"id": 7}), response({"records": [
        {"id": 0, "name": "right"}, {"id": 7, "name": "right" if correct else "wrong"}]}), response()],
        requests=[[ports.RequestSpec("POST", "records")], [ports.RequestSpec("GET", "records")], []])
    result = run_ui(scenario, ui, mode=mode)
    assert [s.status for s in result.steps] == (["PASSED", "PASSED", "COMPLETED"] if correct
                                               else ["PASSED", "FAILED", "COMPLETED"])
    assert len(ui.permits) == 3
    assert list(result.steps[1].resolved_bindings.values()) == [7]
    assert ui.open_calls == ui.close_calls == 1


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_ui_nonscalar_reference_blocks_only_second_action(tmp_path, mode):
    steps = [
        {"id": "source", "do": "click", "target": "source", "expect": {
            "request": {"method": "POST", "path": ["items"]}, "response": [{"check": "success"}]}},
        {"id": "list", "do": "click", "target": "list", "expect": {
            "request": {"method": "POST", "path": ["items"]},
            "response": [check({"id": {"from_step": "source", "response_field": "id"}})]}},
        {"id": "blocked", "do": "click", "target": "blocked"},
    ]
    scenario = load(tmp_path, steps)
    ui = ScriptedUi(payloads=[response({"id": ["sensitive"]}), response({"records": []})],
                    requests=[[ports.RequestSpec("POST", "items")]] * 2)
    result = run_ui(scenario, ui, mode=mode)
    assert [s.status for s in result.steps] == ["PASSED", "BLOCKED", "COMPLETED"]
    assert len(ui.permits) == 2 and result.steps[1].resolved_bindings == {}


class Clock:
    def __init__(self): self.value = 0
    def now(self): return self.value
    def sleep(self, seconds): self.value += seconds


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("policy,ready", [("FAIL", True), ("FAIL", False), ("SKIP", False)])
def test_polling_real_attempts_and_terminal_semantics(tmp_path, projection, policy, ready):
    scenario = load(tmp_path, [request(poll={"on_timeout": policy}), request("after", checks=[{"check": "success"}])])
    class Api(FakeApi):
        def send(self, spec, session):
            self.responses = {("GET", "list"): {"json": response({"records":
                [{"id": "wanted"}] if ready and self.sent else []})}}
            return super().send(spec, session)
    api, clock = Api(), Clock()
    timing = {"poll_config": PollConfig(timeout=1, interval=1), "now": clock.now, "sleep": clock.sleep}
    if projection == "backend":
        result, _ = execute(scenario, api=api, **timing)
    else:
        result = run_ui(scenario, None, api=api,
            resolve_request=lambda s, st, t: ports.RequestSpec(t.method, t.path, t.body), **timing)
    assert [s.status for s in result.steps] == (["PASSED", "PASSED"] if ready else
        (["FAILED", "PASSED"] if policy == "FAIL" else ["SKIPPED", "BLOCKED"]))
    records = [r for r in result.provider_recordings if r.step_id == "list"]
    assert len(records) == 2 and records[0].is_final is False
    assert records[-1].is_final is ready
    if ready:
        assert contract.run(scenario, result.provider_recordings, FakeNormalizer()).status == "PASSED"


def recordings(scenario, payloads):
    return [ports.RecordedResponse(200, {}, response(data), "", None,
        ports.RequestSpec(step.request.method, step.request.path), step_id=step.id,
        template_path=step.request.path) for step, data in zip(scenario.steps, payloads)]


def test_contract_keeps_all_samefield_constraints_and_dataclass_compatibility(tmp_path):
    scenario = load(tmp_path, [request(checks=[check({"id": "wanted"}), check({"name": "right"}), check({"id": "wanted"})])])
    consumer = store.consumer_contract(scenario)
    shape = next(iter(consumer.entries.values()))
    assert len(shape.collection_constraints) == 3
    assert "collection_constraints" not in store.EndpointShape.__match_args__
    assert "collection_errors" not in store.ContractMismatch.__match_args__
    assert store.EndpointShape(frozenset()).collection_constraints is not store.EndpointShape(frozenset()).collection_constraints
    assert "wanted" not in repr(shape)
    rows = [{"id": "wanted", "name": "wrong"}]
    raw = recordings(scenario, [{"records": rows}])
    before = copy.deepcopy(raw)
    result = contract.run(scenario, raw, FakeNormalizer())
    assert result.status == "FAILED"
    mismatch = store.diff(consumer, store.provider_contract(raw, FakeNormalizer()))[0]
    assert len(mismatch.collection_errors) == 1
    assert "matching_keys=['name']" in mismatch.collection_errors[0]
    assert raw == before


@pytest.mark.parametrize("fields", [{}, {"records": None}, {"records": [None]}, {"records": [{"id": "wrong"}]}])
def test_contract_rejects_missing_malformed_or_changed_contents(tmp_path, fields):
    scenario = load(tmp_path)
    assert contract.run(scenario, recordings(scenario, [fields]), FakeNormalizer()).status == "FAILED"


def test_contract_uses_only_final_recording_not_earlier_matching_attempt(tmp_path):
    scenario = load(tmp_path)
    raw = recordings(scenario, [{"records": [{"id": "wanted"}]}])
    raw[0].is_final = False
    assert contract.run(scenario, raw, FakeNormalizer()).status == "FAILED"
    raw += recordings(scenario, [{"records": [{"id": "wrong"}]}])
    assert contract.run(scenario, raw, FakeNormalizer()).status == "FAILED"
    raw[-1].json = response({"records": [{"id": "wanted"}]})
    assert contract.run(scenario, raw, FakeNormalizer()).status == "PASSED"


@pytest.mark.parametrize("source", [{}, {"id": None}, {"id": []}, {"id": {}}])
def test_contract_invalid_reference_never_passes_even_with_matching_shape(tmp_path, source):
    scenario = load(tmp_path, [request("source", checks=[]), request(checks=[check({
        "id": {"from_step": "source", "response_field": "id"}})])])
    raw = recordings(scenario, [source, {"records": [{"id": source.get("id")}]}])
    result = contract.run(scenario, raw, FakeNormalizer())
    assert result.status == "FAILED"


def test_new_diagnostics_never_expose_expected_or_observed_secrets(tmp_path):
    secret, observed = "expected-secret-sentinel", "observed-secret-sentinel"
    scenario = load(tmp_path, [request(checks=[check({"name": secret})])])
    result, _ = execute(scenario, {"list": {"records": [{"name": observed, "other": secret}]}})
    raw = result.provider_recordings
    contract_result = contract.run(scenario, raw, FakeNormalizer())
    mismatches = store.diff(store.consumer_contract(scenario), store.provider_contract(raw, FakeNormalizer()))
    report = RunReport(scenario.id, [result, contract_result])
    surfaces = [repr(mismatches), repr(report), repr(result), repr(contract_result), str(report.localize())]
    surfaces += [c.detail for domain in report.domains for step in domain.steps for c in step.checks]
    assert result.status == contract_result.status == "FAILED"
    for surface in surfaces:
        assert secret not in surface and observed not in surface
    assert "expected_count=1 actual_count=0" in result.steps[0].checks[0].detail


def test_field_is_literal_top_level_key_not_jsonpath():
    raw = check(field="records.nested")
    assertion = Assertion(raw.pop("check"), raw)
    nested = ports.NormalizedResponse(True, {"records": {"nested": [{"id": "wanted"}]}}, 200, None)
    assert not backend._eval_response(assertion, nested).ok
    literal = dataclasses.replace(nested, fields={"records.nested": [{"id": "wanted"}]})
    assert backend._eval_response(assertion, literal).ok


def test_standalone_evaluator_resolves_existing_reference_values():
    result = evaluate({"records": [{"id": False}]}, {"id": ValueRef("input", "wanted")},
                      inputs=[Input("wanted", False)])
    assert result.ok
    assert not evaluate({"records": []}, {"id": ValueRef("bind", "missing")}, count=0).ok
