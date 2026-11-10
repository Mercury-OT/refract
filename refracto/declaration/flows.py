"""Pinned local Flow loading and data-only compilation into Scenario leaves."""
import copy
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

from refracto.declaration.includes import (
    _keys, _map, _safe_file, _unique, is_include, load_dependencies,
    participant_mapping, validate_instantiated,
)
from refracto.declaration.model import (
    Assertion, Binding, Expect, Flow, FlowNode, FlowParameter, Input,
    ResultSource, Scenario, ValueRef,
)


def _error(message):
    from refracto.declaration.loader import DeclarationError
    raise DeclarationError(message)


def _fingerprint(value):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        _error("Flow dependency fingerprint must be lowercase SHA-256")
    return value


def _read(path, label):
    try:
        return path.read_bytes()
    except OSError:
        _error(f"unable to read {label}")


def _compile(flow_id, description, users, definitions, calls, dependencies, policy):
    """Rewrite typed references only; literal data is never reinterpreted."""
    inputs, steps, nodes, sources, all_bindings, user_mappings = [], [], [], {}, {}, {}
    dependency_view = {}
    for call in calls:
        node_id, target = call["id"], call["scenario"]
        child, metadata = dependencies[target]
        if child.users and "with_users" not in call:
            _error("Flow with_users must explicitly map every declared Scenario user")
        participant_call = call
        if not child.users and "with_users" not in call and "anonymous" in users:
            participant_call = {**call, "user": "anonymous"}
        mapping = participant_mapping(participant_call, child.users, users)
        namespace = {key: f"@flow-input:{node_id}:{index}"
                     for index, key in enumerate(child.parameters)}
        flow_inputs, rewritten_bindings = {}, {}
        originals = dict(child.reference_bindings)
        originals.update({binding.placeholder: binding for step in child.steps for binding in step.bind})

        def flow_input(key):
            if key not in flow_inputs:
                flow_inputs[key] = f"@flow-read:{node_id}:{len(flow_inputs)}"
            return flow_inputs[key]

        def binding(key):
            if key not in rewritten_bindings:
                original = originals[key]
                rewritten_bindings[key] = Binding(
                    f"@flow-bind:{len(node_id)}:{node_id}:{key}", f"{node_id}/{original.from_step}", original.field,
                    key=original.key, matching=_map(original.matching, convert),
                    member_field=original.member_field)
            return rewritten_bindings[key]

        def convert(ref):
            if ref.source == "flow":
                return ValueRef("input", flow_input(ref.key))
            if ref.source == "input":
                return ValueRef("input", namespace[ref.key])
            return ValueRef("bind", binding(ref.key).placeholder)

        for key, value in child.parameters.items():
            inputs.append(Input(namespace[key], _map(value, convert)))
        for original in child.steps:
            request = original.request
            if request is not None:
                from urllib.parse import quote
                from refracto.declaration.model import StringConcat
                segments = _map(request.path_segments, convert)
                path = "/".join(
                    "{" + value.source + ":" + value.key + "}" if isinstance(value, ValueRef)
                    else "{concat:" + str(index) + "}" if isinstance(value, StringConcat)
                    else quote(str(value), safe="") for index, value in enumerate(segments))
                request = replace(request, path=path, declared_path=path, path_segments=segments,
                                  body=_map(request.body, convert), query=_map(request.query, convert),
                                  headers=_map(request.headers, convert))
                request.files = copy.deepcopy(original.request.files)
                request.file_descriptors = copy.deepcopy(original.request.file_descriptors)
            expect = Expect(**{
                point: [Assertion(assertion.check, _map(assertion.params, convert))
                        for assertion in getattr(original.expect, point)]
                for point in ("frontend", "response", "backend_state")})
            local_user = child.selected_user(original) or "anonymous"
            effective = mapping[local_user]
            if effective == "anonymous" and original.session is not None:
                _error("anonymous Flow mapping cannot replace a session")
            step = replace(original, id=f"{node_id}/{original.id}", request=request, expect=expect,
                           value=_map(original.value, convert), object_id=_map(original.object_id, convert),
                           bind=[binding(item.placeholder) for item in original.bind],
                           user=None if not users else effective)
            steps.append(step)
            source = copy.deepcopy(child.source_lookup[original.id])
            source.update(flow_node_id=node_id, scheduled_scenario_id=target, effective_user=effective)
            if source.get("include_step_id") is not None:
                source["include_step_id"] = f"{node_id}/{source['include_step_id']}"
            sources[step.id] = source
        writes = {}
        for key, source in child.write_flow.items():
            if isinstance(source, ResultSource):
                writes[key] = replace(source, from_step=f"{node_id}/{source.from_step}")
            elif source.source == "flow":
                flow_input(source.key)
                writes[key] = source
            else:
                writes[key] = convert(source)
        inputs.extend(Input(generated, ValueRef("flow", key)) for key, generated in flow_inputs.items())
        for key in originals:
            item = binding(key)
            all_bindings[item.placeholder] = item
        nodes.append(FlowNode(node_id, target, tuple(f"{node_id}/{step.id}" for step in child.steps),
                              {generated: key for key, generated in flow_inputs.items()}, writes, mapping))
        for include_id, include_mapping in child.include_user_mappings.items():
            user_mappings[f"{node_id}/{include_id}"] = {
                local: mapping[effective] for local, effective in include_mapping.items()}
        dependency_view[target] = {**copy.deepcopy(metadata),
                                   "includes": copy.deepcopy(child.include_dependencies)}
    if len(steps) > 10000:
        _error("Flow exceeds 10000 expanded leaves")
    scenario = Scenario(flow_id, None, "", [], inputs, description, steps, users=list(users),
                        source_lookup=sources, reference_bindings=all_bindings,
                        include_user_mappings=user_mappings)
    validate_instantiated(scenario)
    return Flow(flow_id, description, list(users), definitions, nodes, scenario, dependency_view, policy)


