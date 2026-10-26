"""Authored marker-like data needs an explicit whole-parameter literal boundary."""
import copy
import json

import pytest

from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.run_values import bind_run_values
from tests.test_response_field_comparison import check, document, execute, request
from tests.test_scenario_include import include, leaf, parent, write_bundle


@pytest.mark.parametrize("marker", ["from_parameter", "from_run", "from_step", "from_unknown", "concat"])
@pytest.mark.parametrize("container", ["mapping", "array", "nested-literal"])
def test_reserved_data_keys_require_whole_parameter_literal(marker, container):
    value = {marker: "sensitive-marker-value"}
    if container == "mapping":
        value = {"nested": value}
    elif container == "array":
        value = [{"nested": value}]
    else:
        value = {"nested": {"literal": value}}
    with pytest.raises(DeclarationError, match="literal") as error:
        _load_document(document(parameters={"unused": value}))
    assert "sensitive-marker-value" not in str(error.value)


@pytest.mark.parametrize("value", [
    {"from_parameter": "token"}, {"from_unknown": "token"},
    {"literal": 0, "other": 1}, {"literal": {}, "concat": []},
    {"literal": {}, "from_run": "unique"},
])
def test_ambiguous_whole_parameter_forms_are_rejected(value):
    with pytest.raises(DeclarationError):
        _load_document(document(parameters={"token": "text", "unused": value}))


@pytest.mark.parametrize("payload", [
    None, False, 0, "", "from_run", [], {}, [None, False, 0, ""],
    {"from_parameter": "missing"},
    {"meta": {"from_run": "unique"}, "parts": [{"concat": ["a", "b"]}]},
    {"literal": {"from_run": "time", "offset": {"days": "data"}}},
])
def test_literal_data_round_trips_without_generation_or_mutation(payload, monkeypatch):
    from refracto.declaration import run_values
    monkeypatch.setattr(run_values, "uuid4", lambda: pytest.fail("literal generated a token"))
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("literal sampled a clock"))
    raw = document(request(checks=[check({"from_parameter": "expected"})]),
                   parameters={"expected": {"literal": payload}})
    before = copy.deepcopy(raw)
    scenario = _load_document(raw)
    assert type(scenario.parameters["expected"]) is type(payload)
    assert scenario.parameters["expected"] == payload
    view = expansion_view(scenario)
    assert json.loads(json.dumps(view)) == view
    bound, _ = bind_run_values(scenario)
    prepared, _ = prepare_step(bound.steps[0], bound, {})
    assert type(prepared.expect.response[0].params["value"]) is type(payload)
    assert prepared.expect.response[0].params["value"] == payload
    result, _ = execute(bound, {"read": {"content": payload}})
    assert result.status == "PASSED"
    assert raw == before and bound.run_time is None
    if isinstance(payload, (dict, list)):
        assert scenario.parameters["expected"] is not payload


@pytest.mark.parametrize("payload", [float("nan"), float("inf"), {1: "wrong"}, (), object()])
def test_literal_wrapper_does_not_bypass_finite_data_validation(payload):
    with pytest.raises(DeclarationError, match="finite JSON-like"):
        _load_document(document(parameters={"payload": {"literal": payload}}))


@pytest.mark.parametrize("payload", [".", "..", None, False, {}, []])
def test_literal_wrapper_does_not_make_invalid_path_values_usable(payload):
    step = request()
    step["do"]["request"]["path"] = ["records", {"from_parameter": "segment"}]
    with pytest.raises(DeclarationError):
        _load_document(document(step, parameters={"segment": {"literal": payload}}))


def test_literal_wrapper_has_no_special_meaning_in_action_data():
    payload = {"literal": {"label": "ordinary request data"}}
    step = request()
    step["do"]["request"]["body"] = {"payload": payload}
    scenario = _load_document(document(step))
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    assert prepared.request.body == {"payload": payload}


def test_reserved_parameter_names_and_string_contents_are_not_syntax():
    parameters = {"from_run": "from_parameter", "concat": "concat", "literal": "literal",
                  "ordinary": {"nested": {"literal": "text inside ordinary data", "fromage": "fine"}}}
    scenario = _load_document(document(parameters=parameters))
    assert scenario.parameters == parameters


def test_ordinary_nested_literal_key_is_data_when_no_reserved_content_exists():
    payload = {"nested": {"literal": {"label": "value"}}}
    scenario = _load_document(document(parameters={"payload": payload}))
    assert scenario.parameters["payload"] == payload


def test_wrapped_payload_survives_include_default_override_and_actual_send(tmp_path):
    payload = {"meta": {"from_run": "unique"}, "alias": {"from_parameter": "missing"},
               "steps": [{"concat": ["a", "b"]}]}
    child = leaf(parameters={"name": {"literal": payload}})
    root = parent([include("default"), include("override", **{
        "with": {"name": {"from_parameter": "payload"}}})],
        parameters={"payload": {"literal": payload}})
    path, _ = write_bundle(tmp_path, root, child)
    symbolic = load_scenario(path)
    expanded = expansion_view(symbolic)
    assert all(item["kind"] == "object" or item["kind"] == "reference"
               for item in expanded["parameters"].values())
    bound, _ = bind_run_values(symbolic)
    result, api = execute(bound, {"default/create": {}, "override/create": {}})
    assert result.status == "PASSED"
    assert [sent.body for sent in api.sent] == [{"name": payload}, {"name": payload}]


def test_response_marker_keys_are_observed_data_without_literal_wrapping():
    payload = {"from_run": "unique", "nested": {"concat": ["x", "y"]}}
    source = request("source", [{"check": "success"}])
    consumer = request("consumer", [check({"from_step": "source", "response_field": "content"})])
    consumer["do"]["request"]["body"] = {"value": {"from_step": "source", "response_field": "content"}}
    scenario = _load_document(document(source, consumer))
    result, api = execute(scenario, {"source": {"content": payload}, "consumer": {"content": payload}})
    assert result.status == "PASSED"
    assert api.sent[1].body == {"value": payload}


def test_impact_describes_unwrapped_literal_default_without_exposing_it_by_default(tmp_path):
    from tests.test_scenario_impact import bundle, child, inspect
    payload = {"from_run": "private-value-sentinel", "nested": {"concat": ["a", "b"]}}
    paths = bundle(tmp_path, old=child(parameters={"name": {"literal": payload}}))
    private = inspect(paths, show_values=False)
    assert private["status"] == "COMPLETE"
    assert "private-value-sentinel" not in json.dumps(private)
    visible = inspect(paths, show_values=True)
    default = visible["parents"][0]["includes"][0]["defaults"]["before"]["name"]
    assert default == {"type": "object", "value": payload}
