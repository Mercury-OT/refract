"""Named results are static, read-only aliases, not runtime return statements."""
import hashlib
import json

import pytest
import yaml

from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.ports import NormalizedResponse


def request(sid, *, path=None, body=None, checks=None):
    action = {"method": "POST", "path": ["items"] if path is None else path}
    if body is not None:
        action["body"] = body
    return {"id": sid, "do": {"request": action},
            "expect": {"response": [{"check": "success"}] if checks is None else checks}}


def child():
    return {"schema_version": 1, "scenario": "shared.create", "users": ["user"],
            "parameters": {"name": "Default"},
            "steps": [request("create", body={"name": {"from_parameter": "name"}})],
            "results": {"record_id": {"from_step": "create", "response_field": "id"},
                        "record_name": {"from_step": "create", "response_field": "name"}}}


def include(sid="setup", **kwargs):
    return {"id": sid, "do": {"include": "shared.create"}, **kwargs}


def named(name="record_id", source="setup"):
    return {"from_step": source, "result": name}


def bundle(tmp_path, *, child_raw=None, steps=None, parameters=None, root_extra=None):
    child_path = tmp_path / "child.yaml"
    child_path.write_text(yaml.safe_dump(child() if child_raw is None else child_raw, sort_keys=False))
    root = {"schema_version": 1, "scenario": "example.parent", "users": ["user"],
            "parameters": parameters or {},
            "steps": steps if steps is not None else [include(), request("read", path=["items", named()])]}
    root.update(root_extra or {})
    path = tmp_path / "parent.yaml"
    path.write_text(yaml.safe_dump(root, sort_keys=False))
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1, "scenarios": {
        "shared.create": {"path": "child.yaml", "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}))
    return path, child_path


def norms(**fields):
    return {"setup/create": NormalizedResponse(True, fields, 201, None)}


def test_multiple_results_compile_to_existing_bindings(tmp_path):
    path, child_path = bundle(tmp_path, steps=[include(), request("read", path=["items", named()],
        body={"name": named("record_name")})])
    scenario = load_scenario(path)
    source = load_scenario(child_path)
    assert set(source.results) == {"record_id", "record_name"}
    assert [step.id for step in scenario.steps] == ["setup/create", "read"]
    prepared, bound = prepare_step(scenario.steps[-1], scenario, norms(id=7, name="Actual"))
    assert prepared.request.path == "items/7"
    assert prepared.request.body == {"name": "Actual"}
    assert set(bound.values()) == {7, "Actual"}
    assert {binding.from_step for binding in scenario.steps[-1].bind} == {"setup/create"}


def test_authored_internal_child_reference_rejected(tmp_path):
    path, _ = bundle(tmp_path, steps=[include(), request("read", path=["items", {
        "from_step": "setup/create", "response_field": "id"}])])
    with pytest.raises(DeclarationError, match="earlier request-bearing"):
        load_scenario(path)


@pytest.mark.parametrize("results", [None, [], "id", {"": {"from_step": "create", "response_field": "id"}},
    {"out": {}}, {"out": {"from_step": "create", "response_field": "id", "value": 1}},
    {"out": {"from_step": "absent", "response_field": "id"}},
    {"out": {"from_step": "create", "result": "record_id"}}])
def test_invalid_result_declarations_rejected(tmp_path, results):
    raw = child()
    raw["results"] = results
    path, _ = bundle(tmp_path, child_raw=raw, steps=[include()])
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("results", [{}, "omitted"])
def test_no_public_results_still_executes_child_checks(tmp_path, results):
    raw = child()
    if results == "omitted":
        del raw["results"]
    else:
        raw["results"] = results
    path, child_path = bundle(tmp_path, child_raw=raw, steps=[include()])
    assert load_scenario(child_path).results == {}
    assert load_scenario(path).included_results == {"setup": {}}


@pytest.mark.parametrize("key,value", [("from_step", None), ("from_step", 1), ("from_step", []),
    ("from_step", " "), ("from_step", {"from_parameter": "name"}),
    ("response_field", None), ("response_field", 1), ("response_field", []),
    ("response_field", " "), ("response_field", {"from_parameter": "name"})])
def test_result_source_values_must_be_literal_nonblank_strings(tmp_path, key, value):
    raw = child()
    raw["results"]["record_id"][key] = value
    path, _ = bundle(tmp_path, child_raw=raw, steps=[include()])
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("name", [None, 1, False, " "])
def test_result_names_are_nonblank_strings_without_coercion(tmp_path, name):
    raw = child()
    raw["results"] = {name: {"from_step": "create", "response_field": "id"}}
    path, _ = bundle(tmp_path, child_raw=raw, steps=[include()])
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_duplicate_result_names_are_rejected_by_real_yaml_loader(tmp_path):
    path, child_path = bundle(tmp_path, steps=[include()])
    child_path.write_text(child_path.read_text() + "\n  record_id: {from_step: create, response_field: id}\n")
    sidecar = path.with_suffix(".includes.json")
    pins = json.loads(sidecar.read_text())
    pins["scenarios"]["shared.create"]["sha256"] = hashlib.sha256(child_path.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(pins))
    with pytest.raises(DeclarationError, match="duplicate"):
        load_scenario(path)


@pytest.mark.parametrize("source_step", [
    {"id": "quiet", "do": "wait", "duration": 0},
    {"id": "quiet", "do": "click", "target": "save"},
])
def test_requestless_steps_cannot_provide_results(tmp_path, source_step):
    raw = child()
    raw["steps"].append(source_step)
    raw["results"]["record_id"]["from_step"] = "quiet"
    path, _ = bundle(tmp_path, child_raw=raw)
    with pytest.raises(DeclarationError, match="local request-bearing"):
        load_scenario(path)


@pytest.mark.parametrize("source", ["setup", "setup/create"])
def test_parent_cannot_reexport_child_results_or_internal_leaves(tmp_path, source):
    path, _ = bundle(tmp_path, root_extra={"results": {
        "forwarded": {"from_step": source, "response_field": "id"}}})
    with pytest.raises(DeclarationError, match="local request-bearing"):
        load_scenario(path)


def test_results_from_different_local_request_steps_and_literal_names(tmp_path):
    raw = child()
    raw["steps"].append(request("read", path=["items", {"from_step": "create", "response_field": "id"}]))
    raw["results"]["latest/name"] = {"from_step": "read", "response_field": "name"}
    raw["results"]["same_id"] = dict(raw["results"]["record_id"])
    path, child_path = bundle(tmp_path, child_raw=raw, steps=[include(), request("after", body={
        "id": named(), "same": named("same_id"), "name": named("latest/name")})])
    scenario = load_scenario(path)
    assert load_scenario(child_path).results["latest/name"].from_step == "read"
    prepared, bound = prepare_step(scenario.steps[-1], scenario, {
        **norms(id=4), "setup/read": NormalizedResponse(True, {"name": "Newest"}, 200, None)})
    assert prepared.request.body == {"id": 4, "same": 4, "name": "Newest"}
    assert len(bound) == 2  # Two aliases of one actual field do not duplicate binds.


def test_request_bearing_ui_step_can_provide_results(tmp_path):
    raw = child()
    step = raw["steps"][0]
    template = step["do"]["request"]
    step["do"], step["target"] = "click", "save"
    step["expect"]["request"] = template
    path, _ = bundle(tmp_path, child_raw=raw)
    scenario = load_scenario(path)
    assert scenario.steps[0].request_asserted
    assert prepare_step(scenario.steps[-1], scenario, norms(id=8))[0].request.path == "items/8"


def test_results_do_not_count_as_assertions(tmp_path):
    raw = child()
    del raw["steps"][0]["expect"]
    path, _ = bundle(tmp_path, child_raw=raw)
    with pytest.raises(DeclarationError, match="assertion"):
        load_scenario(path)


@pytest.mark.parametrize("reference", [named("unknown"), named(None), named(" "), named(1),
    named([], "setup"), named(source="future"), named(source="read"),
    {"from_step": "setup"}, {"from_step": "setup", "result": "record_id", "response_field": "id"},
    {"from_step": "setup", "result": "record_id", "extra": True},
    {"from_step": "setup", "result": "record_id", "from_parameter": "name"}])
def test_invalid_result_references_are_errors_not_literal_fallback(tmp_path, reference):
    path, _ = bundle(tmp_path, steps=[include(), request("read", body={"value": reference}), include("future")])
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_named_reference_does_not_address_ordinary_local_request(tmp_path):
    path, _ = bundle(tmp_path, steps=[request("ordinary"), include(), request("read", body={
        "value": named(source="ordinary")})])
    with pytest.raises(DeclarationError, match="earlier include"):
        load_scenario(path)


@pytest.mark.parametrize("source", ["setup", "future"])
def test_with_cannot_read_current_or_future_include(tmp_path, source):
    path, _ = bundle(tmp_path, steps=[include(**{"with": {"name": named(source=source)}}), include("future")])
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("position", ["body", "with", "matching"])
def test_internal_child_access_is_rejected_in_every_recursive_position(tmp_path, position):
    hidden = {"from_step": "setup/create", "response_field": "id"}
    follow = request("read", body={"nested": [hidden]})
    if position == "with":
        follow = include("next", **{"with": {"name": hidden}})
    elif position == "matching":
        follow = request("read", checks=[{"check": "collection_matching_count", "field": "items",
            "matching": {"id": hidden}, "count": 1}])
    path, _ = bundle(tmp_path, steps=[include(), follow])
    with pytest.raises(DeclarationError, match="earlier request-bearing"):
        load_scenario(path)


@pytest.mark.parametrize("payload", [{"result": "ok"}, {"from_step": "absent", "result": "id"},
    {"response_field": "literal"}, [False, 0, ""]])
def test_reference_shaped_parameter_values_remain_literal_data(tmp_path, payload):
    path, _ = bundle(tmp_path, parameters={"payload": payload}, steps=[
        include(**{"with": {"name": {"from_parameter": "payload"}}}),
        request("read", body={"value": {"from_parameter": "payload"}})])
    scenario = load_scenario(path)
    assert prepare_step(scenario.steps[0], scenario, {})[0].request.body == {"name": payload}
    assert prepare_step(scenario.steps[1], scenario, {})[0].request.body == {"value": payload}


def test_result_alone_in_authored_business_object_is_literal(tmp_path):
    path, _ = bundle(tmp_path, steps=[include(**{"with": {"name": {"result": "ok"}}}),
        request("read", body={"result": "ok", "nested": {"result": False}})])
    scenario = load_scenario(path)
    assert prepare_step(scenario.steps[0], scenario, {})[0].request.body == {"name": {"result": "ok"}}
    assert prepare_step(scenario.steps[1], scenario, {})[0].request.body == {"result": "ok", "nested": {"result": False}}


def test_repeated_include_and_later_with_use_actual_isolated_result(tmp_path):
    path, _ = bundle(tmp_path, steps=[include("first"), include("second", **{"with": {
        "name": named("record_name", "first")}}), request("read", body={
            "first": named(source="first"), "second": named(source="second")})])
    scenario = load_scenario(path)
    prior = {"first/create": NormalizedResponse(True, {"id": 4, "name": "Observed"}, 201, None),
             "second/create": NormalizedResponse(True, {"id": 5, "name": "Observed"}, 201, None)}
    assert prepare_step(scenario.steps[1], scenario, prior)[0].request.body == {"name": "Observed"}
    assert prepare_step(scenario.steps[2], scenario, prior)[0].request.body == {"first": 4, "second": 5}


def test_internal_step_rename_requires_pin_update_but_not_caller_change(tmp_path):
    path, child_path = bundle(tmp_path)
    before = path.read_bytes()
    first = load_scenario(path)
    raw = yaml.safe_load(child_path.read_text())
    raw["steps"][0]["id"] = "create_v2"
    for source in raw["results"].values():
        source["from_step"] = "create_v2"
    child_path.write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_scenario(path)
    sidecar = path.with_suffix(".includes.json")
    pins = json.loads(sidecar.read_text())
    pins["scenarios"]["shared.create"]["sha256"] = hashlib.sha256(child_path.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(pins))
    second = load_scenario(path)
    assert path.read_bytes() == before
    assert first.steps[-1].bind[0].from_step == "setup/create"
    assert second.steps[-1].bind[0].from_step == "setup/create_v2"


def test_alias_metadata_is_independent_keyword_only_and_not_runtime_values(tmp_path):
    from dataclasses import fields
    from refracto.declaration.model import Scenario
    path, _ = bundle(tmp_path)
    first, second = load_scenario(path), load_scenario(path)
    for name in ("results", "included_results"):
        definition = next(field for field in fields(Scenario) if field.name == name)
        assert definition.kw_only and not definition.compare and not definition.repr
        assert name not in Scenario.__match_args__
    assert first.included_results is not second.included_results
    first.included_results.clear()
    assert second.included_results and first == second


@pytest.mark.parametrize("position", ["path", "body", "whole_body", "fill", "response", "ui_value",
                                     "ui_id", "state", "matching", "with"])
def test_named_results_work_in_existing_value_positions(tmp_path, position):
    value = {"nested": [False, 0, ""]} if position == "whole_body" else 7
    follow = request("after")
    if position == "path":
        follow["do"]["request"]["path"] = ["items", named()]
    elif position == "body":
        follow["do"]["request"]["body"] = {"nested": [named()]}
    elif position == "whole_body":
        follow["do"]["request"]["body"] = named()
    elif position == "fill":
        follow = {"id": "after", "do": "fill", "target": "name", "value": named()}
    elif position == "response":
        follow["expect"]["response"] = [{"check": "field_equals", "field": "id", "value": named()}]
    elif position in {"ui_value", "ui_id"}:
        follow = {"id": "after", "do": "click", "target": "save", "expect": {"ui": [{
            "check": "object_field_equals", "anchor": "rows", "field": "id",
            "id": named(), "value": named()}]}}
    elif position == "state":
        follow["expect"]["backend_state"] = [{"check": "span_attr", "span": "saved", "attr": "id",
                                              "op": "==", "value": named()}]
    elif position == "matching":
        follow["expect"]["response"] = [{"check": "collection_matching_count", "field": "items",
                                         "matching": {"id": named()}, "count": 1}]
    elif position == "with":
        follow = include("after", **{"with": {"name": named()}})
    path, _ = bundle(tmp_path, steps=[include(), follow])
    scenario = load_scenario(path)
    prepared, bound = prepare_step(scenario.steps[-1], scenario, norms(id=value))
    assert list(bound.values()) == [value]
    assert len(bound) == 1
    if position == "path":
        assert prepared.request.path == "items/7"
    elif position == "body":
        assert prepared.request.body == {"nested": [7]}
    elif position == "whole_body":
        assert prepared.request.body == value
    elif position == "fill":
        assert prepared.value == 7
    elif position == "response":
        assert prepared.expect.response[0].params["value"] == 7
    elif position in {"ui_value", "ui_id"}:
        assert prepared.expect.frontend[0].params["value"] == prepared.expect.frontend[0].params["id"] == 7
    elif position == "state":
        assert prepared.expect.backend_state[0].params["value"] == 7
    elif position == "matching":
        assert prepared.expect.response[0].params["matching"] == {"id": 7}
    elif position == "with":
        assert prepared.request.body == {"name": 7}


def run_backend(path, responses=None, *, api=None, **kwargs):
    from refracto.runner import run_scenario
    from tests.fakes import FakeApi
    from tests.test_scenario_include import adapters_for
    api = FakeApi(responses) if api is None else api
    return run_scenario(path, adapters_for(api), projections=("backend",), **kwargs), api


@pytest.mark.parametrize("value", [0, False, True, "", "ACTUAL-PRIVATE-RESULT-SENTINEL"])
def test_consumed_actual_values_preserve_type_and_hide_default_report_repr(tmp_path, value):
    path, _ = bundle(tmp_path, steps=[include(), request("consumer", path=["read"], body={"value": named()})])
    report, api = run_backend(path, {("POST", "items"): {"json": {"success": True, "data": {"id": value}}}})
    assert report.status == "PASSED"
    actual = api.sent[-1].body["value"]
    assert type(actual) is type(value) and actual == value
    assert list(report.domains[0].steps[-1].resolved_bindings.values()) == [value]
    assert "ACTUAL-PRIVATE-RESULT-SENTINEL" not in repr(report)
    assert "ACTUAL-PRIVATE-RESULT-SENTINEL" not in repr(report.domains[0])
    assert "ACTUAL-PRIVATE-RESULT-SENTINEL" not in repr(report.domains[0].steps[-1])


@pytest.mark.parametrize("fields", [{}, {"id": None}])
def test_consumed_missing_or_null_result_fails_before_consumer_action(tmp_path, fields):
    path, _ = bundle(tmp_path, steps=[include(), request("consumer", path=["read"], body={"value": named()}),
                                    {"id": "after", "do": "wait", "duration": 0}])
    report, api = run_backend(path, {("POST", "items"): {"json": {"success": True, "data": fields}}})
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "BLOCKED", "COMPLETED"]
    assert len(api.sent) == 1 and report.domains[0].steps[1].resolved_bindings == {}


def test_unused_missing_result_does_not_invent_a_runtime_obligation(tmp_path):
    path, _ = bundle(tmp_path, steps=[include(), request("consumer", path=["read"])])
    report, api = run_backend(path)
    assert report.status == "PASSED" and len(api.sent) == 2
    assert all(not step.resolved_bindings for step in report.domains[0].steps)


def test_named_result_resolution_is_atomic_with_multiple_outputs(tmp_path):
    path, _ = bundle(tmp_path, steps=[include(), request("consumer", path=["read"], body={
        "first": named(), "second": named("record_name")})])
    report, api = run_backend(path, {("POST", "items"): {"json": {"success": True, "data": {"id": 7}}}})
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "BLOCKED"]
    assert report.domains[0].steps[-1].resolved_bindings == {} and len(api.sent) == 1


