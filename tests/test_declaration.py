"""Declaration contract after the intentional, new-only format cutover.

Former v1/v2/precondition/bind acceptance obligations now become explicit
rejection tests. Assertion validation, reference scope, typing, and polling
obligations are retained against schema_version: 1 rather than translated by
the test runner.
"""
import copy

import pytest
import yaml

from refracto.declaration.loader import load_scenario, DeclarationError
from refracto.declaration import model


def document():
    return {
        "schema_version": 1, "scenario": "test", "users": ["reader"],
        "parameters": {"name": "sample", "id": "42", "rows": 3},
        "steps": [{"id": "read", "do": {"request": {"method": "GET", "path": ["items"]}},
                   "expect": {"response": [{"check": "success"}]}}],
    }


def write_load(tmp_path, doc):
    p = tmp_path / "scenario.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return load_scenario(p)


def response_doc(assertions):
    doc = document()
    doc["steps"][0]["expect"]["response"] = assertions
    return doc


def ui_doc(assertions):
    doc = document()
    doc["steps"][0] = {"id": "show", "do": "open", "target": "items.page",
                        "expect": {"ui": assertions}}
    return doc


def state_doc(assertions):
    doc = document()
    doc["steps"][0]["expect"]["backend_state"] = assertions
    return doc


def reference_doc(check="field_equals"):
    doc = document()
    source = doc["steps"][0]
    source["id"] = "source"
    # Source response fields are not fabricated by adding a has assertion.
    source["expect"] = {}
    ref = {"from_step": "source", "response_field": "id"}
    target = {"id": "target", "do": {"request": {"method": "PUT",
        "path": ["items", copy.deepcopy(ref)], "body": {"id": copy.deepcopy(ref)}}},
        "expect": {"response": [{"check": check, "field": "id", "value": copy.deepcopy(ref)}]}}
    doc["steps"].append(target)
    return doc


def test_load_synthetic_scenario():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    assert s.id == "refracto.synthetic_probe"
    assert s.grid == model.Grid("smoke", "generic")
    assert s.users == ["actor1"]
    assert s.precondition == []
    assert s.parameters == {"payload": "testdata/synthetic_input.txt"}
    assert len(s.steps) == 1
    step = s.steps[0]
    assert step.id == "main" and step.action == "click"
    assert step.request.method == "POST" and step.request.path == "resource/action"
    assert any(a.check == "has" and a.params["field"] == "taskId" for a in step.expect.response)
    assert [(a.check, a.params["span"]) for a in step.expect.backend_state] == [
        ("span_exists", "POST /resource/action"), ("span_exists", "INSERT resource.job_queue")]


@pytest.mark.parametrize("key", ["precondition", "inputs", "intent", "version", "expect", "expct", "actor"])
def test_old_and_unknown_top_level_keys_rejected(tmp_path, key):
    doc = document()
    doc[key] = []
    with pytest.raises(DeclarationError, match="unknown"):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("value", [None, [], "scenario", 1])
def test_top_level_must_be_mapping(tmp_path, value):
    with pytest.raises(DeclarationError, match="mapping"):
        write_load(tmp_path, value)


@pytest.mark.parametrize("key", ["scenario"])
@pytest.mark.parametrize("value", [None, "", " ", 7, [], {}])
def test_required_metadata_nonempty_strings(tmp_path, key, value):
    doc = document()
    doc[key] = value
    with pytest.raises(DeclarationError, match="non-empty string"):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("value", [None, 0, 2, "1", True, "proposed"])
def test_only_concrete_format_version_is_accepted(tmp_path, value):
    doc = document()
    doc["schema_version"] = value
    with pytest.raises(DeclarationError, match="schema_version"):
        write_load(tmp_path, doc)


def test_missing_format_version_rejected(tmp_path):
    doc = document()
    del doc["schema_version"]
    with pytest.raises(DeclarationError, match="schema_version"):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("version", [None, 1, 2, 99])
def test_legacy_declarations_are_not_silently_upgraded(tmp_path, version):
    old = {"scenario": "old", "actor": "a", "expect": {"response": [{"check": "success"}]}}
    if version is not None:
        old["version"] = version
    with pytest.raises(DeclarationError):
        write_load(tmp_path, old)


@pytest.mark.parametrize("key,value", [
    ("grid", {"level": "s", "module": "m", "extra": 1}),
    ("grid", {"level": "s"}), ("description", []),
    ("parameters", []), ("parameters", {"x": float("inf")}),
    ("parameters", {"x": {"nested": float("nan")}}),
])
def test_metadata_and_data_are_strict(tmp_path, key, value):
    doc = document()
    doc[key] = value
    with pytest.raises(DeclarationError):
        write_load(tmp_path, doc)


def test_multiple_named_parameters_are_allowed(tmp_path):
    s = write_load(tmp_path, document())
    assert s.parameters == {"name": "sample", "id": "42", "rows": 3}
    assert s.grid is None


