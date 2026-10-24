"""String composition retains response provenance and atomic preparation."""
import pytest

from refracto import ports
from refracto.declaration.binding import DependencyUnavailable, prepare_step
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from tests.test_run_values_declaration import declaration
from tests.test_scenario_include import include, leaf, parent, write_bundle


def observed(**fields):
    return ports.NormalizedResponse(True, fields, 200, None)


def response_case(expression, position="body"):
    raw = declaration({"name": "declared"})
    source = raw["steps"][0]
    source["id"] = "source"
    consumer = declaration(value=expression)["steps"][0]
    consumer["id"] = "consume"
    request = consumer["do"]["request"]
    if position == "path":
        request["path"].append(expression)
    elif position in ("query", "headers"):
        request[position] = {"x": expression}
    elif position == "assertion":
        consumer["expect"]["response"].append({"check": "field_equals", "field": "name", "value": expression})
    raw["steps"].append(consumer)
    return _load_document(raw)


def reference(**extra):
    return {"from_step": "source", "response_field": "code", **extra}


@pytest.mark.parametrize("position", ["body", "path", "query", "headers", "assertion"])
def test_response_concat_uses_current_observation_in_existing_value_positions(position):
    scenario = response_case({"concat": ["prefix-", reference(), "-", reference()]}, position)
    step, bound = prepare_step(scenario.steps[1], scenario, {"source": observed(code="value")})
    assert step.request.body["name"] == "prefix-value-value"
    assert list(bound.values()) == ["value"]


@pytest.mark.parametrize("value", [None, 0, False, 1.5, [], {}, {"concat": ["invented"]}])
def test_nonstring_response_operands_block_without_value_leaks(value):
    scenario = response_case({"concat": ["sensitive-sentinel", reference()]})
    with pytest.raises(DependencyUnavailable) as error:
        prepare_step(scenario.steps[1], scenario, {"source": observed(code=value)})
    assert error.value.sources == ["source"]
    assert "sensitive-sentinel" not in str(error.value)


def test_selected_response_string_and_empty_result_are_supported():
    scenario = response_case({"concat": [reference(key="label"), ""]})
    step, _ = prepare_step(scenario.steps[1], scenario, {"source": observed(code={"label": ""})})
    assert step.request.body == {"name": ""}


@pytest.mark.parametrize("expression", [{"from_run": "unique"}, {"concat": ["x", {"concat": ["y"]}]},
    {"concat": [reference(), 4]}, {"concat": [{"from_step": "consume", "response_field": "x"}]}])
def test_invalid_step_expressions_fail_loading(expression):
    with pytest.raises(DeclarationError):
        response_case(expression)


def test_include_response_override_is_a_dependency_of_derived_parameter(tmp_path):
    from refracto.declaration.run_values import bind_run_values
    source = declaration(value="seed")["steps"][0]
    source["id"] = "source"
    child = leaf(parameters={"name": {"concat": ["child-", {"from_parameter": "part"}]}, "part": "default"})
    root = parent([source, include(**{"with": {"part": reference()}})])
    path, _ = write_bundle(tmp_path, root, child)
    scenario, token = bind_run_values(load_scenario(path))
    assert token is None
    consume = scenario.steps[1]
    assert [binding.from_step for binding in consume.bind] == ["source"]
    step, bound = prepare_step(consume, scenario, {"source": observed(code="actual")})
    assert step.request.body == {"name": "child-actual"}
    assert list(bound.values()) == ["actual"]
    with pytest.raises(DependencyUnavailable):
        prepare_step(consume, scenario, {"source": observed(code=42)})


def test_unique_member_operand_and_concat_predicate_use_actual_sources():
    selected = {"from_step": "source", "response_field": "rows",
                "matching": {"code": {"concat": ["prefix-", {"from_parameter": "name"}]}},
                "member_field": "label"}
    scenario = response_case({"concat": ["selected-", selected]})
    step, _ = prepare_step(scenario.steps[1], scenario, {"source": observed(rows=[
        {"code": "other", "label": "wrong"}, {"code": "prefix-declared", "label": "right"}])})
    assert step.request.body == {"name": "selected-right"}


def test_selector_concat_predicate_retains_its_response_dependencies():
    selected = {"from_step": "source", "response_field": "rows",
                "matching": {"code": {"concat": ["prefix-", reference()]}}, "member_field": "label"}
    scenario = response_case({"concat": [selected]})
    step, _ = prepare_step(scenario.steps[1], scenario, {"source": observed(
        code="right", rows=[{"code": "prefix-right", "label": "chosen"}])})
    assert step.request.body == {"name": "chosen"}
    with pytest.raises(DependencyUnavailable):
        prepare_step(scenario.steps[1], scenario, {"source": observed(code=42, rows=[])})


