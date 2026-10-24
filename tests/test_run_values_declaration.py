"""Symbolic run values and bounded parameter composition preserve literal data."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from tests.test_scenario_include import include, leaf, parent, write_bundle


def declaration(parameters=None, value=None):
    return {"schema_version": 1, "scenario": "example.run_values", "users": [],
            "parameters": parameters or {}, "steps": [{"id": "create", "do": {"request": {
                "method": "POST", "path": ["records"],
                "body": {"name": value if value is not None else {"from_parameter": "name"}}}},
                "expect": {"response": [{"check": "success"}]}}]}


def composed_parameters():
    # Forward declaration is intentional; mapping order is not dependency order.
    return {"name": {"concat": [{"from_parameter": "token"}, "-record-", {"from_parameter": "token"}]},
            "token": {"from_run": "unique"}}


def test_loading_and_review_are_symbolic_and_binding_is_once_per_fresh_copy(monkeypatch):
    from refracto.declaration import run_values
    generated = []

    def token():
        generated.append(len(generated))
        return type("Token", (), {"hex": f"token-{len(generated)}"})()

    monkeypatch.setattr(run_values, "uuid4", token)
    scenario = _load_document(declaration(composed_parameters()))
    before = copy.deepcopy(scenario)
    view = expansion_view(scenario)
    assert json.loads(json.dumps(view)) == view
    assert generated == []
    first, first_token = run_values.bind_run_values(scenario)
    second, second_token = run_values.bind_run_values(scenario)
    assert generated == [0, 1]
    assert (first_token, second_token) == ("token-1", "token-2")
    assert first.parameters["name"] == "token-1-record-token-1"
    assert second.parameters["name"] == "token-2-record-token-2"
    assert scenario == before and scenario is not first
    assert first.source_lookup == scenario.source_lookup
    assert first_token not in repr(first)


def test_plain_parameter_concat_needs_no_randomness(monkeypatch):
    from refracto.declaration import run_values
    monkeypatch.setattr(run_values, "uuid4", lambda: pytest.fail("unexpected generation"))
    scenario = _load_document(declaration({"name": {"concat": ["", {"from_parameter": "part"}]},
                                           "part": ""}))
    bound, token = run_values.bind_run_values(scenario)
    assert token is None and bound.parameters["name"] == ""
    assert prepare_step(bound.steps[0], bound, {})[0].request.body == {"name": ""}


@pytest.mark.parametrize("parameters", [
    {"name": {"from_run": "date"}}, {"name": {"from_run": "unique", "prefix": "x"}},
    {"name": {"from_run": "unique", "suffix": "x"}}, {"name": {"from_run": 1}},
    {"name": {"concat": []}}, {"name": {"concat": "x"}}, {"name": {"concat": [1]}},
    {"name": {"concat": [None]}}, {"name": {"concat": [True]}},
    {"name": {"concat": [{"concat": ["x"]}]}}, {"name": {"concat": ["x"], "extra": 1}},
    {"name": {"concat": [{"from_parameter": "missing"}]}},
    {"name": {"concat": [{"from_parameter": "name"}]}},
    {"name": {"concat": [{"from_parameter": "b"}]}, "b": {"concat": [{"from_parameter": "name"}]}},
    {"name": {"concat": [{"from_parameter": "b"}]}, "b": 4},
    {"name": {"concat": [{"from_parameter": "b"}]}, "b": {"from_parameter": "unused"}},
    {"name": {"concat": [{"from_step": "create", "response_field": "id"}]}},
])
def test_invalid_parameter_declarations_fail_loading(parameters):
    with pytest.raises(DeclarationError):
        _load_document(declaration(parameters))


def test_parameter_marker_looking_nested_data_and_plain_alias_stay_literal():
    from refracto.declaration.run_values import bind_run_values
    literal = {"nested": {"concat": [{"from_run": "unique"}]}, "from_parameter": "missing"}
    scenario = _load_document(declaration({"name": literal}))
    bound, token = bind_run_values(scenario)
    assert token is None
    assert prepare_step(bound.steps[0], bound, {})[0].request.body["name"] == literal


def test_unbound_run_marker_is_rejected_without_generating():
    from refracto.declaration.run_values import ensure_bound_run_values
    scenario = _load_document(declaration({"unused": {"from_run": "unique"}}, "plain"))
    with pytest.raises(ValueError, match="bound"):
        ensure_bound_run_values(scenario)


def test_concurrent_bindings_do_not_mutate_or_share_run_tokens():
    from refracto.declaration.run_values import bind_run_values
    scenario = _load_document(declaration(composed_parameters()))
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(lambda _: bind_run_values(scenario), range(12)))
    assert len({token for _, token in runs}) == 12
    for bound, token in runs:
        assert bound.parameters["name"] == f"{token}-record-{token}"


def test_include_overrides_affect_dependent_defaults_without_scope_capture(tmp_path):
    from refracto.declaration.run_values import bind_run_values
    child = leaf(parameters={"name": {"concat": [{"from_parameter": "part"}, "-child"]}, "part": "default"})
    root = parent([include("first", **{"with": {"part": {"from_parameter": "part"}}}),
                   include("second", **{"with": {"part": "second"}})],
                  parameters={"part": {"concat": ["parent-", {"from_parameter": "token"}]},
                              "token": {"from_run": "unique"}})
    path, _ = write_bundle(tmp_path, root, child)
    scenario = load_scenario(path)
    bound, token = bind_run_values(scenario)
    assert [prepare_step(step, bound, {})[0].request.body["name"] for step in bound.steps] == [
        f"parent-{token}-child", "second-child"]
    assert bound.include_dependencies == scenario.include_dependencies
    assert bound.source_lookup == scenario.source_lookup
    assert "from_run" in json.dumps(expansion_view(scenario))


def test_include_literal_override_is_never_reparsed(tmp_path):
    from refracto.declaration.run_values import bind_run_values
    literal = {"nested": {"concat": ["a", "b"]}, "from_run": "not-a-generator"}
    child = leaf(parameters={"name": {}})
    root = parent([include(**{"with": {"name": {"from_parameter": "payload"}}})],
                  parameters={"payload": {"wrapped": literal}})
    path, _ = write_bundle(tmp_path, root, child)
    bound, token = bind_run_values(load_scenario(path))
    assert token is None
    assert prepare_step(bound.steps[0], bound, {})[0].request.body == {"name": {"wrapped": literal}}


def test_include_known_nonstring_override_cannot_hide_in_derived_default(tmp_path):
    child = leaf(parameters={"name": {"concat": [{"from_parameter": "part"}]}, "part": "default"})
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"part": 42}})]), child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_include_distinct_unique_parameters_share_one_frozen_token(tmp_path, monkeypatch):
    from refracto.declaration import run_values
    calls = []
    monkeypatch.setattr(run_values, "uuid4", lambda: calls.append(1) or type("Token", (), {"hex": "one-token"})())
    child = leaf(parameters={"name": {"concat": ["child-", {"from_parameter": "token"}]},
                            "token": {"from_run": "unique"}})
    path, _ = write_bundle(tmp_path, parent([include("first"), include("second")]), child)
    bound, token = run_values.bind_run_values(load_scenario(path))
    assert calls == [1] and token == "one-token"
    assert [prepare_step(step, bound, {})[0].request.body for step in bound.steps] == [
        {"name": "child-one-token"}, {"name": "child-one-token"}]


def test_impact_and_expansion_distinguish_symbolic_concat_and_nested_literal_data(tmp_path, monkeypatch):
    from refracto.declaration import run_values
    from tests.test_scenario_impact import bundle, child, inspect
    monkeypatch.setattr(run_values, "uuid4", lambda: pytest.fail("review generated a token"))
    params = {"name": {"concat": ["prefix-", {"from_parameter": "token"}]},
              "token": {"from_run": "unique"}, "literal": {"nested": {"concat": ["a", "b"]}}}
    paths = bundle(tmp_path, old=child(parameters=params))
    report = inspect(paths, show_values=True)
    assert report["status"] == "COMPLETE"
    defaults = report["parents"][0]["includes"][0]["defaults"]["before"]
    assert defaults["name"]["kind"] == "concat"
    assert defaults["token"]["kind"] == "run-value"
    assert defaults["literal"]["value"] == params["literal"]
    view = expansion_view(load_scenario(paths[3]))
    assert json.loads(json.dumps(view)) == view
    assert any(value["kind"] == "run-value" for value in view["parameters"].values())
    literal = next(value for value in view["parameters"].values()
                   if value["kind"] == "object" and "nested" in value["entries"])
    assert literal["entries"]["nested"]["kind"] == "object"


def test_shared_symbolic_parameter_dag_is_analyzed_without_expanding_paths():
    parameters = {"p0": {"from_run": "unique"}}
    for index in range(1, 45):
        parameters[f"p{index}"] = {"concat": [{"from_parameter": f"p{index - 1}"},
                                                {"from_parameter": f"p{index - 1}"}]}
    # A non-memoized walk follows more than 2**44 paths even though no concrete
    # string is needed during loading. Do not bind this intentionally huge value.
    scenario = _load_document(declaration(parameters, {"from_parameter": "p44"}))
    assert len(scenario.inputs) == 45


def test_excessive_dependency_depth_is_a_declaration_error():
    parameters = {"p0": {"from_run": "unique"}}
    for index in range(1, 1500):
        parameters[f"p{index}"] = {"concat": [{"from_parameter": f"p{index - 1}"}]}
    # Forward order ensures validation must examine the entire dependency chain.
    parameters = dict(reversed(list(parameters.items())))
    with pytest.raises(DeclarationError):
        _load_document(declaration(parameters, {"from_parameter": "p1499"}))


def test_expansion_rejects_bound_models_without_revealing_runtime_token(monkeypatch):
    from refracto.declaration import run_values
    token = "private-runtime-token-sentinel"
    monkeypatch.setattr(run_values, "uuid4", lambda: type("Token", (), {"hex": token})())
    symbolic = _load_document(declaration(composed_parameters()))
    before = expansion_view(symbolic)
    bound, _ = run_values.bind_run_values(symbolic)
    with pytest.raises(ValueError) as error:
        expansion_view(bound)
    assert token not in str(error.value)
    assert token not in repr(bound)
    assert expansion_view(symbolic) == before


@pytest.mark.parametrize("container", ["dict", "list"])
@pytest.mark.parametrize("compose", [False, True])
def test_include_structured_arguments_bind_typed_nodes_and_preserve_literal_data(tmp_path, container, compose):
    from refracto.declaration.run_values import bind_run_values
    operand = {"from_parameter": "token"}
    expression = {"concat": ["prefix-", operand]} if compose else operand
    nested = {"label": expression} if container == "dict" else [expression]
    literal = {"nested": {"from_run": "unique"},
               "list": [{"concat": ["a", "b"]}, {"from_parameter": "missing"}]}
    override = {"value": nested, "literal": {"from_parameter": "payload"}}
    root = parent([include(**{"with": {"name": override}})],
                  parameters={"token": {"from_run": "unique"}, "payload": literal})
    path, _ = write_bundle(tmp_path, root, leaf(parameters={"name": {}}))
    original = load_scenario(path)
    bound, token = bind_run_values(original)
    expected = "prefix-" + token if compose else token
    expected_nested = {"label": expected} if container == "dict" else [expected]
    prepared, _ = prepare_step(bound.steps[0], bound, {})
    assert prepared.request.body == {"name": {"value": expected_nested, "literal": literal}}
    assert original.parameters["payload"] == literal


@pytest.mark.parametrize("container", ["dict", "list"])
def test_nested_typed_run_marker_requires_explicit_binding_even_without_root_marker(container):
    from refracto.declaration.model import Input, RunUnique, StringConcat
    from refracto.declaration.run_values import bind_run_values, ensure_bound_run_values
    scenario = _load_document(declaration({"name": {}}))
    expression = StringConcat(("prefix-", RunUnique()))
    payload = {"label": expression} if container == "dict" else [expression]
    scenario.inputs = [Input("name", payload)]
    with pytest.raises(ValueError, match="bound"):
        ensure_bound_run_values(scenario)
    bound, token = bind_run_values(scenario)
    assert token is not None
    expected = {"label": "prefix-" + token} if container == "dict" else ["prefix-" + token]
    assert prepare_step(bound.steps[0], bound, {})[0].request.body == {"name": expected}
