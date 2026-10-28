"""Semantic state declarations preserve bounded references and honest failures."""
import copy

import pytest

from refracto import ports
from refracto.declaration import object_state, vocabulary
from refracto.declaration.binding import InvalidDependency, MissingDependency, prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import _references, _values
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.model import ValueRef
from tests.test_scenario_include import write_bundle


def check(**overrides):
    return {"check": "object_field_equals", "object": "record",
            "id": {"from_parameter": "record_id"}, "field": "name", "value": "Example", **overrides}


def request(sid="read", assertions=None):
    return {"id": sid, "do": {"request": {"method": "GET", "path": ["records"]}},
            "expect": {"backend_state": [check()] if assertions is None else assertions}}


def document(*steps, parameters=None):
    return {"schema_version": 1, "scenario": "state.example", "users": ["reader"],
            "parameters": {"record_id": 22} if parameters is None else parameters,
            "steps": list(steps) or [request()]}


def load(*steps, parameters=None):
    return _load_document(document(*steps, parameters=parameters))


def norm(**fields):
    return ports.NormalizedResponse(True, fields, 200, None)


def test_vocabulary_keeps_frontend_distinct_and_state_fields_exact():
    assert vocabulary.required_params("backend_state", object_state.CHECK) == ("object", "id", "field", "value")
    assert vocabulary.required_params("frontend", object_state.CHECK) == ("anchor", "id", "field", "value")
    assert vocabulary.optional_params("backend_state", object_state.CHECK) == ()
    assert not vocabulary.is_valid("response", object_state.CHECK)


@pytest.mark.parametrize("name", ["object", "id", "field", "value"])
def test_required_state_fields_are_not_optional(name):
    assertion = check()
    del assertion[name]
    with pytest.raises(DeclarationError, match="missing required"):
        load(request(assertions=[assertion]))


@pytest.mark.parametrize("field,value", [
    ("object", ""), ("object", " "), ("object", 1), ("object", []),
    ("object", {"from_parameter": "name"}), ("field", ""), ("field", None),
    ("field", ["name"]), ("field", {"from_parameter": "name"}), ("sql", "SELECT 1"),
    ("anchor", "records"), ("table", "records"), ("default", "fallback"),
])
def test_state_names_are_literal_and_no_mechanical_or_extra_fields(field, value):
    with pytest.raises(DeclarationError):
        load(request(assertions=[check(**{field: value})]), parameters={"record_id": 22, "name": "name"})


@pytest.mark.parametrize("identity", [22, "22", None, False, [], {}, {"concat": ["id"]}])
def test_state_id_requires_existing_reference_not_a_literal(identity):
    with pytest.raises(DeclarationError):
        load(request(assertions=[check(id=identity)]))


@pytest.mark.parametrize("identity", [None, False, True, "", 1.0, [], {}, [22]])
def test_known_invalid_identity_parameter_rejected(identity):
    with pytest.raises(DeclarationError):
        load(parameters={"record_id": identity})


@pytest.mark.parametrize("identity", [0, -1, 22, "22", "record-22"])
def test_valid_identity_parameter_is_not_coerced(identity):
    scenario = load(parameters={"record_id": identity})
    prepared, bindings = prepare_step(scenario.steps[0], scenario, {})
    actual = prepared.expect.backend_state[0].params["id"]
    assert type(actual) is type(identity) and actual == identity
    assert bindings == {}


@pytest.mark.parametrize("expected", [None, False, True, 0, 1, 1.5, "", "Example"])
@pytest.mark.parametrize("parameter", [False, True])
def test_finite_scalar_expected_values_keep_null_and_falsy_types(expected, parameter):
    declared = {"from_parameter": "expected"} if parameter else expected
    scenario = load(request(assertions=[check(value=declared)]), parameters={"record_id": 22, "expected": expected})
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    actual = prepared.expect.backend_state[0].params["value"]
    assert type(actual) is type(expected) and actual == expected


