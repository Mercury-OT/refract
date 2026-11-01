"""Preflight and symbolic boundary controls for pinned Scenario Flows."""
import copy
import hashlib
import json

import pytest
import yaml

from refracto.cli import main
from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import DeclarationError, load_flow, load_scenario
from refracto.declaration.model import Input, ResultSource, ValueRef


def scenario(identifier="records.create", *, reads=True, writes=True):
    result = {"schema_version": 1, "scenario": identifier, "users": ["operator"],
              "steps": [{"id": "submit", "do": {"request": {
                  "method": "POST", "path": ["records"],
                  "body": {"name": {"from_flow": "name"} if reads else "Name"}}},
                  "expect": {"response": [{"check": "success"}]}}]}
    if writes:
        result["write_flow"] = {"record_id": {"from_step": "submit", "response_field": "id"}}
    return result


def flow(*, calls=None, parameters=None):
    return {"schema_version": 1, "flow": "records.lifecycle", "users": ["tester"],
            "parameters": {"name": {"initial": "Initial"}, "record_id": {}} if parameters is None else parameters,
            "scenarios": calls or [{"id": "create", "scenario": "records.create",
                                    "with_users": {"operator": "tester"}}]}


def bundle(tmp_path, *, document=None, sources=None):
    document = flow() if document is None else document
    sources = [scenario()] if sources is None else sources
    manifest = {"manifest_version": 1, "scenarios": {}}
    paths = []
    for index, source in enumerate(sources):
        path = tmp_path / f"scenario-{index}.yaml"
        path.write_text(yaml.safe_dump(source, sort_keys=False))
        paths.append(path)
        manifest["scenarios"][source["scenario"]] = {
            "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path = tmp_path / "flow.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    path.with_suffix(".scenarios.json").write_text(json.dumps(manifest))
    return path, paths


def rewrite_manifest(path, change):
    sidecar = path.with_suffix(".scenarios.json")
    manifest = json.loads(sidecar.read_text())
    change(manifest)
    sidecar.write_text(json.dumps(manifest))


def test_colon_names_cannot_alias_cross_scenario_bindings_in_review(tmp_path):
    from refracto.declaration.expansion import flow_expansion_view

    def source(identifier, step, field):
        return {"schema_version": 1, "scenario": identifier, "users": [], "steps": [
            {"id": step, "do": {"request": {"method": "GET", "path": ["records"]}},
             "expect": {"response": [{"check": "success"}]}},
            {"id": "consume", "do": {"request": {"method": "POST", "path": ["records"],
             "body": {"copied": {"from_step": step, "response_field": field}}}},
             "expect": {"response": [{"check": "success"}]}}]}

    path, _ = bundle(tmp_path, sources=[source("first", "abc:1", "s:f"), source("second", "s", "f")],
        document={"schema_version": 1, "flow": "records.review", "users": [], "scenarios": [
            {"id": "a", "scenario": "first"}, {"id": "a:5:abc", "scenario": "second"}]})
    declaration = load_flow(path)
    bindings = [binding for step in declaration.scenario.steps for binding in step.bind]
    assert len({binding.placeholder for binding in bindings}) == len(bindings) == 2
    expanded = flow_expansion_view(declaration)["execution"]["steps"]
    observed = {step["id"]: step["do"]["request"]["body"]["entries"]["copied"]
                for step in expanded if step["id"].endswith("/consume")}
    assert observed["a/consume"]["from_step"] == "a/abc:1"
    assert observed["a/consume"]["response_field"] == "s:f"
    assert observed["a:5:abc/consume"]["from_step"] == "a:5:abc/s"
    assert observed["a:5:abc/consume"]["response_field"] == "f"


def test_compilation_preserves_node_identity_typed_reads_and_mapping(tmp_path):
    calls = [{"id": node, "scenario": "records.create", "with_users": {"operator": "tester"}}
             for node in ("first", "second")]
    path, sources = bundle(tmp_path, document=flow(calls=calls))
    declaration = load_flow(path)
    assert [step.id for step in declaration.scenario.steps] == ["first/submit", "second/submit"]
    assert declaration.nodes[0].write_flow == {"record_id": ResultSource("first/submit", "id")}
    assert declaration.nodes[1].write_flow == {"record_id": ResultSource("second/submit", "id")}
    assert declaration.nodes[0].read_inputs != declaration.nodes[1].read_inputs
    assert declaration.scenario.steps[0].user == "tester"
    assert declaration.scenario.source_lookup["first/submit"]["sha256"] == hashlib.sha256(sources[0].read_bytes()).hexdigest()
    assert declaration.scenario.source_lookup["first/submit"]["flow_node_id"] == "first"
    generated = next(iter(declaration.nodes[0].read_inputs))
    assert declaration.scenario.parameters[generated] == ValueRef("flow", "name")
    copied = copy.deepcopy(declaration.scenario)
    copied.inputs = [Input(item.kind, "Snapshot" if item.kind == generated else item.value) for item in copied.inputs]
    prepared, _ = prepare_step(copied.steps[0], copied, {})
    assert prepared.request.body == {"name": "Snapshot"}


@pytest.mark.parametrize("initial", [None, False, 0, "", {}, [], {"from_flow": "literal"}, {"from_run": "unique"}])
def test_initial_values_are_literal_and_distinct_from_unset(tmp_path, initial):
    path, _ = bundle(tmp_path, document=flow(parameters={"name": {"initial": initial}, "record_id": {}}))
    declaration = load_flow(path)
    assert declaration.parameters["name"].initialized is True
    assert declaration.parameters["name"].initial == initial
    assert declaration.parameters["record_id"].initialized is False


@pytest.mark.parametrize("source", [scenario(), scenario(reads=False), scenario(writes=False)])
def test_flow_dependent_scenario_cannot_load_standalone(tmp_path, source):
    _, sources = bundle(tmp_path, sources=[source])
    with pytest.raises(DeclarationError, match="Flow"):
        load_scenario(sources[0])


def test_ordinary_scenario_loads_standalone_and_in_flow(tmp_path):
    path, sources = bundle(tmp_path, sources=[scenario(reads=False, writes=False)])
    assert load_scenario(sources[0]).id == "records.create"
    assert load_flow(path).nodes[0].scenario_id == "records.create"


@pytest.mark.parametrize("change", [
    lambda doc: doc.update(schema_version=True),
    lambda doc: doc.update(on_failure="retry"),
    lambda doc: doc.update(parameters={"name": "value"}),
    lambda doc: doc["parameters"]["name"].update(type="string"),
    lambda doc: doc["parameters"]["name"].update(initial=float("nan")),
    lambda doc: doc["scenarios"].append(copy.deepcopy(doc["scenarios"][0])),
    lambda doc: doc["scenarios"][0].update(id="path/node"),
    lambda doc: doc["scenarios"][0].update(scenario={"from_flow": "name"}),
    lambda doc: doc["scenarios"][0].update(with_users={"wrong": "tester"}),
    lambda doc: doc["scenarios"][0].pop("with_users"),
    lambda doc: doc["scenarios"][0].update(with_users={"operator": "other"}),
    lambda doc: doc["scenarios"][0].update(**{"with": {"name": "override"}}),
    lambda doc: doc["scenarios"].extend({"id": str(index), "scenario": "records.create"} for index in range(100)),
])
def test_flow_preflight_rejects_invalid_shapes_and_mappings(tmp_path, change):
    document = flow()
    change(document)
    path, _ = bundle(tmp_path, document=document)
    with pytest.raises(DeclarationError):
        load_flow(path)


@pytest.mark.parametrize("source", [
    {"from_flow": "missing"}, {"from_flow": "name", "fallback": "Name"},
    {"from_parameter": "missing"}, {"from_step": "other", "response_field": "id"},
    {"from_step": "submit", "response_field": "id", "key": "first"},
    {"from_step": "submit", "result": "id"}, {"concat": ["Name"]}, "Name", None,
])
def test_write_source_shape_and_visibility_are_validated(tmp_path, source):
    child = scenario()
    child["write_flow"] = {"record_id": source}
    path, _ = bundle(tmp_path, sources=[child])
    with pytest.raises(DeclarationError):
        load_flow(path)


def test_parameter_and_flow_write_sources_keep_actual_scope(tmp_path):
    child = scenario()
    child["parameters"] = {"local": {"from_flow": "name"}}
    child["write_flow"] = {"record_id": {"from_parameter": "local"}, "name": {"from_flow": "name"}}
    path, _ = bundle(tmp_path, sources=[child])
    declaration = load_flow(path)
    writes = declaration.nodes[0].write_flow
    assert writes["name"] == ValueRef("flow", "name")
    assert writes["record_id"].source == "input"
    assert declaration.scenario.parameters[writes["record_id"].key].source == "input"


def test_literal_reference_looking_parameter_never_becomes_flow_read(tmp_path):
    child = scenario(reads=False)
    child["parameters"] = {"payload": {"literal": {"from_flow": "undeclared"}}}
    child["steps"][0]["do"]["request"]["body"] = {"payload": {"from_parameter": "payload"}}
    path, _ = bundle(tmp_path, sources=[child])
    declaration = load_flow(path)
    assert declaration.nodes[0].read_inputs == {}
    prepared, _ = prepare_step(declaration.scenario.steps[0], declaration.scenario, {})
    assert prepared.request.body == {"payload": {"from_flow": "undeclared"}}


@pytest.mark.parametrize("mutation", [
    lambda manifest: manifest.update(manifest_version=True),
    lambda manifest: manifest.update(extra={}),
    lambda manifest: manifest["scenarios"].clear(),
    lambda manifest: manifest["scenarios"]["records.create"].update(sha256="0" * 64),
    lambda manifest: manifest["scenarios"]["records.create"].update(sha256="ABC"),
    lambda manifest: manifest["scenarios"]["records.create"].update(path="../outside.yaml"),
    lambda manifest: manifest["scenarios"]["records.create"].update(path="https://example.invalid/a"),
    lambda manifest: manifest["scenarios"]["records.create"].update(includes_sha256="0" * 64),
])
def test_manifest_identity_and_local_boundary_are_strict(tmp_path, mutation):
    path, _ = bundle(tmp_path)
    rewrite_manifest(path, mutation)
    with pytest.raises(DeclarationError):
        load_flow(path)


def test_changed_scenario_bytes_and_duplicate_sidecar_keys_reject(tmp_path):
    path, sources = bundle(tmp_path)
    sources[0].write_text(sources[0].read_text() + "\n# drift\n")
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_flow(path)
    path.with_suffix(".scenarios.json").write_text('{"manifest_version":1,"manifest_version":1,"scenarios":{}}')
    with pytest.raises(DeclarationError, match="duplicate"):
        load_flow(path)


@pytest.mark.parametrize("sidecar", [False, True])
def test_symlink_dependencies_and_sidecars_reject(tmp_path, sidecar):
    path, sources = bundle(tmp_path)
    original = path.with_suffix(".scenarios.json") if sidecar else sources[0]
    moved = original.with_suffix(".saved")
    original.rename(moved)
    original.symlink_to(moved)
    with pytest.raises(DeclarationError, match="symlink"):
        load_flow(path)


def included_bundle(tmp_path, *, child_write=False):
    nested = scenario("shared.create", writes=child_write)
    nested["results"] = {"record_id": {"from_step": "submit", "response_field": "id"}}
    nested_path = tmp_path / "shared.yaml"
    nested_path.write_text(yaml.safe_dump(nested, sort_keys=False))
    caller = {"schema_version": 1, "scenario": "records.create", "users": ["operator"],
              "steps": [{"id": "setup", "do": {"include": "shared.create"}}],
              "write_flow": {"record_id": {"from_step": "setup", "result": "record_id"}}}
    path, sources = bundle(tmp_path, sources=[caller])
    includes = sources[0].with_suffix(".includes.json")
    includes.write_text(json.dumps({"manifest_version": 1, "scenarios": {"shared.create": {
        "path": nested_path.name, "sha256": hashlib.sha256(nested_path.read_bytes()).hexdigest()}}}))
    rewrite_manifest(path, lambda manifest: manifest["scenarios"]["records.create"].update(
        includes_sha256=hashlib.sha256(includes.read_bytes()).hexdigest()))
    return path, includes, nested_path


def test_include_reads_same_snapshot_and_publishes_only_through_caller(tmp_path):
    path, _, _ = included_bundle(tmp_path)
    declaration = load_flow(path)
    assert declaration.nodes[0].step_ids == ("create/setup/submit",)
    assert declaration.nodes[0].write_flow == {"record_id": ResultSource("create/setup/submit", "id")}
    assert set(declaration.nodes[0].read_inputs.values()) == {"name"}
    assert "includes_sha256" in declaration.dependencies["records.create"]
    assert declaration.dependencies["records.create"]["includes"]["shared.create"]["path"] == "shared.yaml"


def test_included_writer_rejects_even_with_valid_pins(tmp_path):
    path, _, _ = included_bundle(tmp_path, child_write=True)
    with pytest.raises(DeclarationError, match="directly scheduled"):
        load_flow(path)


def test_repinning_include_child_cannot_bypass_flow_identity(tmp_path):
    path, includes, nested = included_bundle(tmp_path)
    load_flow(path)
    nested.write_text(nested.read_text().replace("submit", "changed"))
    manifest = json.loads(includes.read_text())
    manifest["scenarios"]["shared.create"]["sha256"] = hashlib.sha256(nested.read_bytes()).hexdigest()
    includes.write_text(json.dumps(manifest))
    with pytest.raises(DeclarationError, match="sidecar fingerprint"):
        load_flow(path)


def test_cli_and_default_repr_hide_values_and_expansion_is_explicit(tmp_path, capsys):
    secret = "FLOW-INITIAL-CONFIDENTIAL-SENTINEL"
    path, _ = bundle(tmp_path, document=flow(parameters={"name": {"initial": secret}, "record_id": {}}))
    declaration = load_flow(path)
    assert secret not in repr(declaration)
    assert secret not in repr(declaration.parameters)
    assert main(["validate-flow", str(path)]) == 0
    assert secret not in str(capsys.readouterr())
    assert main(["validate-flow", str(path), "--expand"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["parameters"]["name"] == {"initial": secret}
    assert output["scenarios"][0]["write_flow"]["record_id"] == {"from_step": "create/submit", "response_field": "id"}
    assert main(["validate", str(path)]) == 2
    assert capsys.readouterr().out == ""


def test_cli_rejects_invalid_yaml_without_echoing_source_values(tmp_path, capsys):
    path = tmp_path / "flow.yaml"
    path.write_text("schema_version: 1\nflow: records\nsecret: [PRIVATE-FLOW-VALUE\n")
    assert main(["validate-flow", str(path), "--expand"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "PRIVATE-FLOW-VALUE" not in captured.err


@pytest.mark.parametrize("reference", [
    {"from_flow": None}, {"from_flow": True}, {"from_flow": 7}, {"from_flow": []},
    {"from_flow": {}}, {"from_flow": "undeclared"}, {"from_flow": "name", "from_parameter": "local"},
    {"from_flow": "name", "response_field": "id"}, {"from_unknown": "name"},
])
def test_flow_references_require_exact_shape_and_declared_names(tmp_path, reference):
    child = scenario()
    child["steps"][0]["do"]["request"]["body"] = {"nested": [reference]}
    path, _ = bundle(tmp_path, sources=[child])
    with pytest.raises(DeclarationError):
        load_flow(path)


@pytest.mark.parametrize("mutation", [
    lambda child: child["steps"][0].update(user={"from_flow": "name"}),
    lambda child: child["steps"][0].update(session={"from_flow": "name"}),
    lambda child: child["steps"][0].update(id="setup/submit"),
    lambda child: child["steps"][0]["do"]["request"].update(method={"from_flow": "name"}),
    lambda child: child["steps"][0]["expect"]["response"][0].update(check={"from_flow": "name"}),
    lambda child: child.update(results={"value": {"from_flow": "name"}}),
    lambda child: child.update(write_flow={"undeclared": {"from_flow": "name"}}),
])
def test_flow_references_do_not_extend_literal_only_contexts(tmp_path, mutation):
    child = scenario()
    mutation(child)
    path, _ = bundle(tmp_path, sources=[child])
    with pytest.raises(DeclarationError):
        load_flow(path)


def test_flow_parameter_concat_is_symbolic_and_literal_payload_stays_data(tmp_path):
    child = scenario()
    child["parameters"] = {"label": {"concat": ["Prefix-", {"from_flow": "name"}]}}
    child["steps"][0]["do"]["request"]["body"] = {"name": {"from_parameter": "label"}}
    path, _ = bundle(tmp_path, sources=[child])
    declaration = load_flow(path)
    generated = next(iter(declaration.nodes[0].read_inputs))
    execution = copy.deepcopy(declaration.scenario)
    execution.inputs = [Input(item.kind, "Actual" if item.kind == generated else item.value) for item in execution.inputs]
    assert prepare_step(execution.steps[0], execution, {})[0].request.body == {"name": "Prefix-Actual"}


def test_flow_manifest_and_source_hashes_describe_exact_loaded_bytes(tmp_path):
    path, _ = bundle(tmp_path)
    declaration = load_flow(path)
    assert declaration.source_pins["flow_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert declaration.source_pins["manifest_sha256"] == hashlib.sha256(path.with_suffix(".scenarios.json").read_bytes()).hexdigest()
    assert declaration.source_pins["scenarios"] == declaration.dependencies


def test_all_user_mappings_preflight_even_for_later_nodes(tmp_path):
    calls = flow()["scenarios"] + [{"id": "later", "scenario": "records.create", "with_users": {"operator": "unknown"}}]
    path, _ = bundle(tmp_path, document=flow(calls=calls))
    with pytest.raises(DeclarationError, match="declared parent users"):
        load_flow(path)


def test_distinct_users_cannot_collapse_and_anonymous_cannot_authenticate(tmp_path):
    child = scenario()
    child["users"] = ["operator", "reviewer"]
    child["steps"][0]["user"] = "operator"
    document = flow()
    document["scenarios"][0]["with_users"] = {"operator": "tester", "reviewer": "tester"}
    path, _ = bundle(tmp_path, document=document, sources=[child])
    with pytest.raises(DeclarationError, match="distinct"):
        load_flow(path)
    child["users"] = ["anonymous"]
    child["steps"][0].pop("user")
    document["scenarios"][0]["with_users"] = {"anonymous": "tester"}
    path, _ = bundle(tmp_path, document=document, sources=[child])
    with pytest.raises(DeclarationError, match="anonymous"):
        load_flow(path)


def test_implicit_anonymous_scenario_can_run_in_flow_with_other_participants(tmp_path):
    child = scenario()
    child["users"] = []
    document = flow()
    document["users"] = ["tester", "anonymous"]
    document["scenarios"][0].pop("with_users")
    path, _ = bundle(tmp_path, document=document, sources=[child])
    declaration = load_flow(path)
    assert declaration.nodes[0].with_users == {"anonymous": "anonymous"}
    assert declaration.scenario.effective_user(declaration.scenario.steps[0]) is None


def test_flow_rejects_duplicate_yaml_keys_without_values(tmp_path):
    path, _ = bundle(tmp_path)
    path.write_text(path.read_text() + "\non_failure: stop\non_failure: continue\n")
    with pytest.raises(DeclarationError, match="duplicate"):
        load_flow(path)


def test_flow_cannot_schedule_flow_document(tmp_path):
    path, sources = bundle(tmp_path)
    sources[0].write_text(yaml.safe_dump(flow()))
    rewrite_manifest(path, lambda manifest: manifest["scenarios"]["records.create"].update(
        sha256=hashlib.sha256(sources[0].read_bytes()).hexdigest()))
    with pytest.raises(DeclarationError):
        load_flow(path)


def test_flow_rejects_mismatched_scenario_id_and_duplicate_dependency_file(tmp_path):
    path, _ = bundle(tmp_path)
    document = flow()
    document["scenarios"].append({"id": "other", "scenario": "other.id", "with_users": {"operator": "tester"}})
    path.write_text(yaml.safe_dump(document))
    rewrite_manifest(path, lambda manifest: manifest["scenarios"].update({
        "other.id": copy.deepcopy(manifest["scenarios"]["records.create"])}))
    with pytest.raises(DeclarationError, match="distinct"):
        load_flow(path)
    path, sources = bundle(tmp_path)
    sources[0].write_text(sources[0].read_text().replace("records.create", "different.id"))
    rewrite_manifest(path, lambda manifest: manifest["scenarios"]["records.create"].update(
        sha256=hashlib.sha256(sources[0].read_bytes()).hexdigest()))
    with pytest.raises(DeclarationError, match="does not match"):
        load_flow(path)


def test_flow_rejects_65_distinct_scenario_targets_before_reading_sources(tmp_path):
    calls = [{"id": f"node-{index}", "scenario": f"scenario-{index}", "with_users": {"operator": "tester"}}
             for index in range(65)]
    path, _ = bundle(tmp_path, document=flow(calls=calls))
    with pytest.raises(DeclarationError, match="64"):
        load_flow(path)


def test_flow_include_depth_and_missing_manifest_pin_are_rejected(tmp_path):
    path, includes, nested = included_bundle(tmp_path)
    rewrite_manifest(path, lambda manifest: manifest["scenarios"]["records.create"].pop("includes_sha256"))
    with pytest.raises(DeclarationError, match="includes_sha256"):
        load_flow(path)
    path, includes, nested = included_bundle(tmp_path)
    content = yaml.safe_load(nested.read_text())
    content["steps"].append({"id": "nested", "do": {"include": "another.scenario"}})
    nested.write_text(yaml.safe_dump(content))
    manifest = json.loads(includes.read_text())
    manifest["scenarios"]["shared.create"]["sha256"] = hashlib.sha256(nested.read_bytes()).hexdigest()
    includes.write_text(json.dumps(manifest))
    rewrite_manifest(path, lambda manifest: manifest["scenarios"]["records.create"].update(
        includes_sha256=hashlib.sha256(includes.read_bytes()).hexdigest()))
    with pytest.raises(DeclarationError, match="must not include"):
        load_flow(path)
