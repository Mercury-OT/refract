"""Exact-ID absence uses the existing bounded declaration and binding rules."""
import copy

import pytest

from refracto.declaration import object_state, vocabulary
from refracto.declaration.binding import InvalidDependency, MissingDependency, prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from tests.test_object_state_declaration import document, norm, request
from tests.test_scenario_include import write_bundle


def absent(**overrides):
    return {"check": "object_absent", "object": "record",
            "id": {"from_parameter": "record_id"}, **overrides}


def load(assertion=None, *, parameters=None):
    return _load_document(document(request(assertions=[absent() if assertion is None else assertion]),
                                   parameters=parameters))


def test_absence_vocabulary_is_only_backend_state_with_exact_selector_keys():
    assert object_state.ABSENT_CHECK == "object_absent"
    assert vocabulary.required_params("backend_state", "object_absent") == ("object", "id")
    assert vocabulary.optional_params("backend_state", "object_absent") == ()
    for section in ("frontend", "request", "response"):
        assert not vocabulary.is_valid(section, "object_absent")


@pytest.mark.parametrize("section", ["ui", "response"])
def test_wrong_assertion_section_is_rejected(section):
    step = request(assertions=[])
    step["expect"][section] = [absent()]
    with pytest.raises(DeclarationError):
        _load_document(document(step))


@pytest.mark.parametrize("key", ["object", "id"])
def test_absence_requires_both_selector_fields(key):
    assertion = absent()
    del assertion[key]
    with pytest.raises(DeclarationError, match="missing required"):
        load(assertion)


@pytest.mark.parametrize("key,value", [
    ("object", ""), ("object", " "), ("object", 1), ("object", None),
    ("object", []), ("object", {"from_parameter": "record_id"}),
    ("field", "name"), ("value", None), ("table", "records"), ("sql", "SELECT 1"),
    ("anchor", "records"), ("default", True), ("matching", {"code": "example"}),
])
def test_absence_has_literal_business_name_and_no_extra_options(key, value):
    with pytest.raises(DeclarationError):
        load(absent(**{key: value}))


@pytest.mark.parametrize("identity", [22, "22", None, True, False, [], {}, {"concat": ["r", "22"]}])
def test_literal_or_direct_concat_id_is_rejected(identity):
    with pytest.raises(DeclarationError):
        load(absent(id=identity))


@pytest.mark.parametrize("identity", [None, True, False, "", 1.0, [], {}, [22]])
def test_known_invalid_id_is_rejected(identity):
    with pytest.raises(DeclarationError):
        load(parameters={"record_id": identity})


@pytest.mark.parametrize("identity", [0, -1, 22, "22", "record-22"])
def test_parameter_identity_is_exact_and_not_coerced(identity):
    scenario = load(parameters={"record_id": identity})
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    actual = prepared.expect.backend_state[0].params["id"]
    assert type(actual) is type(identity) and actual == identity


@pytest.mark.parametrize("reference", [
    {"from_parameter": "unknown"}, {"from_step": "read", "response_field": "id"},
    {"from_step": "later", "response_field": "id"}, {"from_step": "source"},
    {"from_step": "source", "result": "unknown"},
    {"from_step": "source", "response_field": "id", "default": 22},
])
def test_unavailable_self_future_and_extended_references_fail_loading(reference):
    with pytest.raises(DeclarationError):
        _load_document(document(request("source", []), request(assertions=[absent(id=reference)]),
                                request("later", [])))


@pytest.mark.parametrize("payload,error", [
    ({}, MissingDependency), ({"id": None}, InvalidDependency),
    ({"id": True}, InvalidDependency), ({"id": False}, InvalidDependency),
    ({"id": ""}, InvalidDependency), ({"id": 1.0}, InvalidDependency),
    ({"id": []}, InvalidDependency), ({"id": {}}, InvalidDependency),
])
def test_runtime_invalid_ids_retain_dependency_and_do_not_mutate_declaration(payload, error):
    scenario = _load_document(document(request("source", []), request(assertions=[
        absent(id={"from_step": "source", "response_field": "id"})])))
    before = copy.deepcopy(scenario.steps[1])
    with pytest.raises(error) as failure:
        prepare_step(scenario.steps[1], scenario, {"source": norm(**payload)})
    assert failure.value.sources == ["source"]
    assert scenario.steps[1] == before


@pytest.mark.parametrize("selector,payload", [
    ({}, 22), ({"key": "id"}, {"id": 22}),
    ({"matching": {"code": "selected"}, "member_field": "id"}, [{"id": 22, "code": "selected"}]),
])
def test_existing_earlier_response_reference_forms_resolve(selector, payload):
    scenario = _load_document(document(request("source", []), request(assertions=[
        absent(id={"from_step": "source", "response_field": "data", **selector})])))
    prepared, _ = prepare_step(scenario.steps[1], scenario, {"source": norm(data=payload)})
    assert prepared.expect.backend_state[0].params["id"] == 22


def child_document():
    child = document(request(assertions=[absent()]))
    child["scenario"] = "shared.absence"
    return child


@pytest.mark.parametrize("value", [None, True, False, "", 1.0, [], {}])
@pytest.mark.parametrize("parameter", [False, True])
def test_include_override_cannot_bypass_id_validation(tmp_path, value, parameter):
    override = {"from_parameter": "supplied"} if parameter else value
    root = document({"id": "included", "do": {"include": "shared.absence"},
                     "with": {"record_id": override}}, parameters={"supplied": value})
    path, _ = write_bundle(tmp_path, root, child_document())
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_named_include_result_resolves_and_retains_expanded_review_identity(tmp_path):
    child = document(request("create", []))
    child["steps"][0]["expect"] = {"response": [{"check": "success"}]}
    child["scenario"] = "shared.create"
    child["results"] = {"record_id": {"from_step": "create", "response_field": "id"}}
    root = document({"id": "setup", "do": {"include": "shared.create"}}, request(assertions=[
        absent(id={"from_step": "setup", "result": "record_id"})]))
    path, _ = write_bundle(tmp_path, root, child)
    scenario = load_scenario(path)
    prepared, _ = prepare_step(scenario.steps[1], scenario, {"setup/create": norm(id=22)})
    assert prepared.expect.backend_state[0].params == {"object": "record", "id": 22}
    assert scenario.steps[1].bind[0].from_step == "setup/create"
    rendered = expansion_view(scenario)["steps"][1]["expect"]["backend_state"][0]
    assert rendered["check"] == "object_absent"
    assert rendered["id"]["from_step"] == "setup/create"


def test_storage_observation_cannot_be_exported_as_a_named_result():
    raw = document(request(assertions=[absent()]))
    raw["results"] = {"absence": {"from_step": "read", "object": "record", "check": "object_absent"}}
    with pytest.raises(DeclarationError):
        _load_document(raw)
