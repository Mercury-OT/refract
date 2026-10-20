"""Authoring ambiguity must not silently weaken a declared check."""
import hashlib
import json

import pytest
import yaml

from refracto.cli import main
from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import DeclarationError, _decode_document, _load_document, load_scenario
from tests.test_response_field_comparison import check, document, execute, request
from tests.test_scenario_include import include, leaf, parent, write_bundle


@pytest.mark.parametrize("name", ["from_paramter", "from_steps", "from_unknown"])
@pytest.mark.parametrize("position", ["expected", "body", "nested", "action"])
def test_unknown_reference_keys_rejected_in_expression_positions(name, position):
    value = {name: "private-value-sentinel"}
    step = request("read", [check(value, unequal=True)])
    if position == "body":
        step["do"]["request"]["body"] = {"value": value}
        step["expect"]["response"] = [{"check": "success"}]
    elif position == "nested":
        step["expect"]["response"][0]["value"] = {"nested": [value]}
    elif position == "action":
        step = {"id": "fill", "do": "fill", "target": "name", "value": value,
                "expect": {"ui": [{"check": "visible", "anchor": "name"}]}}
    with pytest.raises(DeclarationError, match="unknown reference") as error:
        _load_document(document(step))
    assert "private-value-sentinel" not in str(error.value)


def test_include_override_rejects_unknown_reference_key(tmp_path):
    path, _ = write_bundle(tmp_path, parent([include(**{
        "with": {"name": {"from_paramter": "private-value-sentinel"}}})]))
    with pytest.raises(DeclarationError, match="unknown reference") as error:
        load_scenario(path)
    assert "private-value-sentinel" not in str(error.value)


@pytest.mark.parametrize("value", [
    {"from_paramter": "not-syntax"},
    {"from_domain": {"from_step": "not-syntax", "response_field": "id"}},
    {"nested": [{"from_unknown": "literal"}]},
])
def test_literal_parameters_and_response_evidence_remain_data(value):
    source = request("source", [check({"from_parameter": "expected"})])
    consumer = request("consumer", [check({"from_step": "source", "response_field": "content"})])
    scenario = _load_document(document(source, consumer, parameters={"expected": value}))
    result, _ = execute(scenario, {"source": {"content": value}, "consumer": {"content": value}})
    assert [step.status for step in result.steps] == ["PASSED", "PASSED"]


def test_include_literal_parameter_is_not_reparsed(tmp_path):
    value = {"from_paramter": "literal"}
    path, _ = write_bundle(tmp_path, parent([include(**{
        "with": {"name": {"from_parameter": "payload"}}})], parameters={"payload": value}))
    scenario = load_scenario(path)
    assert prepare_step(scenario.steps[0], scenario, {})[0].request.body == {"name": value}


def yaml_document(token):
    return (
        "schema_version: 1\nscenario: authoring.example\nusers: []\n"
        f"parameters:\n  expected: {token}\n"
        "steps:\n- id: read\n  do: {request: {method: GET, path: [records]}}\n"
        "  expect:\n    response:\n"
        "    - {check: field_equals, field: value, value: {from_parameter: expected}}\n"
    )


@pytest.mark.parametrize("token", [
    "yes", "Yes", "YES", "no", "No", "NO", "on", "On", "ON", "off", "Off", "OFF",
    "12:30", "1:02:03", "-12:30", "+12:30", "12:30.5",
    "017", "-017", "+017", "00", "0_17",
])
def test_ambiguous_implicit_yaml_scalars_rejected_with_safe_guidance(token):
    with pytest.raises(DeclarationError, match="quote.*decimal"):
        _load_document(_decode_document(yaml_document(token).encode()))


@pytest.mark.parametrize("token", ["NO", "yes", "12:30", "017", "00", "2026-10-20"])
@pytest.mark.parametrize("quote", ["'", '"'])
def test_quoted_scalar_spelling_stays_a_string(token, quote):
    scenario = _load_document(_decode_document(yaml_document(quote + token + quote).encode()))
    assert scenario.parameters["expected"] == token


@pytest.mark.parametrize("token,value", [
    ("true", True), ("false", False), ("True", True), ("False", False),
    ("null", None), ("~", None), ("0", 0), ("17", 17), ("-17", -17), ("+17", 17),
    ("1.5", 1.5), ("-0.5", -0.5), ("1.5e+2", 150.0),
])
def test_unambiguous_existing_scalar_values_preserved(token, value):
    scenario = _load_document(_decode_document(yaml_document(token).encode()))
    assert type(scenario.parameters["expected"]) is type(value)
    assert scenario.parameters["expected"] == value


def test_loader_guard_does_not_change_global_pyyaml_resolvers():
    with pytest.raises(DeclarationError):
        _decode_document(yaml_document("NO").encode())
    assert yaml.safe_load("value: NO") == {"value": False}


def test_cli_rejects_ambiguous_scalar_without_echoing_source(tmp_path, capsys):
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml_document("NO").replace("expected: NO", "expected: NO # private-source-sentinel"))
    assert main(["validate", str(path)]) == 2
    output = capsys.readouterr()
    assert "quote" in output.out + output.err
    assert "private-source-sentinel" not in output.out + output.err


def test_pinned_child_uses_same_yaml_scalar_guard(tmp_path):
    path, child = write_bundle(tmp_path)
    child.write_text(yaml.safe_dump(leaf()).replace("name: Default", "name: NO"))
    sidecar = json.loads(path.with_suffix(".includes.json").read_text())
    sidecar["scenarios"]["shared.create"]["sha256"] = hashlib.sha256(child.read_bytes()).hexdigest()
    path.with_suffix(".includes.json").write_text(json.dumps(sidecar))
    with pytest.raises(DeclarationError, match="quote"):
        load_scenario(path)
