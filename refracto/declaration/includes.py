"""One-level, pinned local composition into the existing execution model.

Only parsed ValueRef objects are substituted. Literal parameter dictionaries are
never parsed a second time, and runtime values are not read during compilation.
"""
import copy
import hashlib
import json
import re
from dataclasses import replace
from pathlib import PurePosixPath

from refracto.declaration.model import Assertion, Binding, Expect, ValueRef
from refracto.declaration.collections import is_scalar


def is_include(item):
    return isinstance(item, dict) and isinstance(item.get("do"), dict) and "include" in item["do"]


def _error(message):
    from refracto.declaration.loader import DeclarationError
    raise DeclarationError(message)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _error("duplicate include sidecar key")
        result[key] = value
    return result


def _keys(value, keys, context):
    if not isinstance(value, dict) or set(value) != set(keys):
        _error(f"invalid {context} fields")


def _safe_file(base, declared):
    if (not isinstance(declared, str) or not declared.strip()
            or any(c in declared for c in ("\x00", "\\", ":", "*", "?", "[", "]", "$", "~"))
            or declared.startswith("/") or ".." in declared.split("/")
            or any(not part or part == "." for part in declared.split("/"))):
        _error("dependency path must be a literal relative local path")
    try:
        path = base
        for part in PurePosixPath(declared).parts:
            path = path / part
            if path.is_symlink():
                _error("dependency symlink is forbidden")
        if not path.resolve().is_relative_to(base.resolve()) or not path.is_file():
            _error("dependency is not a regular file within the parent directory")
    except (OSError, ValueError) as exc:
        from refracto.declaration.loader import DeclarationError
        raise DeclarationError("invalid or inaccessible dependency path") from exc
    return path


def load_dependencies(parent, raw, decode, parse):
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
        return None
    calls = [item for item in raw["steps"] if is_include(item)]
    if not calls:
        return None
    targets = set()
    for call in calls:
        _keys(call["do"], {"include"}, "include action")
        target = call["do"]["include"]
        if not isinstance(target, str) or not target.strip():
            _error("include target must be a literal Scenario ID")
        if target == raw.get("scenario"):
            _error("self-inclusion is forbidden")
        targets.add(target)
    if len(targets) > 64:
        _error("composition exceeds 64 distinct child files")
    sidecar = parent.with_suffix(".includes.json")
    if sidecar.is_symlink() or not sidecar.is_file():
        _error("include sidecar must be a regular local file, not a symlink")
    try:
        manifest = json.loads(sidecar.read_bytes().decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, OSError) as exc:
        from refracto.declaration.loader import DeclarationError
        raise DeclarationError("invalid include sidecar JSON") from exc
    _keys(manifest, {"manifest_version", "scenarios"}, "include sidecar")
    if type(manifest["manifest_version"]) is not int or manifest["manifest_version"] != 1:
        _error("include manifest_version must be integer 1")
    entries = manifest["scenarios"]
    if not isinstance(entries, dict) or set(entries) != targets:
        _error("include sidecar targets must exactly match the parent includes")
    dependencies, paths = {}, set()
    for target, entry in entries.items():
        _keys(entry, {"path", "sha256"}, "dependency entry")
        pin = entry["sha256"]
        if not isinstance(pin, str) or not re.fullmatch("[0-9a-f]{64}", pin):
            _error("dependency fingerprint must be lowercase SHA-256")
        file = _safe_file(parent.parent, entry["path"])
        canonical = file.resolve()
        if canonical == parent.resolve() or canonical in paths:
            _error("dependency files must be distinct and cannot alias the parent")
        paths.add(canonical)
        try:
            data = file.read_bytes()
        except OSError as exc:
            from refracto.declaration.loader import DeclarationError
            raise DeclarationError("unable to read include dependency") from exc
        if hashlib.sha256(data).hexdigest() != pin:
            _error("dependency fingerprint mismatch")
        child_raw = decode(data)
        if isinstance(child_raw, dict) and isinstance(child_raw.get("steps"), list):
            if any(is_include(item) for item in child_raw["steps"]):
                _error("included Scenario must not include another Scenario")
        child = parse(child_raw)
        if child.id != target:
            _error("dependency Scenario ID does not match include target")
        if any("/" in step.id for step in child.steps):
            _error("included source step IDs must not contain slash")
        dependencies[target] = (child, pin, entry["path"])
    return dependencies


def _map(node, convert):
    if isinstance(node, ValueRef):
        return convert(node)
    if isinstance(node, dict):
        return {key: _map(value, convert) for key, value in node.items()}
    if isinstance(node, list):
        return [_map(value, convert) for value in node]
    return copy.deepcopy(node)