@pytest.mark.parametrize("stop", ["FAILED", "ERROR", "SKIPPED"])
def test_child_stop_after_result_source_prevents_early_return(tmp_path, stop):
    from refracto.runner import PollConfig
    from tests.fakes import FakeApi
    raw = child()
    later = request("later", path=["later"])
    later["on_failure"] = "stop"
    later["do"]["request"]["method"] = "GET"
    if stop == "SKIPPED":
        later["poll"] = {"on_timeout": "SKIP"}
    raw["steps"].extend([later, {"id": "child_after", "do": "wait", "duration": 0}])
    path, _ = bundle(tmp_path, child_raw=raw)
    class Fault(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            if spec.path == "later" and stop == "ERROR":
                raise ValueError("injected failure after output source")
            return response
    api = Fault({("POST", "items"): {"json": {"success": True, "data": {"id": 7}}},
                 ("GET", "later"): {"json": {"success": False}}})
    clock = [0.0]
    def sleep(duration):
        clock[0] += duration
    report, _ = run_backend(path, api=api, now=lambda: clock[0], sleep=sleep,
                            poll_config=PollConfig(timeout=.1, interval=.1))
    assert [step.status for step in report.domains[0].steps] == ["PASSED", stop, "BLOCKED", "BLOCKED"]
    assert all(spec.path in {"items", "later"} for spec in api.sent)
    assert report.domains[0].steps[-1].resolved_bindings == {}


@pytest.mark.parametrize("observed,expected", [(False, 0), (0, False), (True, 1), (1, True)])
def test_named_result_assertions_keep_existing_strict_type_comparison(tmp_path, observed, expected):
    path, _ = bundle(tmp_path, steps=[include(), request("read", path=["read"], checks=[{
        "check": "field_equals", "field": "id", "value": named()}])])
    report, _ = run_backend(path, {("POST", "items"): {"json": {"success": True, "data": {"id": expected}}},
                                  ("POST", "read"): {"json": {"success": True, "data": {"id": observed}}}})
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED"]


def test_named_result_models_and_backend_reports_equal_independent_flat_flow(tmp_path, monkeypatch):
    from refracto.projection import backend
    raw = child()
    raw["parameters"] = {}
    raw["steps"][0]["do"]["request"]["body"] = {"name": "Fixed"}
    read = request("read", path=["items", named()], body={"name": named("record_name")})
    path, _ = bundle(tmp_path, child_raw=raw, steps=[include(), read])
    # Independent authored flat declaration uses ordinary local response refs.
    flat = {"schema_version": 1, "scenario": "example.parent", "users": ["user"], "steps": [
        request("setup/create", body={"name": "Fixed"}),
        request("read", path=["items", {"from_step": "setup/create", "response_field": "id"}],
                body={"name": {"from_step": "setup/create", "response_field": "name"}})]}
    flat_path = tmp_path / "flat.yaml"
    flat_path.write_text(yaml.safe_dump(flat))
    assert load_scenario(path) == load_scenario(flat_path)
    monkeypatch.setattr(backend, "gen_traceparent", lambda: "00-" + "1" * 32 + "-" + "2" * 16 + "-01")
    responses = {("POST", "items"): {"json": {"success": True, "data": {"id": 7, "name": "Actual"}}}}
    included, included_api = run_backend(path, responses)
    flattened, flat_api = run_backend(flat_path, responses)
    assert included.status == flattened.status == "PASSED"
    assert included == flattened
    assert included_api.sent == flat_api.sent


def test_invalid_named_reference_fails_before_authentication_or_actions(tmp_path):
    from refracto.runner import run_scenario
    from tests.test_scenario_include import adapters_for
    path, _ = bundle(tmp_path, steps=[include(), request("read", body={"id": named("not_exported")})])
    class Forbidden:
        def __getattr__(self, name):
            raise AssertionError("adapter accessed before declaration finished")
    with pytest.raises(DeclarationError, match="declared result"):
        run_scenario(path, adapters_for(api=Forbidden(), auth=Forbidden()), projections=("backend",))