@pytest.mark.parametrize("point", ["frontend", "e2e", "contract", "resposne"])
def test_unknown_expect_block_rejected(tmp_path, point):
    doc = document()
    doc["steps"][0]["expect"][point] = []
    with pytest.raises(DeclarationError, match="unknown"):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("value", [{"check": "success"}, None, "success"])
def test_observation_point_must_be_list(tmp_path, value):
    with pytest.raises(DeclarationError, match="list"):
        write_load(tmp_path, response_doc(value))


@pytest.mark.parametrize("assertion", ["text", {}, {"check": []}, {"check": "span_exists", "span": "x"}])
def test_invalid_response_assertion_rejected(tmp_path, assertion):
    with pytest.raises(DeclarationError):
        write_load(tmp_path, response_doc([assertion]))


@pytest.mark.parametrize("assertion", [
    {"check": "has"}, {"check": "has", "field": "id", "extra": 1},
    {"check": "has", "field": ""}, {"check": "field_equals", "field": "id", "value": []},
    {"check": "field_equals", "field": "id", "value": {"unexpected": 1}},
    {"check": "field_equals", "field": "id"},
])
def test_response_assertion_shape_remains_bounded(tmp_path, assertion):
    with pytest.raises(DeclarationError):
        write_load(tmp_path, response_doc([assertion]))


@pytest.mark.parametrize("value", [None, 0, False, "", "ready", 2.5])
def test_field_equals_literals_preserve_types(tmp_path, value):
    s = write_load(tmp_path, response_doc([{"check": "field_equals", "field": "state", "value": value}]))
    found = s.steps[0].expect.response[0].params["value"]
    assert type(found) is type(value) and found == value


@pytest.mark.parametrize("assertions", [
    [{"check": "success"}, {"check": "failure"}],
    [{"check": "field_equals", "field": "id", "value": 1}, {"check": "field_equals", "field": "id", "value": 1}],
    [{"check": "field_absent", "field": "id"}, {"check": "has", "field": "id"}],
])
def test_conflicting_response_obligations_rejected(tmp_path, assertions):
    with pytest.raises(DeclarationError):
        write_load(tmp_path, response_doc(assertions))


def test_has_and_field_equals_same_field_remain_legal(tmp_path):
    s = write_load(tmp_path, response_doc([{"check": "has", "field": "id"},
        {"check": "field_equals", "field": "id", "value": {"from_parameter": "id"}}]))
    assert s.steps[0].expect.response[1].params["value"] == model.ValueRef("input", "id")


@pytest.mark.parametrize("key", ["bind", "request", "action", "type", "sequence", "step_extra"])
def test_unknown_or_removed_step_keys_rejected(tmp_path, key):
    doc = document()
    doc["steps"][0][key] = {}
    with pytest.raises(DeclarationError, match="unknown"):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("value", [None, "", 0, []])
def test_step_id_is_required_and_named(tmp_path, value):
    doc = document()
    doc["steps"][0]["id"] = value
    with pytest.raises(DeclarationError, match="step.id"):
        write_load(tmp_path, doc)


def test_duplicate_step_id_rejected(tmp_path):
    doc = document()
    doc["steps"].append(copy.deepcopy(doc["steps"][0]))
    with pytest.raises(DeclarationError, match="duplicated"):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("field,value", [("extra", 1), ("async", "taskId"), ("method", ""),
    ("path", "items/{id}"), ("path", []), ("body", [])])
def test_request_fields_are_explicit(tmp_path, field, value):
    doc = document()
    doc["steps"][0]["do"]["request"][field] = value
    with pytest.raises(DeclarationError):
        write_load(tmp_path, doc)


def test_method_normalization_and_path_segments(tmp_path):
    doc = document()
    doc["steps"][0]["do"]["request"] = {"method": "get", "path": ["items", "a/b"]}
    s = write_load(tmp_path, doc)
    assert s.steps[0].request.method == "GET"
    assert s.steps[0].request.path == "items/a%2Fb"


def test_request_assertion_in_ui_is_not_a_second_action(tmp_path):
    doc = ui_doc([{"check": "visible", "anchor": "row"}])
    doc["steps"][0]["expect"]["request"] = {"method": "GET", "path": ["items"]}
    s = write_load(tmp_path, doc)
    assert s.steps[0].action == "open" and s.steps[0].request_asserted


@pytest.mark.parametrize("source", ["target", "later", "unknown"])
def test_response_reference_requires_prior_step(tmp_path, source):
    doc = reference_doc()
    doc["steps"][1]["do"]["request"]["body"]["id"]["from_step"] = source
    with pytest.raises(DeclarationError, match="earlier request-bearing"):
        write_load(tmp_path, doc)


