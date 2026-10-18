"""Numeric thresholds retain bounded references, inclusion and review views."""
import pytest

from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import _references, _values
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.projection import contract
from tests.fakes import FakeNormalizer
from tests.test_response_field_comparison import document, execute, load, request
from tests.test_response_numeric_length import TERMS, check
from tests.test_scenario_include import write_bundle


def child_document(term, value=1):
    child = document(request("child_read", [check(term, {"from_parameter": "threshold"})]),
                     parameters={"threshold": value}, users=["reader"])
    child["scenario"] = "shared.numeric"
    return child


@pytest.mark.parametrize("term,value", [
    *((term, value) for term in TERMS for value in [None, True, "1", [], {}]),
    ("collection_length", 1.0), ("collection_length", -1),
])
@pytest.mark.parametrize("from_parameter", [False, True])
def test_known_invalid_include_overrides_rejected_at_load(tmp_path, term, value, from_parameter):
    override = {"from_parameter": "supplied"} if from_parameter else value
    root = document({"id": "included", "do": {"include": "shared.numeric"},
                     "with": {"threshold": override}}, parameters={"supplied": value}, users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child_document(term))
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("term", TERMS)
def test_invalid_child_default_rejected_even_when_overridden(tmp_path, term):
    root = document({"id": "included", "do": {"include": "shared.numeric"},
                     "with": {"threshold": 2}}, users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child_document(term, True))
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("kind", ["literal", "parameter", "response"])
def test_include_threshold_substitution_and_repeated_instance_isolation(tmp_path, term, kind):
    value = {"literal": 2, "parameter": {"from_parameter": "supplied"},
             "response": {"from_step": "source", "response_field": "threshold"}}[kind]
    root = document(request("source", []),
        {"id": "first", "do": {"include": "shared.numeric"}, "with": {"threshold": value}},
        {"id": "second", "do": {"include": "shared.numeric"}, "with": {"threshold": 2}},
        parameters={"supplied": 2}, users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child_document(term))
    scenario = load_scenario(path)
    observed = 2 if term == "field_compare" else ["one", "two"]
    result, _ = execute(scenario, {"source": {"threshold": 2}, "child_read": {"measured": observed}})
    assert result.status == "PASSED"
    assert [step.step_id for step in result.steps] == ["source", "first/child_read", "second/child_read"]
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"
    assert scenario.steps[1].expect.response[0] is not scenario.steps[2].expect.response[0]


@pytest.mark.parametrize("term", TERMS)
def test_invalid_runtime_include_threshold_blocks_before_child_action(tmp_path, term):
    root = document(request("source", []),
        {"id": "included", "do": {"include": "shared.numeric"},
         "with": {"threshold": {"from_step": "source", "response_field": "threshold"}}},
        request("independent"), users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child_document(term))
    scenario = load_scenario(path)
    result, api = execute(scenario, {"source": {"threshold": "invalid"}})
    assert [step.status for step in result.steps] == ["COMPLETED", "BLOCKED", "PASSED"]
    assert result.steps[1].resolved_bindings == {}
    assert [item.path for item in api.sent] == ["source", "independent"]
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).steps[0].status == "ERROR"


@pytest.mark.parametrize("term", TERMS)
def test_named_result_threshold_is_actual_provider_evidence_and_reviewable(tmp_path, term):
    child = document(request("source", [{"check": "has", "field": "threshold"}]), users=["reader"])
    child["scenario"] = "shared.numeric"
    child["results"] = {"limit": {"from_step": "source", "response_field": "threshold"}}
    root = document({"id": "included", "do": {"include": "shared.numeric"}},
        request("read", [check(term, {"from_step": "included", "result": "limit"}, "<=")]), users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child)
    scenario = load_scenario(path)
    observed = 2 if term == "field_compare" else [None, None]
    result, _ = execute(scenario, {"source": {"threshold": 2}, "read": {"measured": observed}})
    assert result.status == "PASSED"
    assert scenario.steps[1].bind[0].from_step == "included/source"
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"
    rendered = expansion_view(scenario)["steps"][1]["expect"]["response"][0]
    assert rendered["check"] == term and rendered["op"] == {"kind": "literal", "value": "<="}
    assert rendered["value"]["from_step"] == "included/source"
    assert any(list(_references(value, location)) for location, value in _values(root["steps"][1], 1))


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("selector", [
    {"key": "limit"}, {"matching": {"name": "chosen"}, "member_field": "limit"},
])
def test_existing_member_thresholds_prepare_and_contract_replay(term, selector):
    reference = {"from_step": "source", "response_field": "settings", **selector}
    scenario = load(request("source", []), request("read", [check(term, reference)]))
    settings = {"limit": 2} if "key" in selector else [{"name": "other", "limit": 3}, {"name": "chosen", "limit": 2}]
    result, _ = execute(scenario, {"source": {"settings": settings},
        "read": {"measured": 2 if term == "field_compare" else [None, None]}})
    assert result.status == "PASSED"
    assert list(result.steps[1].resolved_bindings.values()) == [2]
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"


@pytest.mark.parametrize("term,value", [
    *((term, value) for term in TERMS for value in ["2", None, True, {}]),
    ("collection_length", -1.0),
])
def test_invalid_member_thresholds_block_or_contract_error(term, value):
    scenario = load(request("source", []), request("read", [check(term,
        {"from_step": "source", "response_field": "settings", "key": "limit"})]))
    result, api = execute(scenario, {"source": {"settings": {"limit": value}}})
    assert [step.status for step in result.steps] == ["COMPLETED", "BLOCKED"]
    assert len(api.sent) == 1 and result.steps[1].resolved_bindings == {}
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).steps[0].status == "ERROR"


@pytest.mark.parametrize("term", TERMS)
@pytest.mark.parametrize("reference", [
    {"from_step": "read", "response_field": "threshold"},
    {"from_step": "later", "response_field": "threshold"},
    {"from_step": "source"}, {"response_field": "threshold"},
    {"from_parameter": "missing"}, {"from_step": "source", "response_field": "threshold", "extra": 1},
    {"from_step": "source", "response_field": "threshold", "matching": {"x": 1}},
])
def test_malformed_forward_and_self_threshold_references_rejected(term, reference):
    with pytest.raises(DeclarationError):
        load(request("source", []), request("read", [check(term, reference)]), request("later"))


@pytest.mark.parametrize("term", TERMS)
def test_named_results_cannot_add_selectors_and_inclusion_depth_is_unchanged(tmp_path, term):
    child = document(request("source"), users=["reader"])
    child["scenario"] = "shared.numeric"
    child["results"] = {"limit": {"from_step": "source", "response_field": "threshold"}}
    root = document({"id": "included", "do": {"include": "shared.numeric"}},
        request("read", [check(term, {"from_step": "included", "result": "limit", "key": "value"})]),
        users=["owner"])
    path, _ = write_bundle(tmp_path, root=root, child=child)
    with pytest.raises(DeclarationError):
        load_scenario(path)
    child["steps"].append({"id": "nested", "do": {"include": "shared.other"}})
    root["steps"].pop()
    path, _ = write_bundle(tmp_path, root=root, child=child)
    with pytest.raises(DeclarationError):
        load_scenario(path)