def instantiate(call, dependencies, parameters, prior, user, caller_parameters):
    from refracto.declaration.loader import _data, _mapping
    _mapping(call, {"id", "do", "with", "user"}, "include step")
    sid = call["id"]
    child, pin, _ = dependencies[call["do"]["include"]]
    if len(child.users) > 1:
        _error("including a multi-user Scenario is unsupported")
    if bool(child.users) != (user is not None):
        _error("anonymous and authenticated include users cannot be mixed")
    overrides = call.get("with", {})
    if not isinstance(overrides, dict) or set(overrides) - set(child.parameters):
        _error("include with must contain only declared child parameters")
    namespace, external = {}, []
    for index, (key, default) in enumerate(child.parameters.items()):
        generated = f"@include:{sid}:{index}"
        while generated in parameters:
            generated = "@" + generated
        if key in overrides:
            value = _data(overrides[key], caller_parameters, prior, external, "include with value")
            # Caller input values are already literal JSON data; do not revisit
            # their keys as declaration syntax during substitution.
            value = _map(value, lambda ref: copy.deepcopy(caller_parameters[ref.key])
                         if ref.source == "input" else ref)
        else:
            value = copy.deepcopy(default)
        parameters[generated] = value
        namespace[key] = generated
    external_bindings = {binding.placeholder: binding for binding in external}
    result, sources = [], {}
    for original in child.steps:
        rewritten = {}
        for binding in original.bind:
            source = f"{sid}/{binding.from_step}"
            key = f"{len(source)}:{source}:{binding.field}"
            rewritten[binding.placeholder] = Binding(key, source, binding.field)
        used = {}

        def visit_external(node):
            if isinstance(node, ValueRef):
                if node.source == "bind":
                    binding = external_bindings[node.key]
                    used[binding.placeholder] = binding
                elif node.source == "input":
                    visit_external(parameters[node.key])
            elif isinstance(node, dict):
                for value in node.values():
                    visit_external(value)
            elif isinstance(node, list):
                for value in node:
                    visit_external(value)

        def convert(ref):
            if ref.source == "input":
                key = namespace[ref.key]
                visit_external(parameters[key])
                if isinstance(parameters[key], ValueRef):
                    # Preserve the existing direct response reference model so
                    # offline contract comparison sees the same runtime source.
                    return parameters[key]
                return ValueRef("input", key)
            binding = rewritten[ref.key]
            used[binding.placeholder] = binding
            return ValueRef("bind", binding.placeholder)

        request = original.request
        if request is not None:
            segments = _map(request.path_segments, convert)
            from urllib.parse import quote
            path = "/".join("{" + v.source + ":" + v.key + "}" if isinstance(v, ValueRef)
                            else quote(str(v), safe="") for v in segments)
            request = replace(request, path=path, declared_path=path,
                              path_segments=segments, body=_map(request.body, convert))
        expect = Expect(**{point: [Assertion(a.check, _map(a.params, convert))
                                  for a in getattr(original.expect, point)]
                           for point in ("frontend", "response", "backend_state")})
        value = _map(original.value, convert)
        step = replace(original, id=f"{sid}/{original.id}", request=request,
                       expect=expect, value=value, bind=list(used.values()), user=user)
        result.append(step)
        sources[step.id] = {"scenario_id": child.id, "step_id": original.id,
                            "include_step_id": sid, "sha256": pin,
                            "source_user": original.user, "effective_user": user}
    return result, sources


def validate_instantiated(scenario):
    """Reject known invalid input values without evaluating response references."""
    unknown = object()
    parameters = scenario.parameters

    def known(node):
        if isinstance(node, ValueRef):
            return known(parameters[node.key]) if node.source == "input" else unknown
        if isinstance(node, dict):
            return {key: known(value) for key, value in node.items()}
        if isinstance(node, list):
            return [known(value) for value in node]
        return node

    for step in scenario.steps:
        if step.request is not None:
            for segment in step.request.path_segments:
                value = known(segment)
                if value is not unknown and (type(value) not in (str, int) or value == ""):
                    _error("instantiated path segment must be a non-empty string or integer")
            body = known(step.request.body)
            if body is not unknown and body is not None and not isinstance(body, dict):
                _error("instantiated request body must be a mapping")
        for point in ("frontend", "response", "backend_state"):
            for assertion in getattr(step.expect, point):
                for key in {"value", "id"} & set(assertion.params):
                    value = known(assertion.params[key])
                    if value is not unknown and isinstance(value, (list, dict)):
                        _error("instantiated assertion value must be scalar")
                if assertion.check == "collection_matching_count":
                    for declared in assertion.params["matching"].values():
                        value = known(declared)
                        if value is not unknown and not is_scalar(value):
                            _error("instantiated collection matching value must be a finite scalar")