@pytest.mark.parametrize("expected", [[], {}, [1], {"name": "Example"}, float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("parameter", [False, True])
def test_known_nonscalar_or_nonfinite_expected_rejected(expected, parameter):
    declared = {"from_parameter": "expected"} if parameter else expected
    with pytest.raises(DeclarationError):
        load(request(assertions=[check(value=declared)]), parameters={"record_id": 22, "expected": expected})


def test_new_state_expected_rejects_direct_concat_but_accepts_composed_parameter():
    with pytest.raises(DeclarationError, match="scalar or reference"):
        load(request(assertions=[check(value={"concat": ["Ex", "ample"]})]))
    scenario = load(request(assertions=[check(value={"from_parameter": "expected"})]),
                    parameters={"record_id": 22, "expected": {"concat": ["Ex", "ample"]}})
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    assert prepared.expect.backend_state[0].params["value"] == "Example"


@pytest.mark.parametrize("position", ["id", "value"])
@pytest.mark.parametrize("reference", [
    {"from_parameter": "unknown"}, {"from_step": "read", "response_field": "id"},
    {"from_step": "later", "response_field": "id"}, {"from_step": "source"},
    {"from_step": "source", "response_field": "id", "extra": True},
])
def test_state_references_keep_existing_load_time_constraints(position, reference):
    with pytest.raises(DeclarationError):
        load(request("source", []), request(assertions=[check(**{position: reference})]), request("later", []))


@pytest.mark.parametrize("position,value", [
    ("id", False), ("id", True), ("id", ""), ("id", 1.0), ("id", []), ("id", {}),
    ("value", []), ("value", {}), ("value", ["Example"]),
])
def test_invalid_response_derived_use_site_retains_blocking_source(position, value):
    scenario = load(request("source", []), request(assertions=[check(**{
        position: {"from_step": "source", "response_field": "observed"}})]))
    before = copy.deepcopy(scenario.steps[1])
    with pytest.raises(InvalidDependency) as failure:
        prepare_step(scenario.steps[1], scenario, {"source": norm(observed=value)})
    assert failure.value.sources == ["source"]
    assert scenario.steps[1] == before


@pytest.mark.parametrize("position", ["id", "value"])
@pytest.mark.parametrize("payload,exception", [({}, MissingDependency), ({"observed": None}, InvalidDependency)])
def test_absent_and_null_response_bindings_remain_unavailable(position, payload, exception):
    scenario = load(request("source", []), request(assertions=[check(**{
        position: {"from_step": "source", "response_field": "observed"}})]))
    with pytest.raises(exception) as failure:
        prepare_step(scenario.steps[1], scenario, {"source": norm(**payload)})
    assert failure.value.sources == ["source"]


@pytest.mark.parametrize("position,value", [("id", 0), ("id", "record-22"), ("value", False), ("value", 0), ("value", "")])
def test_response_references_keep_usable_falsy_values(position, value):
    scenario = load(request("source", []), request(assertions=[check(**{
        position: {"from_step": "source", "response_field": "observed"}})]))
    prepared, bound = prepare_step(scenario.steps[1], scenario, {"source": norm(observed=value)})
    assert type(prepared.expect.backend_state[0].params[position]) is type(value)
    assert prepared.expect.backend_state[0].params[position] == value
    assert list(bound.values()) == [value]


@pytest.mark.parametrize("selector,payload", [({"key": "id"}, {"id": 22}),
    ({"matching": {"code": "selected"}, "member_field": "id"}, [{"id": 22, "code": "selected"}])])
def test_existing_member_references_are_available_for_state_id(selector, payload):
    scenario = load(request("source", []), request(assertions=[check(id={
        "from_step": "source", "response_field": "data", **selector})]))
    prepared, _ = prepare_step(scenario.steps[1], scenario, {"source": norm(data=payload)})
    assert prepared.expect.backend_state[0].params["id"] == 22


def child_document():
    child = document(request(assertions=[check(value={"from_parameter": "expected"})]),
                     parameters={"record_id": 22, "expected": "Example"})
    child["scenario"] = "shared.state"
    return child


def include(**overrides):
    return {"id": "included", "do": {"include": "shared.state"}, "with": overrides}


@pytest.mark.parametrize("key,value", [("record_id", False), ("record_id", ""), ("record_id", 1.0),
    ("record_id", None), ("expected", []), ("expected", {})])
@pytest.mark.parametrize("parameter", [False, True])
def test_known_invalid_include_override_is_rejected_during_load(tmp_path, key, value, parameter):
    override = {"from_parameter": "supplied"} if parameter else value
    path, _ = write_bundle(tmp_path, root=document(include(**{key: override}), parameters={"supplied": value}),
                           child=child_document())
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_include_substitution_matches_flattened_semantics_and_review_view(tmp_path):
    root = document(request("source", []), include(record_id={"from_step": "source", "response_field": "id"},
                    expected={"from_parameter": "name"}), parameters={"name": "Renamed"})
    path, _ = write_bundle(tmp_path, root=root, child=child_document())
    included = load_scenario(path)
    flat = load(request("source", []), request(assertions=[check(
        id={"from_step": "source", "response_field": "id"}, value="Renamed")]))
    evidence = {"source": norm(id=22)}
    actual, _ = prepare_step(included.steps[1], included, evidence)
    expected, _ = prepare_step(flat.steps[1], flat, evidence)
    assert actual.expect == expected.expect and actual.request == expected.request
    assert included.source_lookup["included/read"]["scenario_id"] == "shared.state"
    assert included.source_lookup["included/read"]["source_user"] == "reader"
    rendered = expansion_view(included)["steps"][1]["expect"]["backend_state"][0]
    assert rendered["id"] == {"kind": "reference", "from_step": "source", "response_field": "id"}


@pytest.mark.parametrize("key,value", [("record_id", False), ("expected", {})])
def test_invalid_runtime_include_override_retains_original_source(tmp_path, key, value):
    root = document(request("source", []), include(**{key: {"from_step": "source", "response_field": "observed"}}))
    path, _ = write_bundle(tmp_path, root=root, child=child_document())
    scenario = load_scenario(path)
    with pytest.raises(InvalidDependency) as failure:
        prepare_step(scenario.steps[1], scenario, {"source": norm(observed=value)})
    assert failure.value.sources == ["source"]


def test_named_child_result_is_valid_state_identity_with_attributed_binding(tmp_path):
    child = document(request("create", [{"check": "span_exists", "span": "created"}]))
    child["scenario"] = "shared.state"
    child["results"] = {"record_id": {"from_step": "create", "response_field": "id"}}
    root = document(include(), request(assertions=[check(id={"from_step": "included", "result": "record_id"})]))
    path, _ = write_bundle(tmp_path, root=root, child=child)
    scenario = load_scenario(path)
    binding = scenario.steps[1].bind[0]
    assert binding.from_step == "included/create" and binding.field == "id"
    assert isinstance(scenario.steps[1].expect.backend_state[0].params["id"], ValueRef)
    prepared, _ = prepare_step(scenario.steps[1], scenario, {"included/create": norm(id=22)})
    assert prepared.expect.backend_state[0].params["id"] == 22
    refs = [reference for location, value in _values(root["steps"][1], 1)
            for reference in _references(value, location)]
    assert refs == [("included", "record_id", "/steps/1/expect/backend_state/0/id")]


def test_object_observation_does_not_enable_nested_include_or_state_result_syntax(tmp_path):
    child = child_document()
    child["steps"].insert(0, {"id": "nested", "do": {"include": "shared.other"}})
    path, _ = write_bundle(tmp_path, root=document(include()), child=child)
    with pytest.raises(DeclarationError, match="must not include another"):
        load_scenario(path)
    raw = document()
    raw["results"] = {"stored_name": {"from_step": "read", "object": "record", "field": "name"}}
    with pytest.raises(DeclarationError):
        _load_document(raw)


def test_state_and_span_checks_can_share_a_step_without_changing_spans():
    scenario = load(request(assertions=[check(), {"check": "span_exists", "span": "read_record"},
        {"check": "span_attr", "span": "read_record", "attr": "allowed", "op": "==", "value": True}]))
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    assert [assertion.check for assertion in prepared.expect.backend_state] == [
        "object_field_equals", "span_exists", "span_attr"]
    assert prepared.expect.backend_state[2].params["value"] is True


def test_frontend_object_check_keeps_its_existing_shape_and_value_rules():
    raw = document({"id": "inspect", "do": "open", "target": "records", "expect": {"ui": [{
        "check": "object_field_equals", "anchor": "records", "id": {"from_parameter": "record_id"},
        "field": "name", "value": {"concat": ["Ex", "ample"]}}]}})
    scenario = _load_document(raw)
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    assert prepared.expect.frontend[0].params == {"anchor": "records", "id": 22, "field": "name", "value": "Example"}


def test_helpers_never_echo_rejected_sensitive_values():
    secret = {"sensitive-object-state-sentinel": "private"}
    for require in (object_state.require_id, object_state.require_expected):
        with pytest.raises(ValueError) as failure:
            require(secret)
        assert "sensitive-object-state-sentinel" not in str(failure.value)