def load_flow(path, *, file_config=None):
    from refracto.declaration.loader import (
        _decode_document, _json, _load_document, _mapping, _string,
    )
    from refracto.files import AssetSnapshots
    snapshots = AssetSnapshots(file_config)
    file = Path(path)
    data = file.read_bytes()
    raw = _decode_document(data)
    _mapping(raw, {"schema_version", "flow", "description", "users", "parameters",
                   "on_failure", "scenarios"}, "Flow top-level")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        _error("Flow schema_version must be integer 1")
    flow_id = _string(raw.get("flow"), "flow")
    description = raw.get("description", "")
    if type(description) is not str:
        _error("Flow description must be a string")
    users = raw.get("users")
    if (type(users) is not list or any(type(user) is not str or not user.strip() for user in users)
            or len(set(users)) != len(users)):
        _error("Flow users must be a list of distinct non-empty literal names")
    policy = raw.get("on_failure", "stop")
    if type(policy) is not str or policy not in {"stop", "continue"}:
        _error("Flow on_failure must be stop or continue")
    parameters = raw.get("parameters", {})
    if type(parameters) is not dict:
        _error("Flow parameters must be a mapping")
    definitions = {}
    for key, declaration in parameters.items():
        _string(key, "Flow parameter name")
        _mapping(declaration, {"initial"}, "Flow parameter declaration")
        if "initial" in declaration:
            _json(declaration["initial"], "Flow initial value")
        definitions[key] = FlowParameter("initial" in declaration, copy.deepcopy(declaration.get("initial")))
    calls = raw.get("scenarios")
    if type(calls) is not list or not calls or len(calls) > 100:
        _error("Flow scenarios must contain between 1 and 100 scheduled nodes")
    node_ids, targets = set(), set()
    for call in calls:
        _mapping(call, {"id", "scenario", "with_users"}, "Flow Scenario call")
        node_id = _string(call.get("id"), "Flow node id")
        target = _string(call.get("scenario"), "Flow Scenario target")
        if "/" in node_id or node_id in node_ids:
            _error("Flow node IDs must be unique and contain no slash")
        node_ids.add(node_id)
        targets.add(target)
    if len(targets) > 64:
        _error("Flow exceeds 64 distinct Scenario files")
    sidecar = file.with_suffix(".scenarios.json")
    if sidecar.is_symlink() or not sidecar.is_file():
        _error("Flow sidecar must be a regular local file, not a symlink")
    try:
        manifest_data = _read(sidecar, "Flow sidecar")
        manifest = json.loads(manifest_data.decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError):
        _error("invalid Flow sidecar JSON")
    _keys(manifest, {"manifest_version", "scenarios"}, "Flow sidecar")
    if type(manifest["manifest_version"]) is not int or manifest["manifest_version"] != 1:
        _error("Flow manifest_version must be integer 1")
    entries = manifest["scenarios"]
    if type(entries) is not dict or set(entries) != targets:
        _error("Flow sidecar targets must exactly match scheduled Scenarios")
    dependencies, paths = {}, set()
    for target, entry in entries.items():
        if type(entry) is not dict or set(entry) not in ({"path", "sha256"}, {"path", "sha256", "includes_sha256"}):
            _error("invalid Flow dependency entry fields")
        pin = _fingerprint(entry["sha256"])
        source = _safe_file(file.parent, entry["path"])
        canonical = source.resolve()
        if canonical == file.resolve() or canonical in paths:
            _error("Flow dependencies must be distinct and cannot alias the Flow")
        paths.add(canonical)
        source_data = _read(source, "Flow Scenario dependency")
        if hashlib.sha256(source_data).hexdigest() != pin:
            _error("Flow dependency fingerprint mismatch")
        source_raw = _decode_document(source_data)
        has_includes = (isinstance(source_raw, dict) and isinstance(source_raw.get("steps"), list)
                        and any(is_include(item) for item in source_raw["steps"]))
        if has_includes != ("includes_sha256" in entry):
            _error("Flow includes_sha256 is required exactly for scheduled Scenarios with includes")
        includes_pin = _fingerprint(entry["includes_sha256"]) if has_includes else None
        child_dependencies = load_dependencies(
            source, source_raw, _decode_document,
            lambda document, **context: _load_document(document, flow_keys=set(definitions), **context),
            expected_sidecar_hash=includes_pin)
        child = _load_document(source_raw, dependencies=child_dependencies, source_hash=pin,
                               flow_keys=set(definitions), allow_write_flow=True, source_path=source)
        if child.id != target:
            _error("Flow dependency Scenario ID does not match target")
        dependencies[target] = (child, copy.deepcopy(entry))
    compiled = _compile(flow_id, description, users, definitions, calls, dependencies, policy)
    try:
        snapshots.freeze(compiled.scenario)
    except ValueError as exc:
        _error(str(exc))
    return replace(compiled, source_pins={
        "flow_sha256": hashlib.sha256(data).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
        "scenarios": copy.deepcopy(compiled.dependencies)})
