"""Public, product-neutral controls for bounded Scenario inclusion."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.binding import prepare_step


def leaf(scenario="shared.create", *, parameters=None, actor="editor"):
    return {
        "schema_version": 1, "scenario": scenario, "users": [actor],
        "parameters": {"name": "Default"} if parameters is None else parameters,
        "steps": [{"id": "create", "do": {"request": {
            "method": "POST", "path": ["records"],
            "body": {"name": {"from_parameter": "name"}},
        }}, "expect": {"response": [{"check": "success"}]}}],
    }


def include(step="setup", target="shared.create", **extra):
    return {"id": step, "do": {"include": target}, **extra}


def parent(steps=None, parameters=None):
    return {"schema_version": 1, "scenario": "example.parent", "users": ["editor"],
            "parameters": parameters or {}, "steps": steps or [include()]}


def write_bundle(tmp_path, root=None, child=None, *, sidecar=None):
    child = leaf() if child is None else child
    directory = tmp_path / "shared"
    directory.mkdir(exist_ok=True)
    child_path = directory / "create.yaml"
    child_path.write_text(yaml.safe_dump(child, sort_keys=False))
    root_path = tmp_path / "parent.yaml"
    root_path.write_text(yaml.safe_dump(parent() if root is None else root, sort_keys=False))
    pin = {"manifest_version": 1, "scenarios": {child["scenario"]: {
        "path": "shared/create.yaml", "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest(),
    }}}
    root_path.with_suffix(".includes.json").write_text(json.dumps(pin if sidecar is None else sidecar))
    return root_path, child_path


def test_include_loads_as_qualified_leaves_and_records_source(tmp_path):
    path, child = write_bundle(tmp_path)
    scenario = load_scenario(path)
    assert [step.id for step in scenario.steps] == ["setup/create"]
    source = scenario.source_lookup["setup/create"]
    assert source == {"scenario_id": "shared.create", "step_id": "create",
                      "include_step_id": "setup", "sha256": hashlib.sha256(child.read_bytes()).hexdigest(),
                      "source_user": "editor", "effective_user": "editor"}
    step, bound = prepare_step(scenario.steps[0], scenario, {})
    assert step.request.body == {"name": "Default"}
    assert bound == {}


def test_repeated_include_uses_isolated_parameters(tmp_path):
    root = parent([include("first", **{"with": {"name": "One"}}),
                   include("second", **{"with": {"name": "Two"}})])
    path, _ = write_bundle(tmp_path, root)
    scenario = load_scenario(path)
    assert [prepare_step(step, scenario, {})[0].request.body for step in scenario.steps] == [
        {"name": "One"}, {"name": "Two"}]
    assert scenario.steps[0].request is not scenario.steps[1].request


def test_caller_reads_named_result_from_qualified_execution_source(tmp_path):
    read = {"id": "read", "do": {"request": {"method": "GET", "path": [
        "records", {"from_step": "setup", "result": "record_id"}]}},
        "expect": {"response": [{"check": "success"}]}}
    child = leaf()
    child["results"] = {"record_id": {"from_step": "create", "response_field": "id"}}
    path, _ = write_bundle(tmp_path, parent([include(), read]), child)
    scenario = load_scenario(path)
    assert scenario.steps[1].bind[0].from_step == "setup/create"


def test_child_bytes_rechecked_on_every_load(tmp_path):
    path, child = write_bundle(tmp_path)
    load_scenario(path)
    child.write_text(child.read_text() + "\n# changed\n")
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_scenario(path)


@pytest.mark.parametrize("field,value", [("expect", {}), ("poll", {}), ("target", "x"),
                                       ("value", "x"), ("duration", 1), ("repeat", 2), ("times", 2)])
def test_include_rejects_behavior_overrides(tmp_path, field, value):
    path, _ = write_bundle(tmp_path, parent([include(**{field: value})]))
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("target", [None, 1, {"from_parameter": "name"}, ["shared.create"]])
def test_dynamic_include_rejected(tmp_path, target):
    path, _ = write_bundle(tmp_path, parent([include(target=target)]))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_child_user_alias_maps_to_parent_user(tmp_path):
    path, _ = write_bundle(tmp_path, child=leaf(actor="reader"))
    scenario = load_scenario(path)
    assert scenario.users == ["editor"]
    assert scenario.steps[0].user == "editor"


def test_child_without_assertion_rejected(tmp_path):
    child = leaf()
    del child["steps"][0]["expect"]
    path, _ = write_bundle(tmp_path, child=child)
    with pytest.raises(DeclarationError, match="assertion"):
        load_scenario(path)


def test_nested_include_rejected(tmp_path):
    child = leaf()
    child["steps"].append(include("nested", "shared.other"))
    path, _ = write_bundle(tmp_path, child=child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_unknown_with_parameter_rejected(tmp_path):
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"unknown": 1}})]))
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("sid", ["setup/create", "with/slash"])
def test_composition_source_slash_rejected(tmp_path, sid):
    path, _ = write_bundle(tmp_path, parent([include(sid)]))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def rewrite_pin(path, child):
    pin_path = path.with_suffix(".includes.json")
    pin = json.loads(pin_path.read_text())
    next(iter(pin["scenarios"].values()))["sha256"] = hashlib.sha256(child.read_bytes()).hexdigest()
    pin_path.write_text(json.dumps(pin))


def test_child_internal_response_and_caller_with_are_distinct_scopes(tmp_path):
    from refracto.ports import NormalizedResponse
    source = leaf()["steps"][0]
    source["id"] = "before"
    child = leaf()
    child["steps"].append({"id": "read", "do": {"request": {"method": "GET", "path": [
        "records", {"from_step": "create", "response_field": "id"}]}},
        "expect": {"response": [{"check": "success"}]}})
    root = parent([source, include(**{"with": {"name": {
        "from_step": "before", "response_field": "name"}}})], parameters={"name": "Root"})
    path, _ = write_bundle(tmp_path, root, child)
    scenario = load_scenario(path)
    assert scenario.steps[1].bind[0].from_step == "before"
    assert scenario.steps[2].bind[0].from_step == "setup/create"
    prepared, _ = prepare_step(scenario.steps[1], scenario, {
        "before": NormalizedResponse(True, {"name": "Actual"}, 200, None)})
    assert prepared.request.body == {"name": "Actual"}


@pytest.mark.parametrize("value", [None, 0, False, True, "", {"from_step": "not-a-reference", "response_field": "id"}])
def test_literal_parameter_values_remain_literal(tmp_path, value):
    root = parent([include(**{"with": {"name": {"from_parameter": "payload"}}})],
                  parameters={"payload": {"literal": value}})
    path, _ = write_bundle(tmp_path, root)
    scenario = load_scenario(path)
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    assert type(prepared.request.body["name"]) is type(value)
    assert prepared.request.body["name"] == value


def test_nested_with_response_data_is_symbolic_until_execution(tmp_path):
    from refracto.ports import NormalizedResponse
    before = copy.deepcopy(leaf()["steps"][0])
    before["id"] = "before"
    before["do"]["request"]["body"] = {}
    root = parent([before, include(**{"with": {"name": {
        "actual": {"from_step": "before", "response_field": "id"}}}})])
    path, _ = write_bundle(tmp_path, root)
    scenario = load_scenario(path)
    prepared, _ = prepare_step(scenario.steps[1], scenario, {
        "before": NormalizedResponse(True, {"id": 0}, 200, None)})
    assert prepared.request.body == {"name": {"actual": 0}}


def test_invalid_static_parameter_use_rejected(tmp_path):
    child = leaf()
    child["steps"][0]["do"]["request"]["path"] = ["records", {"from_parameter": "name"}]
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"name": []}})]), child)
    with pytest.raises(DeclarationError, match="path"):
        load_scenario(path)


@pytest.mark.parametrize("bad_path", ["/tmp/child.yaml", "../child.yaml", "file://child.yaml", "https://example.com/a", "shared\\create.yaml", "shared/*.yaml", "$CHILD.yaml", "~/child.yaml", "shared/\x00create.yaml"])
def test_forbidden_dependency_paths(tmp_path, bad_path):
    path, _ = write_bundle(tmp_path)
    pin_path = path.with_suffix(".includes.json")
    pin = json.loads(pin_path.read_text())
    pin["scenarios"]["shared.create"]["path"] = bad_path
    pin_path.write_text(json.dumps(pin))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_dependency_symlink_rejected(tmp_path):
    path, child = write_bundle(tmp_path)
    real = child.with_suffix(".real")
    child.rename(real)
    child.symlink_to(real.name)
    with pytest.raises(DeclarationError, match="symlink"):
        load_scenario(path)


def test_sidecar_symlink_rejected(tmp_path):
    path, _ = write_bundle(tmp_path)
    manifest = path.with_suffix(".includes.json")
    real = manifest.with_suffix(".real")
    manifest.rename(real)
    manifest.symlink_to(real.name)
    with pytest.raises(DeclarationError, match="symlink"):
        load_scenario(path)


@pytest.mark.parametrize("change", ["extra", "missing", "duplicate", "wrong_version", "wrong_hash", "unknown"])
def test_strict_sidecar_schema(tmp_path, change):
    path, _ = write_bundle(tmp_path)
    pin_path = path.with_suffix(".includes.json")
    pin = json.loads(pin_path.read_text())
    if change == "extra":
        pin["scenarios"]["unused"] = dict(pin["scenarios"]["shared.create"])
    elif change == "missing":
        pin["scenarios"] = {}
    elif change == "wrong_version":
        pin["manifest_version"] = True
    elif change == "wrong_hash":
        pin["scenarios"]["shared.create"]["sha256"] = "A" * 64
    elif change == "unknown":
        pin["scenarios"]["shared.create"]["extra"] = "not allowed"
    if change == "duplicate":
        pin_path.write_text('{"manifest_version":1,"manifest_version":1,"scenarios":{}}')
    else:
        pin_path.write_text(json.dumps(pin))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_read_once_uses_verified_buffer_after_replacement(tmp_path, monkeypatch):
    path, child = write_bundle(tmp_path, parent([include("one"), include("two")]))
    original = Path.read_bytes
    reads = []

    def replace_after_read(file):
        data = original(file)
        if file.resolve() == child.resolve():
            reads.append(file)
            file.write_text("invalid replacement")
        return data

    monkeypatch.setattr(Path, "read_bytes", replace_after_read)
    scenario = load_scenario(path)
    assert len(reads) == 1
    assert [step.id for step in scenario.steps] == ["one/create", "two/create"]
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_resolution_independent_of_cwd_and_network(tmp_path, monkeypatch):
    import socket
    path, _ = write_bundle(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.chdir(tmp_path.parent)
    assert load_scenario(path).steps[0].id == "setup/create"


@pytest.mark.parametrize("count,valid", [(1000, True), (1001, False)])
def test_leaf_limit_is_inclusive(tmp_path, count, valid):
    path, _ = write_bundle(tmp_path, parent([include(f"call_{i}") for i in range(count)]))
    if valid:
        assert len(load_scenario(path).steps) == count
    else:
        with pytest.raises(DeclarationError, match="1,000|1000"):
            load_scenario(path)


@pytest.mark.parametrize("count,valid", [(64, True), (65, False)])
def test_distinct_child_limit_is_inclusive(tmp_path, count, valid):
    root = parent([include(f"call_{i}", f"shared.{i}") for i in range(count)])
    path = tmp_path / "parent.yaml"
    path.write_text(yaml.safe_dump(root))
    pins = {}
    for index in range(count):
        child_path = tmp_path / f"child_{index}.yaml"
        child_path.write_text(yaml.safe_dump(leaf(f"shared.{index}")))
        pins[f"shared.{index}"] = {"path": child_path.name, "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1, "scenarios": pins}))
    if valid:
        assert len(load_scenario(path).steps) == count
    else:
        with pytest.raises(DeclarationError, match="64"):
            load_scenario(path)


def adapters_for(api=None, auth=None, recorder_factory=None):
    from refracto import ports
    from refracto.runner import Adapters
    from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
    return Adapters(auth or FakeAuth(), api or FakeApi(), None, None,
                    recorder_factory or FakeRecorder,
                    lambda template: ports.RequestSpec(
                        template.method, template.path, template.body), FakeNormalizer())


def test_late_invalid_include_never_reaches_any_adapter(tmp_path):
    from refracto.runner import run_scenario
    first = leaf()["steps"][0]
    first["do"]["request"]["body"] = {}
    path, child = write_bundle(tmp_path, parent([first, include()]))
    child.write_text(child.read_text() + "\n# drift\n")
    class Forbidden:
        def __getattr__(self, name):
            raise AssertionError("adapter was reached before full validation")
    adapters = adapters_for(api=Forbidden(), auth=Forbidden(), recorder_factory=Forbidden())
    with pytest.raises(DeclarationError):
        run_scenario(path, adapters, projections=("backend",))


@pytest.mark.parametrize("stop", ["FAILED", "ERROR", "SKIPPED"])
def test_child_stop_blocks_remaining_child_and_parent(tmp_path, stop):
    from refracto.runner import PollConfig, run_scenario
    from tests.fakes import FakeApi
    child = leaf()
    child["steps"][0]["do"]["request"] = {"method": "GET", "path": ["records"]}
    child["steps"][0]["on_failure"] = "stop"
    child["steps"].append({"id": "after", "do": "wait", "duration": 0})
    if stop == "SKIPPED":
        child["steps"][0]["poll"] = {"on_timeout": "SKIP"}
    path, _ = write_bundle(tmp_path, parent([include(), {"id": "parent_after", "do": "wait", "duration": 0}]), child)
    api = FakeApi({("GET", "records"): {"json": {"success": False}}})
    if stop == "ERROR":
        def boom(*args):
            raise ValueError("injected send error")
        api.send = boom
    time = [0.0]
    def sleep(seconds):
        time[0] += seconds
    report = run_scenario(path, adapters_for(api), projections=("backend",),
                          poll_config=PollConfig(timeout=.1, interval=.1),
                          now=lambda: time[0], sleep=sleep)
    assert [step.status for step in report.domains[0].steps] == [stop, "BLOCKED", "BLOCKED"]
    if stop == "FAILED":
        assert report.localize()[0][1] == "setup/create"
    if stop == "ERROR":
        assert report.localize() == []
    assert report.source_lookup["setup/create"]["scenario_id"] == "shared.create"


@pytest.mark.parametrize("actual", [None, [], {}, "__missing__"])
def test_runtime_bad_path_binding_errors_before_consumer(tmp_path, actual):
    from refracto.runner import run_scenario
    from tests.fakes import FakeApi
    before = copy.deepcopy(leaf()["steps"][0])
    before["id"] = "before"
    before["do"]["request"]["body"] = {}
    child = leaf()
    child["steps"][0]["do"]["request"]["path"] = ["records", {"from_parameter": "name"}]
    root = parent([before, include(**{"with": {"name": {"from_step": "before", "response_field": "id"}}}),
                   {"id": "after", "do": "wait", "duration": 0}])
    path, _ = write_bundle(tmp_path, root, child)
    data = {} if actual == "__missing__" else {"id": actual}
    api = FakeApi({("POST", "records"): {"json": {"success": True, "data": data}}})
    report = run_scenario(path, adapters_for(api), projections=("backend",))
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "BLOCKED", "COMPLETED"]
    assert len(api.sent) == 1


def test_same_role_two_inclusions_run_twice_one_session_and_offline_contract(tmp_path):
    from refracto.runner import run_scenario
    from tests.fakes import FakeApi, FakeAuth
    class Auth(FakeAuth):
        calls = 0
        def session(self, role):
            self.calls += 1
            return super().session(role)
    auth, api = Auth(), FakeApi()
    path, _ = write_bundle(tmp_path, parent([include("one"), include("two")]))
    report = run_scenario(path, adapters_for(api, auth), projections=("backend", "contract"))
    assert report.status == "PASSED"
    assert auth.calls == 1 and len(api.sent) == 2
    assert [record.step_id for record in report.domains[0].provider_recordings] == ["one/create", "two/create"]


def test_contract_failure_uses_qualified_source_lookup(tmp_path):
    from refracto.runner import run_scenario
    from refracto.projection import contract
    from tests.fakes import FakeNormalizer
    path, _ = write_bundle(tmp_path)
    report = run_scenario(path, adapters_for(), projections=("backend",))
    # An independent offline provider-drift fixture exercises localization.
    # A Recorder is no longer allowed to alter accepted live backend evidence.
    drift = copy.deepcopy(report.domains[0].provider_recordings)
    for response in drift:
        response.json = {"success": False}
    report.domains.append(contract.run(load_scenario(path), drift, FakeNormalizer(),
                                       execution_steps=report.domains[0].steps))
    assert report.domains[0].status == "PASSED"
    assert report.domains[1].status == "FAILED"
    assert report.localize()[0][:2] == ("contract", "setup/create")
    assert report.source_lookup[report.localize()[0][1]]["step_id"] == "create"


def test_parameter_namespace_collision_cannot_alias_and_is_not_readable(tmp_path):
    root = parent([include(**{"with": {"name": "Included"}})],
                  parameters={"@include:setup:0": "Root"})
    path, _ = write_bundle(tmp_path, root)
    scenario = load_scenario(path)
    assert prepare_step(scenario.steps[0], scenario, {})[0].request.body == {"name": "Included"}
    assert scenario.parameters["@include:setup:0"] == "Root"
    root = parent([include(), include("two", **{"with": {"name": {"from_parameter": "@include:setup:0"}}})])
    path, _ = write_bundle(tmp_path, root)
    with pytest.raises(DeclarationError, match="unknown parameter"):
        load_scenario(path)


def test_source_metadata_is_independent_keyword_only_and_hidden(tmp_path):
    from dataclasses import fields
    from refracto.declaration.model import Scenario
    from refracto.report import RunReport
    from refracto.runner import run_scenario
    sentinel = "PRIVATE-CALL-VALUE-SENTINEL"
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"name": sentinel}})]))
    first = load_scenario(path)
    second = load_scenario(path)
    report = run_scenario(path, adapters_for(), projections=("backend",))
    assert sentinel not in repr(first) and sentinel not in repr(report)
    assert first.source_lookup is not second.source_lookup
    for cls in (Scenario, RunReport):
        info = next(field for field in fields(cls) if field.name == "source_lookup")
        assert info.kw_only and not info.compare and not info.repr
        assert "source_lookup" not in cls.__match_args__


@pytest.mark.parametrize("mutation", ["parent_ref", "future_ref", "node_ref", "requestless_ref", "duplicate_id", "wrong_id", "self_include"])
def test_scope_and_identity_rejections(tmp_path, mutation):
    root, child = parent(), leaf()
    if mutation == "parent_ref":
        child["steps"][0]["do"]["request"]["body"] = {"name": {"from_step": "parent", "response_field": "name"}}
    elif mutation in {"future_ref", "node_ref", "requestless_ref"}:
        source = {"future_ref": "future/create", "node_ref": "setup", "requestless_ref": "setup/wait"}[mutation]
        child["steps"].append({"id": "wait", "do": "wait", "duration": 0})
        root["steps"].append({"id": "read", "do": {"request": {"method": "GET", "path": [
            {"from_step": source, "response_field": "id"}]}}, "expect": {"response": [{"check": "success"}]}})
        if mutation == "future_ref":
            root["steps"].append(include("future"))
    elif mutation == "duplicate_id":
        root["steps"].append(include())
    elif mutation == "wrong_id":
        child["scenario"] = "other.id"
    elif mutation == "self_include":
        root["scenario"] = "shared.create"
    path, _ = write_bundle(tmp_path, root, child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("suffix", ["\nusers: [editor]\n", "\nunknown: &a [one]\nmore: *a\n", "\nunsafe: !!python/object/apply:os.system ['exit 1']\n"])
def test_invalid_child_yaml_rejected_without_raw_value_leak(tmp_path, suffix):
    path, child = write_bundle(tmp_path)
    child.write_text(child.read_text() + suffix)
    rewrite_pin(path, child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_same_call_and_parent_leaf_cannot_read_generated_namespace(tmp_path):
    child = leaf(parameters={"name": "N", "other": "O"})
    root = parent([include(**{"with": {"name": "One", "other": {"from_parameter": "@include:setup:0"}}})])
    path, _ = write_bundle(tmp_path, root, child)
    with pytest.raises(DeclarationError, match="unknown parameter"):
        load_scenario(path)
    root = parent([include(), {"id": "fill", "do": "fill", "target": "input",
                             "value": {"from_parameter": "@include:setup:0"}}])
    path, _ = write_bundle(tmp_path, root)
    with pytest.raises(DeclarationError, match="unknown parameter"):
        load_scenario(path)


def test_compiled_mutable_parameters_are_isolated_between_calls_and_loads(tmp_path):
    child = leaf(parameters={"name": {"nested": [1]}})
    path, _ = write_bundle(tmp_path, parent([include("one"), include("two")]), child)
    first, second = load_scenario(path), load_scenario(path)
    first.parameters["@include:one:0"]["nested"].append(2)
    assert first.parameters["@include:two:0"] == {"nested": [1]}
    assert second.parameters["@include:one:0"] == {"nested": [1]}


def test_loaded_models_equal_independent_flat_after_explicit_id_renaming(tmp_path):
    from refracto.declaration.model import ValueRef
    child = leaf()
    child["steps"].append({"id": "read", "do": {"request": {"method": "GET", "path": [
        "records", {"from_step": "create", "response_field": "id"}]}},
        "expect": {"response": [{"check": "field_equals", "field": "name", "value": {"from_parameter": "name"}}]}})
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"name": "Concrete"}})]), child)
    flat = {"schema_version": 1, "scenario": "flat", "users": ["editor"], "parameters": {"label": "Concrete"},
            "steps": [
                {"id": "make", "do": {"request": {"method": "POST", "path": ["records"], "body": {"name": {"from_parameter": "label"}}}},
                 "expect": {"response": [{"check": "success"}]}},
                {"id": "retrieve", "do": {"request": {"method": "GET", "path": ["records", {"from_step": "make", "response_field": "id"}]}},
                 "expect": {"response": [{"check": "field_equals", "field": "name", "value": {"from_parameter": "label"}}]}},
            ]}
    flat_path = tmp_path / "flat.yaml"
    flat_path.write_text(yaml.safe_dump(flat))
    included, handwritten = load_scenario(path), load_scenario(flat_path)

    def normalize(scenario, ids):
        output = []
        for step in scenario.steps:
            bindings = {b.placeholder: b for b in step.bind}
            def value(node):
                if isinstance(node, ValueRef):
                    if node.source == "input":
                        return ("parameter", scenario.parameters[node.key])
                    binding = bindings[node.key]
                    return ("response", ids[binding.from_step], binding.field)
                if isinstance(node, list):
                    return [value(item) for item in node]
                if isinstance(node, dict):
                    return {key: value(item) for key, item in node.items()}
                return node
            output.append((ids[step.id], step.action, step.request.method,
                value(step.request.path_segments), value(step.request.body),
                [(a.check, value(a.params)) for a in step.expect.response], step.poll))
        return output
    assert normalize(included, {"setup/create": "a", "setup/read": "b"}) == normalize(handwritten, {"make": "a", "retrieve": "b"})


def dynamic_use_bundle(tmp_path, position):
    """Response values enter an included consumer only through explicit with."""
    first = {"id": "before", "do": {"request": {"method": "GET", "path": ["source"]}},
             "expect": {"response": [{"check": "success"}]}}
    child = leaf(parameters={"name": {} if position == "body" else "Default"})
    request = child["steps"][0]["do"]["request"]
    if position == "assertion":
        child["steps"][0]["expect"]["response"].append({
            "check": "field_equals", "field": "name", "value": {"from_parameter": "name"}})
    elif position == "path":
        request["path"] = ["records", {"from_parameter": "name"}]
    elif position == "body":
        request["body"] = {"from_parameter": "name"}
    elif position == "id":
        child["steps"][0]["do"] = "click"
        child["steps"][0]["target"] = "save"
        child["steps"][0]["expect"]["request"] = request
        child["steps"][0]["expect"]["ui"] = [{"check": "object_field_equals", "anchor": "rows",
            "id": {"from_parameter": "name"}, "field": "name", "value": "Expected"}]
    elif position == "state":
        child["steps"][0]["expect"]["backend_state"] = [{"check": "span_attr", "span": "saved",
            "attr": "name", "op": "==", "value": {"from_parameter": "name"}}]
    root = parent([first, include(**{"with": {"name": {"from_step": "before", "response_field": "value"}}}),
                   {"id": "after", "do": "wait", "duration": 0}])
    return write_bundle(tmp_path, root, child)[0]


@pytest.mark.parametrize("position,value", [
    ("state", {"secret": "SENSITIVE-DYNAMIC"}), ("id", []),
    ("assertion", float("nan")), ("assertion", float("inf")),
    ("id", {"secret": "SENSITIVE-DYNAMIC"}), ("state", []),
    ("body", []), ("body", "SENSITIVE-DYNAMIC"),
    ("body", {"nested": float("nan")}),
    ("path", ""), ("path", False), ("path", True),
])
def test_dynamic_invalid_use_fails_before_consumer_mapping_and_send(tmp_path, position, value):
    from refracto.runner import run_scenario
    from tests.fakes import FakeApi, FakeAuth
    path = dynamic_use_bundle(tmp_path, position)
    class Auth(FakeAuth):
        calls = 0
        def session(self, role):
            self.calls += 1
            return super().session(role)
    api = FakeApi({("GET", "source"): {"json": {"success": True, "data": {"value": value}}}})
    auth = Auth()
    adapters = adapters_for(api, auth)
    original_mapper = adapters.resolve_request
    mapped = []
    def mapper(template):
        mapped.append(template.path)
        return original_mapper(template)
    adapters.resolve_request = mapper
    report = run_scenario(path, adapters, projections=("backend", "contract"))
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "BLOCKED", "COMPLETED"]
    assert mapped == ["source"] and len(api.sent) == 1 and auth.calls == 1
    error_step = report.domains[0].steps[1]
    assert error_step.resolved_bindings == {}
    assert "SENSITIVE-DYNAMIC" not in error_step.detail
    assert "SENSITIVE-DYNAMIC" not in repr(report)


@pytest.mark.parametrize("position,value", [
    ("assertion", 0), ("assertion", False), ("assertion", True), ("assertion", ""),
    ("assertion", []), ("assertion", {"nested": [None, False]}),
    ("body", {}), ("body", {"nested": [False, 0, ""]}),
    ("path", 0), ("path", "actual"),
])
def test_dynamic_valid_neighbors_preserve_typed_values(tmp_path, position, value):
    from refracto.runner import run_scenario
    from tests.fakes import FakeApi
    path = dynamic_use_bundle(tmp_path, position)
    class Echo(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            if spec.method == "POST":
                response.json = {"success": True, "data": {"name": value}}
            return response
    api = Echo({("GET", "source"): {"json": {"success": True, "data": {"value": value}}}})
    report = run_scenario(path, adapters_for(api), projections=("backend", "contract"))
    assert report.status == "PASSED", report.localize()
    assert len(api.sent) == 2
    if position == "body":
        assert api.sent[1].body == value
    elif position == "assertion":
        assert type(api.sent[1].body["name"]) is type(value)
        assert api.sent[1].body["name"] == value


def test_explicit_null_body_remains_supported(tmp_path):
    from refracto.runner import run_scenario
    from tests.fakes import FakeApi
    child = leaf(parameters={"name": {}})
    child["steps"][0]["do"]["request"]["body"] = {"from_parameter": "name"}
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"name": None}})]), child)
    api = FakeApi()
    report = run_scenario(path, adapters_for(api), projections=("backend",))
    assert report.status == "PASSED" and api.sent[0].body is None


def test_dependency_filesystem_error_is_safe_declaration_error(tmp_path, monkeypatch):
    path, child = write_bundle(tmp_path)
    original = Path.resolve
    def denied(file, *args, **kwargs):
        if file == child:
            raise OSError("SENSITIVE-PATH-CONTENT")
        return original(file, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", denied)
    with pytest.raises(DeclarationError) as error:
        load_scenario(path)
    assert "SENSITIVE-PATH-CONTENT" not in str(error.value)


@pytest.mark.parametrize("case", ["missing_sidecar", "malformed_sidecar", "missing_child", "aliased_child", "child_slash"])
def test_dependency_boundary_failures_are_declaration_errors(tmp_path, case):
    root, child = parent(), leaf()
    if case == "aliased_child":
        root["steps"].append(include("another", "other.id"))
    if case == "child_slash":
        child["steps"][0]["id"] = "create/child"
    path, child_path = write_bundle(tmp_path, root, child)
    sidecar = path.with_suffix(".includes.json")
    if case == "missing_sidecar":
        sidecar.unlink()
    elif case == "malformed_sidecar":
        sidecar.write_text("{SENSITIVE-RAW-CONTENT")
    elif case == "missing_child":
        child_path.unlink()
    elif case == "aliased_child":
        pins = json.loads(sidecar.read_text())
        pins["scenarios"]["other.id"] = dict(pins["scenarios"]["shared.create"])
        sidecar.write_text(json.dumps(pins))
    with pytest.raises(DeclarationError) as error:
        load_scenario(path)
    assert "SENSITIVE-RAW-CONTENT" not in str(error.value)


@pytest.mark.parametrize("value", [[], None, False, "mapping-required"])
def test_with_requires_mapping(tmp_path, value):
    path, _ = write_bundle(tmp_path, parent([include(**{"with": value})]))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_frontend_expanded_unsupported_poll_flow_rejects_before_context(tmp_path):
    from refracto.runner import run_scenario
    from tests.fakes import FakeApi, FakeAuth, FakeUi
    child = leaf()
    child["steps"].insert(0, {"id": "open", "do": "open", "target": "records.page"})
    child["steps"][1]["do"]["request"] = {"method": "GET", "path": ["records"]}
    child["steps"][1]["poll"] = {"on_timeout": "SKIP"}
    path, _ = write_bundle(tmp_path, child=child)
    class Auth(FakeAuth):
        calls = 0
        def session(self, role):
            self.calls += 1
            return super().session(role)
    auth, api, ui = Auth(), FakeApi(), FakeUi()
    adapters = adapters_for(api, auth)
    adapters.ui = ui
    report = run_scenario(path, adapters, projections=("frontend",), mock_plan=[])
    assert [step.status for step in report.domains[0].steps] == ["ERROR", "BLOCKED"]
    assert "direct API" in report.domains[0].steps[0].detail
    assert auth.calls == 0 and api.sent == []
    assert ui.open_calls == ui.close_calls == 0 and ui.permits == []