def test_named_result_operand_preserves_child_result_interface(tmp_path):
    child = leaf()
    child["results"] = {"label": {"from_step": "create", "response_field": "label"}}
    consume = declaration(value={"concat": ["child-", {"from_step": "setup", "result": "label"}]})["steps"][0]
    consume["id"] = "consume"
    path, _ = write_bundle(tmp_path, parent([include(), consume]), child)
    scenario = load_scenario(path)
    step, _ = prepare_step(scenario.steps[1], scenario, {"setup/create": observed(label="actual")})
    assert step.request.body == {"name": "child-actual"}


def test_include_transitive_defaults_collect_all_response_sources(tmp_path):
    from refracto.declaration.run_values import bind_run_values
    sources = []
    for sid in ("first", "second"):
        step = declaration(value="seed")["steps"][0]
        step["id"] = sid
        sources.append(step)
    child = leaf(parameters={
        "name": {"concat": [{"from_parameter": "combined"}, "-child"]},
        "combined": {"concat": [{"from_parameter": "left"}, "-", {"from_parameter": "right"}]},
        "left": "L", "right": "R"})
    overrides = {name: {"from_step": sid, "response_field": "code"}
                 for name, sid in (("left", "first"), ("right", "second"))}
    path, _ = write_bundle(tmp_path, parent([*sources, include(**{"with": overrides})]), child)
    scenario, _ = bind_run_values(load_scenario(path))
    consume = scenario.steps[-1]
    assert [binding.from_step for binding in consume.bind] == ["first", "second"]
    prior = {"first": observed(code="one"), "second": observed(code="two")}
    assert prepare_step(consume, scenario, prior)[0].request.body == {"name": "one-two-child"}
    prior["second"] = observed(code=42)
    with pytest.raises(DependencyUnavailable) as error:
        prepare_step(consume, scenario, prior)
    assert error.value.sources == ["second"]


@pytest.mark.parametrize("slot", ["field_compare", "collection_length", "status_equals", "identity", "body"])
def test_concat_does_not_broaden_nonstring_slots(slot):
    raw = declaration({"name": "text"})
    expression = {"concat": ["1"]}
    step = raw["steps"][0]
    if slot == "body":
        step["do"]["request"]["body"] = expression
    elif slot == "identity":
        step["do"] = "click"
        step["target"] = "control"
        step["expect"] = {"ui": [{"check": "object_field_equals", "anchor": "rows", "id": expression,
                                  "field": "name", "value": "name"}]}
    else:
        assertion = {"check": slot, "value": expression}
        if slot != "status_equals":
            assertion.update(field="field", op="==")
        step["expect"]["response"].append(assertion)
    with pytest.raises(DeclarationError):
        _load_document(raw)


@pytest.mark.parametrize("position,value", [("path", ""), ("path", "."), ("path", ".."), ("headers", " bad")])
def test_composed_strings_keep_destination_validation(position, value):
    with pytest.raises(DeclarationError):
        response_case({"concat": [value]}, position)


def test_response_marker_looking_objects_remain_data_outside_concat():
    scenario = response_case(reference())
    literal = {"concat": ["not", "executed"], "from_run": "unique"}
    step, _ = prepare_step(scenario.steps[1], scenario, {"source": observed(code=literal)})
    assert step.request.body == {"name": literal}


def test_flat_and_include_path_templates_keep_segment_identity_without_values(tmp_path):
    child = leaf(parameters={"name": "selected"})
    expression = {"concat": ["sensitive-path-prefix-", {"from_parameter": "name"}]}
    child["steps"][0]["do"]["request"]["path"] = ["records", expression]
    flat = _load_document(child)
    path, _ = write_bundle(tmp_path, parent(), child)
    expanded = load_scenario(path)
    assert flat.steps[0].request.declared_path == expanded.steps[0].request.declared_path == "records/{concat:1}"
    assert "sensitive-path-prefix" not in flat.steps[0].request.declared_path
    actual_flat = prepare_step(flat.steps[0], flat, {})[0].request.path
    actual_include = prepare_step(expanded.steps[0], expanded, {})[0].request.path
    assert actual_flat == actual_include == "records/sensitive-path-prefix-selected"
