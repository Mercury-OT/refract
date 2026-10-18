"""Selectors survive one-level expansion without exposing child internals."""
import copy

import pytest

from refracto import ports
from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import _references, _wiring
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.projection import contract
from tests.fakes import FakeNormalizer
from tests.test_response_field_comparison import document, request, execute
from tests.test_response_member_references import selected, SENTINEL
from tests.test_scenario_include import write_bundle


def child_document():
    consume = request("consume")
    consume["do"]["request"]["body"] = {"selected": selected("list", source="list", matching={
        "code": {"from_parameter": "code"}, "region": {"from_step": "seed", "response_field": "region"}})}
    child = document(request("seed"), request("list"), consume, parameters={"code": "default", "unused": None})
    child["scenario"] = "shared.select"
    return child


def call(sid, code, **extra):
    return {"id": sid, "do": {"include": "shared.select"}, "with": {"code": code}, **extra}


def test_internal_predicates_and_two_invocations_resolve_independently(tmp_path):
    root = document(call("first", "A"), call("second", "B"))
    path, _ = write_bundle(tmp_path, root, child_document())
    case = load_scenario(path)
    observations = {
        "first/seed": ports.NormalizedResponse(True, {"region": "north"}, 200, None),
        "second/seed": ports.NormalizedResponse(True, {"region": "south"}, 200, None),
        "first/list": ports.NormalizedResponse(True, {"record": [
            {"code": "A", "region": "north", "id": 11}, {"code": "A", "region": "south", "id": 90}]}, 200, None),
        "second/list": ports.NormalizedResponse(True, {"record": [
            {"code": "B", "region": "north", "id": 91}, {"code": "B", "region": "south", "id": 22}]}, 200, None),
    }
    first, second = case.steps[2], case.steps[5]
    assert prepare_step(first, case, observations)[0].request.body["selected"] == 11
    assert prepare_step(second, case, observations)[0].request.body["selected"] == 22
    assert not set(binding.placeholder for binding in first.bind) & set(binding.placeholder for binding in second.bind)
    view = expansion_view(case)
    reference = view["steps"][2]["do"]["request"]["body"]["entries"]["selected"]
    assert reference["from_step"] == "first/list"
    assert reference["matching"]["region"]["from_step"] == "first/seed"
    assert reference["member_field"] == "id"


@pytest.mark.parametrize("kind", ["key", "list"])
def test_selected_with_values_and_unused_overrides_remain_visible(tmp_path, kind):
    root_call = call("setup", selected(kind, key="code"))
    root_call["with"]["unused"] = selected(kind, key="id")
    root = document(request("source"), root_call)
    path, _ = write_bundle(tmp_path, root, child_document())
    case = load_scenario(path)
    member = {"code": "B", "id": 22}
    observations = {
        "source": ports.NormalizedResponse(True, {"record": member if kind == "key" else [member]}, 200, None),
        "setup/seed": ports.NormalizedResponse(True, {"region": "west"}, 200, None),
        "setup/list": ports.NormalizedResponse(True, {"record": [{"code": "B", "region": "west", "id": 42}]}, 200, None),
    }
    step, bound = prepare_step(case.steps[-1], case, observations)
    assert step.request.body["selected"] == 42
    assert 22 not in bound.values()
    view = expansion_view(case)
    code = view["parameters"]["@include:setup:0"]
    unused = view["parameters"]["@include:setup:1"]
    field_name = "key" if kind == "key" else "member_field"
    assert code[field_name] == "code" and unused[field_name] == "id"
    assert unused["from_step"] == "source"


def test_unused_with_selector_keeps_predicate_dependency_in_review(tmp_path):
    call_step = call("setup", "B")
    call_step["with"]["unused"] = selected("list", matching={"code": {
        "from_step": "source", "response_field": "code"}})
    path, _ = write_bundle(tmp_path, document(request("source"), call_step), child_document())
    case = load_scenario(path)
    view = expansion_view(case)
    unused = view["parameters"]["@include:setup:1"]
    assert unused["matching"]["code"] == {"kind": "reference", "from_step": "source", "response_field": "code"}
    assert all(binding.from_step != "source" for step in case.steps for binding in step.bind)