def test_prior_request_does_not_need_a_fabricated_source_assertion(tmp_path):
    s = write_load(tmp_path, reference_doc())
    assert s.steps[0].expect.response == []
    assert len(s.steps[1].bind) == 1
    b = s.steps[1].bind[0]
    assert (b.from_step, b.field) == ("source", "id")
    assert s.steps[1].expect.response[0].params["value"] == model.ValueRef("bind", b.placeholder)


@pytest.mark.parametrize("ref", [
    {"from_parameter": "missing"}, {"from_parameter": ""}, {"from_parameter": "name", "extra": 1},
    {"from_step": "source"}, {"from_step": "source", "response_field": ""},
    {"from_step": "source", "response_field": "id", "extra": 1},
    {"from_input": "name"}, {"from_bind": "id"},
])
def test_reference_shapes_are_closed(tmp_path, ref):
    doc = reference_doc()
    doc["steps"][1]["expect"]["response"][0]["value"] = ref
    with pytest.raises(DeclarationError):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("policy", ["FAIL", "SKIP"])
def test_get_poll_keeps_explicit_timeout_policy(tmp_path, policy):
    doc = document()
    doc["steps"][0]["poll"] = {"on_timeout": policy}
    assert write_load(tmp_path, doc).steps[0].poll == model.PollPolicy(policy)


@pytest.mark.parametrize("change", ["method", "no_response", "empty_response", "policy", "unknown"])
def test_poll_validation_keeps_stop_condition_and_safe_method(tmp_path, change):
    doc = document()
    step = doc["steps"][0]
    step["poll"] = {"on_timeout": "FAIL"}
    if change == "method": step["do"]["request"]["method"] = "POST"
    elif change == "no_response": del step["expect"]["response"]
    elif change == "empty_response": step["expect"]["response"] = []
    elif change == "policy": step["poll"]["on_timeout"] = "RETRY"
    else: step["poll"]["extra"] = 1
    with pytest.raises(DeclarationError, match="poll"):
        write_load(tmp_path, doc)


@pytest.mark.parametrize("value", ["many", True, None, []])
def test_count_gt_non_numeric_count_rejected(tmp_path, value):
    with pytest.raises(DeclarationError):
        write_load(tmp_path, ui_doc([{"check": "count_gt", "anchor": "row", "count": value}]))


@pytest.mark.parametrize("key,value", [("op", "!="), ("value", "three"), ("value", True)])
def test_span_attr_ordering_is_bounded(tmp_path, key, value):
    a = {"check": "span_attr", "span": "insert", "attr": "count", "op": ">", "value": 0}
    a[key] = value
    with pytest.raises(DeclarationError):
        write_load(tmp_path, state_doc([a]))


def test_span_attr_parameter_reference_equality_only(tmp_path):
    a = {"check": "span_attr", "span": "insert", "attr": "count", "op": "==", "value": {"from_parameter": "rows"}}
    s = write_load(tmp_path, state_doc([a]))
    assert s.steps[0].expect.backend_state[0].params["value"] == model.ValueRef("input", "rows")
    a["op"] = ">"
    with pytest.raises(DeclarationError, match="equality"):
        write_load(tmp_path, state_doc([a]))


def test_span_attr_prior_response_reference_is_not_an_unused_binding(tmp_path):
    doc = reference_doc()
    doc["steps"][1]["expect"] = {"backend_state": [{"check": "span_attr", "span": "updated",
        "attr": "id", "op": "==", "value": {"from_step": "source", "response_field": "id"}}]}
    s = write_load(tmp_path, doc)
    assert len(s.steps[1].bind) == 1


@pytest.mark.parametrize("key,value", [("anchor", ""), ("field", ""), ("anchor", 1),
    ("id", "42"), ("value", []), ("value", {"unexpected": 1})])
def test_object_identity_assertion_shape(tmp_path, key, value):
    a = {"check": "object_field_equals", "anchor": "row", "id": {"from_parameter": "id"},
         "field": "name", "value": {"from_parameter": "name"}}
    a[key] = value
    with pytest.raises(DeclarationError):
        write_load(tmp_path, ui_doc([a]))


def test_object_identity_and_no_anonymous_are_preserved(tmp_path):
    s = write_load(tmp_path, ui_doc([
        {"check": "object_field_equals", "anchor": "row", "id": {"from_parameter": "id"},
         "field": "name", "value": {"from_parameter": "name"}},
        {"check": "no_anonymous", "anchor": "row"},
    ]))
    assert s.steps[0].expect.frontend[0].params["id"] == model.ValueRef("input", "id")
    assert s.steps[0].expect.frontend[1].check == "no_anonymous"


def test_both_canonical_multistep_examples_load():
    for path in ("scenarios/demo_job_run.yaml", "tests/fixtures/synthetic_templated_scenario.yaml"):
        s = load_scenario(path)
        assert len(s.steps) >= 2
        assert any(step.bind for step in s.steps)
