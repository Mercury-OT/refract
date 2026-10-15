"""Strict, data-only loader for the action-oriented Scenario format."""
import math
import numbers
import urllib.parse
import hashlib
from pathlib import Path
import yaml
from refracto.declaration import vocabulary as vocab
from refracto.declaration.collections import is_scalar
from refracto.declaration.model import (
    Scenario, Grid, Input, Assertion, Expect, RequestTemplate, Binding,
    PollPolicy, Step, ValueRef, ResultSource,
)


class DeclarationError(Exception):
    pass


class _ReferenceScope(dict):
    """Authored local steps and explicitly exported prior include interfaces.

    Expanded leaves are deliberately absent: declarations cannot bypass a
    child's public result names by addressing its internal qualified step IDs.
    """
    def __init__(self):
        super().__init__()
        self.include_results = {}


class _Loader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise DeclarationError("YAML aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise DeclarationError("mapping keys must be strings")
            if key in result:
                raise DeclarationError(f"duplicate mapping key {key!r}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _mapping(raw, allowed, where):
    if not isinstance(raw, dict):
        raise DeclarationError(f"{where} must be a mapping")
    extra = set(raw) - set(allowed)
    if extra:
        raise DeclarationError(f"{where}: unknown field(s) {sorted(extra)}")
    return raw


def _string(value, where):
    if not isinstance(value, str) or not value.strip():
        raise DeclarationError(f"{where} must be a non-empty string")
    return value


def _json(value, where):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json(item, where)
        return
    if isinstance(value, dict) and all(type(k) is str for k in value):
        for item in value.values():
            _json(item, where)
        return
    raise DeclarationError(f"{where} requires finite JSON-like data")


def _reference(value, parameters, prior, bindings, where):
    if not isinstance(value, dict):
        return None
    if "from_parameter" in value:
        _mapping(value, {"from_parameter"}, where)
        key = _string(value["from_parameter"], where)
        if key not in parameters:
            raise DeclarationError(f"{where}: unknown parameter {key!r}")
        return ValueRef("input", key)
    if "from_step" in value or "response_field" in value:
        source = _string(value.get("from_step"), where)
        if "result" in value:
            _mapping(value, {"from_step", "result"}, where)
            name = _string(value["result"], where)
            aliases = getattr(prior, "include_results", {}).get(source)
            if aliases is None or name not in aliases:
                raise DeclarationError(f"{where}: result source must name an earlier include's declared result")
            alias = aliases[name]
            source, field = alias.from_step, alias.response_field
        else:
            _mapping(value, {"from_step", "response_field"}, where)
            field = _string(value.get("response_field"), where)
            if source not in prior or prior[source].request is None:
                raise DeclarationError(f"{where}: response source must be an earlier request-bearing step")
        # Length-prefix the source so dots/colons in identifiers cannot alias.
        key = f"{len(source)}:{source}:{field}"
        if not any(b.placeholder == key for b in bindings):
            bindings.append(Binding(key, source, field))
        return ValueRef("bind", key)
    if set(value) & {"from_bind", "from_input"}:
        raise DeclarationError(f"{where}: old reference syntax is unsupported")
    return None


def _data(value, parameters, prior, bindings, where):
    ref = _reference(value, parameters, prior, bindings, where)
    if ref is not None:
        return ref
    if isinstance(value, dict):
        return {k: _data(v, parameters, prior, bindings, where) for k, v in value.items()}
    if isinstance(value, list):
        return [_data(v, parameters, prior, bindings, where) for v in value]
    _json(value, where)
    return value


def _request(raw, parameters, prior, bindings, where):
    _mapping(raw, {"method", "path", "body"}, where)
    method = _string(raw.get("method"), f"{where}.method").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise DeclarationError(f"{where}: unsupported HTTP method")
    path = raw.get("path")
    if not isinstance(path, list) or not path:
        raise DeclarationError(f"{where}.path must be a non-empty list of segments")
    segments = [_data(v, parameters, prior, bindings, f"{where}.path") for v in path]
    for v in segments:
        if not isinstance(v, ValueRef) and (type(v) not in (str, int) or v == ""):
            raise DeclarationError(f"{where}.path segments must be non-empty strings, integers, or references")
    template_path = "/".join(
        "{" + v.source + ":" + v.key + "}" if isinstance(v, ValueRef)
        else urllib.parse.quote(str(v), safe="") for v in segments)
    body = raw.get("body")
    if body is not None and not isinstance(body, dict):
        raise DeclarationError(f"{where}.body must be a mapping")
    body = _data(body, parameters, prior, bindings, f"{where}.body")
    return RequestTemplate(method, template_path, body, path_segments=segments,
                           declared_path=template_path)


def _assertions(point, raw, parameters, prior, bindings):
    if not isinstance(raw, list):
        raise DeclarationError(f"expect.{point} must be a list")
    out = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("check"), str):
            raise DeclarationError(f"{point}: each assertion must be a mapping with a 'check' key")
        check = item["check"]
        if not vocab.is_valid(point, check):
            raise DeclarationError(f"{point}: unknown/invalid check {check!r}")
        required = vocab.required_params(point, check)
        _mapping(item, {"check", *required, *vocab.optional_params(point, check)}, f"{point}.{check}")
        missing = set(required) - set(item)
        if missing:
            raise DeclarationError(f"{point}.{check}: missing required param {sorted(missing)}")
        params = {k: v for k, v in item.items() if k != "check"}
        for key in set(params) & {"anchor", "field", "span", "attr"}:
            _string(params[key], f"{point}.{check}.{key}")
        if check in {"objects_matching_count", "collection_matching_count", "count_gt"}:
            count = params["count"]
            if check != "count_gt" and (type(count) is not int or count < 0):
                raise DeclarationError(f"{check}.count must be a non-negative integer")
            if check == "count_gt" and (isinstance(count, bool) or not isinstance(count, numbers.Real) or not math.isfinite(count)):
                raise DeclarationError("count_gt.count must be a finite number")
        if check == "collection_matching_count":
            matching = params["matching"]
            if not isinstance(matching, dict) or not matching:
                raise DeclarationError("collection_matching_count.matching must be a non-empty mapping")
            resolved = {}
            for key, declared in matching.items():
                _string(key, "collection matching key")
                value = _reference(declared, parameters, prior, bindings, "collection matching value")
                if value is None:
                    if not is_scalar(declared):
                        raise DeclarationError("collection matching value must be a finite scalar or reference")
                    value = declared
                elif value.source == "input" and not is_scalar(parameters[value.key]):
                    raise DeclarationError("collection matching parameter must be a finite scalar")
                resolved[key] = value
            params["matching"] = resolved
        for key in set(params) & {"value", "id"}:
            value = _data(params[key], parameters, prior, bindings, f"{point}.{check}.{key}")
            if not isinstance(value, ValueRef) and isinstance(value, (list, dict)):
                raise DeclarationError(f"{point}.{check}.{key} must be scalar or a reference")
            if key == "id" and not isinstance(value, ValueRef):
                raise DeclarationError("object_field_equals.id must be a value reference")
            params[key] = value
        if check == "span_attr":
            op, value = params["op"], params["value"]
            if op not in vocab.COMPARISON_OPS:
                raise DeclarationError("span_attr.op is unsupported")
            if isinstance(value, ValueRef) and op != "==":
                raise DeclarationError("span_attr reference requires equality")
            if op in vocab.ORDERING_OPS and (isinstance(value, bool) or not isinstance(value, numbers.Real)):
                raise DeclarationError("span_attr ordering requires a numeric value")
        out.append(Assertion(check, params))
    return out


def _response_constraints(assertions):
    checks = {a.check for a in assertions}
    if {"success", "failure"} <= checks:
        raise DeclarationError("response success and failure are mutually exclusive")
    for check in ("field_equals", "field_absent"):
        fields = [a.params["field"] for a in assertions if a.check == check]
        if len(fields) != len(set(fields)):
            raise DeclarationError(f"duplicate {check} constraint")
    required = {a.params["field"] for a in assertions
                if a.check in ("has", "field_equals", "collection_matching_count")}
    forbidden = {a.params["field"] for a in assertions if a.check == "field_absent"}
    if required & forbidden:
        raise DeclarationError("field_absent conflicts with has/field_equals/collection_matching_count")


def _decode_document(data):
    try:
        return yaml.load(data.decode("utf-8"), Loader=_Loader)
    except (yaml.YAMLError, UnicodeError) as exc:
        # Parser diagnostics can echo source lines containing sensitive values.
        raise DeclarationError("invalid YAML or UTF-8 declaration") from exc


def load_scenario(path: str) -> Scenario:
    from refracto.declaration.includes import load_dependencies
    file = Path(path)
    data = file.read_bytes()
    raw = _decode_document(data)
    dependencies = load_dependencies(file, raw, _decode_document, _load_document)
    return _load_document(raw, dependencies=dependencies,
                          source_hash=hashlib.sha256(data).hexdigest())


def _load_document(raw, *, dependencies=None, source_hash=None) -> Scenario:
    _mapping(raw, {"schema_version", "scenario", "description", "actor", "parameters", "grid", "steps", "results"}, "top-level")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise DeclarationError("schema_version must be integer 1; old declarations are unsupported")
    scenario_id = _string(raw.get("scenario"), "scenario")
    actor = _string(raw.get("actor"), "actor")
    description = raw.get("description", "")
    if not isinstance(description, str):
        raise DeclarationError("description must be a string")
    parameters = raw.get("parameters", {})
    if not isinstance(parameters, dict):
        raise DeclarationError("parameters must be a unique-key mapping")
    for key, value in parameters.items():
        _string(key, "parameter key")
        _json(value, "parameter")
    parameters = dict(parameters)
    declared_parameters = dict(parameters)
    grid = None
    if "grid" in raw:
        g = _mapping(raw["grid"], {"level", "module"}, "grid")
        grid = Grid(_string(g.get("level"), "grid.level"), _string(g.get("module"), "grid.module"))
    if not isinstance(raw.get("steps"), list) or not raw["steps"]:
        raise DeclarationError("steps must be a non-empty list")
    steps, prior, assertion_count = [], _ReferenceScope(), 0
    execution_ids = set()
    source_lookup, source_ids = {}, set()
    for item in raw["steps"]:
        if dependencies is not None:
            from refracto.declaration.includes import instantiate, is_include
            sid = _string(item.get("id"), "step.id") if isinstance(item, dict) else None
            if sid is None or "/" in sid or sid in source_ids:
                raise DeclarationError("composition source step IDs must be unique and contain no slash")
            source_ids.add(sid)
            if is_include(item):
                expanded, sources = instantiate(item, dependencies, parameters, prior, actor,
                                                declared_parameters)
                for step in expanded:
                    if step.id in execution_ids:
                        raise DeclarationError("expanded step ID collision")
                    steps.append(step)
                    execution_ids.add(step.id)
                    assertion_count += int(step.request_asserted) + len(step.expect.frontend) + len(step.expect.response) + len(step.expect.backend_state)
                source_lookup.update(sources)
                child = dependencies[item["do"]["include"]][0]
                prior.include_results[sid] = {
                    name: ResultSource(f"{sid}/{alias.from_step}", alias.response_field)
                    for name, alias in child.results.items()}
                if len(steps) > 1000:
                    raise DeclarationError("composition exceeds 1000 expanded leaves")
                continue
        _mapping(item, {"id", "do", "target", "value", "duration", "expect", "poll"}, "step")
        sid = _string(item.get("id"), "step.id")
        if sid in execution_ids:
            raise DeclarationError(f"step id {sid!r} is duplicated")
        bindings = []
        action = item.get("do")
        request = None
        if isinstance(action, dict):
            _mapping(action, {"request"}, "do")
            if set(action) != {"request"}:
                raise DeclarationError("do mapping must contain only request")
            request = _request(action["request"], declared_parameters, prior, bindings, "do.request")
            action = "request"
        elif action not in ("open", "click", "fill", "wait"):
            raise DeclarationError("do must be open/click/fill/wait or a request mapping")
        allowed = {"target"} if action in ("open", "click") else {"target", "value"} if action == "fill" else {"duration"} if action == "wait" else set()
        if ((set(item) & {"target", "value", "duration"}) - allowed) or not allowed <= set(item):
            raise DeclarationError(f"{action}: wrong action fields; required {sorted(allowed)}")
        target = _string(item["target"], "target") if "target" in item else None
        value = _data(item.get("value"), declared_parameters, prior, bindings, "value")
        duration = item.get("duration")
        if action == "wait" and (type(duration) is not int or duration < 0):
            raise DeclarationError("duration must be a non-negative integer in milliseconds")
        exp = _mapping(item.get("expect", {}), {"request", "ui", "response", "backend_state"}, "expect")
        request_asserted = "request" in exp
        if request_asserted:
            if action == "request":
                raise DeclarationError("do.request must not also declare expect.request")
            if action == "wait":
                raise DeclarationError("wait has no action/request correlation; expect.request is unsupported")
            request = _request(exp["request"], declared_parameters, prior, bindings, "expect.request")
        expect = Expect(
            frontend=_assertions("frontend", exp.get("ui", []), declared_parameters, prior, bindings),
            response=_assertions("response", exp.get("response", []), declared_parameters, prior, bindings),
            backend_state=_assertions("backend_state", exp.get("backend_state", []), declared_parameters, prior, bindings),
        )
        _response_constraints(expect.response)
        if expect.response and request is None:
            raise DeclarationError("response assertions require a declared request")
        poll = None
        if "poll" in item:
            p = _mapping(item["poll"], {"on_timeout"}, "poll")
            if action != "request" or request.method != "GET" or not expect.response:
                raise DeclarationError("poll requires do.request GET and response stop assertions")
            policy = p.get("on_timeout", "FAIL")
            if policy not in vocab.POLL_ON_TIMEOUT:
                raise DeclarationError("poll.on_timeout must be FAIL or SKIP")
            poll = PollPolicy(policy)
        step = Step(sid, request, expect, bindings, poll, action, target, value, duration, request_asserted)
        steps.append(step)
        execution_ids.add(sid)
        prior[sid] = step
        if source_hash is not None:
            source_lookup[sid] = {"scenario_id": scenario_id, "step_id": sid,
                                  "include_step_id": None, "sha256": source_hash}
        assertion_count += int(request_asserted) + len(expect.frontend) + len(expect.response) + len(expect.backend_state)
    if not assertion_count:
        raise DeclarationError("Scenario must contain at least one effective assertion")
    results = raw.get("results", {})
    if not isinstance(results, dict):
        raise DeclarationError("results must be a unique-key mapping")
    aliases = {}
    for name, alias in results.items():
        _string(name, "result name")
        _mapping(alias, {"from_step", "response_field"}, "result source")
        source = _string(alias.get("from_step"), "result source.from_step")
        field = _string(alias.get("response_field"), "result source.response_field")
        if source not in prior or prior[source].request is None:
            raise DeclarationError("result source must be an authored local request-bearing step")
        aliases[name] = ResultSource(source, field)
    result = Scenario(scenario_id, grid, actor, [], [Input(k, v) for k, v in parameters.items()], description, steps,
                      source_lookup=source_lookup,
                      include_dependencies={key: {"path": value[2], "sha256": value[1]}
                                            for key, value in (dependencies or {}).items()},
                      results=aliases, included_results=prior.include_results)
    if dependencies is not None:
        from refracto.declaration.includes import validate_instantiated
        if len(steps) > 1000:
            raise DeclarationError("composition exceeds 1000 expanded leaves")
        validate_instantiated(result)
    return result