def test_selected_external_dependency_through_with_is_read_from_actual_contract(tmp_path):
    child = document(request("compare", [{"check": "field_equals", "field": "selected", "value": {"from_parameter": "expected"}}]),
                     parameters={"expected": 1})
    child["scenario"] = "shared.select"
    root = document(request("source"), {"id": "setup", "do": {"include": "shared.select"},
                                      "with": {"expected": selected("list")}})
    path, _ = write_bundle(tmp_path, root, child)
    case = load_scenario(path)
    result, _ = execute(case, {"source": {"record": [{"code": "B", "id": 22}]}, "compare": {"selected": 22}})
    assert result.passed
    assert contract.run(case, result.provider_recordings, FakeNormalizer()).passed
    bad = copy.deepcopy(result.provider_recordings)
    bad[0].json["data"]["record"].append({"code": "B", "id": 22})
    assert not contract.run(case, bad, FakeNormalizer()).passed


def test_named_result_can_supply_plain_selection_predicate(tmp_path):
    child = document(request("seed"))
    child["scenario"] = "shared.select"
    child["results"] = {"code": {"from_step": "seed", "response_field": "code"}}
    consumer = request("consume")
    consumer["do"]["request"]["body"] = {"selected": selected("list", matching={"code": {"from_step": "setup", "result": "code"}})}
    root = document({"id": "setup", "do": {"include": "shared.select"}}, request("source"), consumer)
    path, _ = write_bundle(tmp_path, root, child)
    case = load_scenario(path)
    result, _ = execute(case, {"seed": {"code": "B"}, "source": {"record": [{"code": "B", "id": 22}]}})
    assert result.passed
    assert result.steps[-1].resolved_bindings
    assert contract.run(case, result.provider_recordings, FakeNormalizer()).passed


@pytest.mark.parametrize("kind", ["key", "list"])
def test_results_definitions_do_not_gain_selectors(kind):
    raw = document(request("source"))
    raw["results"] = {"id": selected(kind)}
    with pytest.raises(DeclarationError):
        _load_document(raw)


def test_with_known_nonscalar_matching_parameter_rejected(tmp_path):
    path, _ = write_bundle(tmp_path, document(call("setup", {"nested": 1})), child_document())
    with pytest.raises(DeclarationError, match="matching"):
        load_scenario(path)


def test_impact_view_preserves_selection_and_named_result_predicate_without_literal_disclosure():
    ref = selected("list", matching={"code": {"from_step": "setup", "result": "code"}, "secret": SENTINEL})
    assert list(_references(ref, "/value")) == [("setup", "code", "/value/matching/code")]
    wiring = _wiring(ref, False)
    assert wiring["kind"] == "step-reference" and wiring["member_field"] == "id"
    assert SENTINEL not in repr(wiring)
    assert SENTINEL in repr(_wiring(ref, True))
    assert _wiring(selected(), False)["key"] == "id"


@pytest.mark.parametrize("kind", ["key", "list"])
@pytest.mark.parametrize("bad", [False, "", [], {}, 1.5])
def test_contract_validates_selected_with_parameter_at_child_path_use_site(tmp_path, kind, bad):
    read = request("read")
    read["do"]["request"]["path"].append({"from_parameter": "id"})
    child = document(read, parameters={"id": 1})
    child["scenario"] = "shared.select"
    root = document(request("source"), {"id": "setup", "do": {"include": "shared.select"},
                                      "with": {"id": selected(kind)}})
    path, _ = write_bundle(tmp_path, root, child)
    case = load_scenario(path)
    member = {"code": "B", "id": 22}
    result, _ = execute(case, {"source": {"record": member if kind == "key" else [member]}})
    assert result.passed and contract.run(case, result.provider_recordings, FakeNormalizer()).passed
    changed = copy.deepcopy(result.provider_recordings)
    value = changed[0].json["data"]["record"]
    (value if kind == "key" else value[0])["id"] = bad
    checked = contract.run(case, changed, FakeNormalizer())
    assert not checked.passed and checked.steps[0].status == "ERROR"
