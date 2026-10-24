"""Strict, data-only loader for the action-oriented Scenario format."""
import math
import numbers
import urllib.parse
import hashlib
import json
from pathlib import Path
import yaml
from refracto.declaration import vocabulary as vocab
from refracto.declaration import http_status
from refracto.declaration import field_comparison
from refracto.declaration import numeric_comparison
from refracto.declaration import values as value_ops
from refracto.declaration.collections import is_scalar
from refracto.query import wire_query
from refracto import headers as header_ops
from refracto.declaration.run_values import UNKNOWN, STRING, known_value, validate_parameters
from refracto.declaration.model import (
    Scenario, Grid, Input, Assertion, Expect, RequestTemplate, Binding,
    PollPolicy, Step, ValueRef, ResultSource, RunUnique, RunTime, StringConcat,
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
    def resolve(self, kind, value, implicit):
        tag = super().resolve(kind, value, implicit)
        if kind is yaml.ScalarNode and implicit[0]:
            numeric = tag in ("tag:yaml.org,2002:int", "tag:yaml.org,2002:float")
            digits = value.lstrip("+-").replace("_", "")
            ambiguous = (
                tag == "tag:yaml.org,2002:bool" and value.lower() not in ("true", "false")
                or numeric and ":" in value
                or tag == "tag:yaml.org,2002:int" and len(digits) > 1
                and digits.startswith("0") and digits.isdigit()
            )
            if ambiguous:
                raise DeclarationError(
                    "ambiguous implicit YAML scalar; quote text or use true/false and decimal numbers"
                )
        return tag

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
                raise DeclarationError("duplicate mapping key")
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


def _binding(bindings, source, field, *, key=None, matching=None, member_field=None):
    """Intern typed selectors without placing predicate data in report keys."""
    for binding in bindings:
        if (binding.from_step == source and binding.field == field
                and binding.key == key and binding.member_field == member_field
                and value_ops.equal(binding.matching, matching)):
            return binding
    def typed(node):
        if isinstance(node, ValueRef):
            return ["reference", node.source, node.key]
        if isinstance(node, StringConcat):
            return ["concat", [typed(part) for part in node.parts]]
        if type(node) is dict:
            return ["object", [[name, typed(item)] for name, item in sorted(node.items())]]
        return [type(node).__name__, node]

    identity = json.dumps([source, field, key, typed(matching), member_field],
                          ensure_ascii=True, separators=(",", ":"))
    placeholder = (f"{len(source)}:{source}:{field}" if key is None and matching is None
                   else "@member:" + hashlib.sha256(identity.encode("utf-8")).hexdigest())
    binding = Binding(placeholder, source, field, key=key, matching=matching, member_field=member_field)
    bindings.append(binding)
    return binding


def _reference(value, parameters, prior, bindings, where, *, selectors=True):
    if not isinstance(value, dict):
        return None
    if any(type(key) is str and key.startswith("from_")
           and key not in {"from_parameter", "from_step", "from_bind", "from_input"} for key in value):
        raise DeclarationError("unknown reference key in a declaration value")
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
            _mapping(value, {"from_step", "response_field", "key", "matching", "member_field"}, where)
            field = _string(value.get("response_field"), where)
            if source not in prior or prior[source].request is None:
                raise DeclarationError(f"{where}: response source must be an earlier request-bearing step")
        selection = set(value) & {"key", "matching", "member_field"}
        if selection and not selectors:
            raise DeclarationError("collection reference predicates cannot contain member selectors")
        if selection not in (set(), {"key"}, {"matching", "member_field"}):
            raise DeclarationError("response member reference requires either key or matching with member_field")
        key, matching, member_field = None, None, None
        if "key" in value:
            key = _string(value["key"], "response reference key")
        if "matching" in value:
            member_field = _string(value["member_field"], "response reference member_field")
            if type(value["matching"]) is not dict or not value["matching"]:
                raise DeclarationError("response reference matching must be a nonempty mapping")
            matching = {}
            for name, declared in value["matching"].items():
                _string(name, "response reference matching key")
                predicate = _value(declared, parameters, prior, bindings, where, selectors=False)
                if predicate is None:
                    if not is_scalar(declared):
                        raise DeclarationError("response reference matching value must be a finite scalar or plain reference")
                    predicate = declared
                elif not _scalar_known(predicate, parameters):
                    raise DeclarationError("response reference matching parameter must be a finite scalar")
                matching[name] = predicate
        binding = _binding(bindings, source, field, key=key, matching=matching, member_field=member_field)
        return ValueRef("bind", binding.placeholder)
    if set(value) & {"from_bind", "from_input"}:
        raise DeclarationError(f"{where}: old reference syntax is unsupported")
    return None


def _known(value, parameters):
    try:
        return known_value(value, parameters)
    except (ValueError, RecursionError):
        raise DeclarationError("invalid parameter dependency or concat operand") from None


def _scalar_known(value, parameters):
    known = _known(value, parameters)
    return known is UNKNOWN or known is STRING or is_scalar(known)


def _concat(raw, parameters, prior, bindings, where, *, selectors=True, validate=True):
    _mapping(raw, {"concat"}, where)
    parts = raw["concat"]
    if type(parts) is not list or not parts:
        raise DeclarationError("concat requires a nonempty list")
    parsed = []
    for part in parts:
        if type(part) is str:
            parsed.append(part)
            continue
        ref = _reference(part, parameters, prior, bindings, where, selectors=selectors)
        if ref is None:
            raise DeclarationError("concat operands must be strings or references; nested concat is unsupported")
        parsed.append(ref)
    result = StringConcat(tuple(parsed))
    if validate:
        _known(result, parameters)
    return result


def _value(value, parameters, prior, bindings, where, *, selectors=True):
    ref = _reference(value, parameters, prior, bindings, where, selectors=selectors)
    if ref is not None:
        return ref
    if isinstance(value, dict) and "concat" in value:
        return _concat(value, parameters, prior, bindings, where, selectors=selectors)
    return None


def _data(value, parameters, prior, bindings, where):
    ref = _value(value, parameters, prior, bindings, where)
    if ref is not None:
        return ref
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise DeclarationError(f"{where} requires string-keyed objects")
        return {k: _data(v, parameters, prior, bindings, where) for k, v in value.items()}
    if isinstance(value, list):
        return [_data(v, parameters, prior, bindings, where) for v in value]
    _json(value, where)
    return value


def _header_value(declared, parameters, prior, bindings, where):
    value = _value(declared, parameters, prior, bindings, where)
    if value is None:
        value = declared
    known = _known(value, parameters)
    if known is not UNKNOWN and known is not STRING:
        try:
            header_ops.validate_value(known)
        except ValueError as exc:
            raise DeclarationError(str(exc)) from None
    return value


def _request(raw, parameters, prior, bindings, where):
    _mapping(raw, {"method", "path", "body", "query", "headers"}, where)
    method = _string(raw.get("method"), f"{where}.method").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise DeclarationError(f"{where}: unsupported HTTP method")
    path = raw.get("path")
    if not isinstance(path, list) or not path:
        raise DeclarationError(f"{where}.path must be a non-empty list of segments")
    segments = [_data(v, parameters, prior, bindings, f"{where}.path") for v in path]
    for v in segments:
        if not isinstance(v, (ValueRef, StringConcat)) and (type(v) not in (str, int) or v == ""):
            raise DeclarationError(f"{where}.path segments must be non-empty strings, integers, or references")
        known = _known(v, parameters)
        if known is not UNKNOWN and known is not STRING and (type(known) not in (str, int) or known == ""):
            raise DeclarationError("request path segment must be a non-empty string or integer")
        if type(known) is str and known in (".", ".."):
            raise DeclarationError("request path must not contain a dot segment")
    template_path = "/".join(
        "{" + v.source + ":" + v.key + "}" if isinstance(v, ValueRef)
        else "{concat:" + str(index) + "}" if isinstance(v, StringConcat)
        else urllib.parse.quote(str(v), safe="") for index, v in enumerate(segments))
    body = raw.get("body")
    if body is not None and not isinstance(body, dict):
        raise DeclarationError(f"{where}.body must be a mapping")
    body = _data(body, parameters, prior, bindings, f"{where}.body")
    body_known = _known(body, parameters)
    if body_known is not UNKNOWN and body_known is not None and not isinstance(body_known, dict):
        raise DeclarationError("request body must resolve to a mapping")
    query = None
    if "query" in raw:
        if type(raw["query"]) is not dict:
            raise DeclarationError(f"{where}.query must be a mapping")
        query = {}
        for key, declared in raw["query"].items():
            if type(key) is not str or not key:
                raise DeclarationError("query keys must be nonempty literal strings")
            value = _value(declared, parameters, prior, bindings, f"{where}.query value")
            if value is None:
                value = declared
            known = _known(value, parameters)
            if known is not UNKNOWN and known is not STRING:
                try:
                    wire_query({key: known})
                except ValueError as exc:
                    raise DeclarationError(str(exc)) from None
            query[key] = value
    headers = None
    if "headers" in raw:
        if type(raw["headers"]) is not dict:
            raise DeclarationError("request headers must be a mapping")
        headers, names = {}, set()
        for name, declared in raw["headers"].items():
            try:
                folded = header_ops.validate_name(name, business=True)
            except ValueError as exc:
                raise DeclarationError(str(exc)) from None
            if folded in names:
                raise DeclarationError("duplicate case-insensitive header name")
            names.add(folded)
            headers[name] = _header_value(declared, parameters, prior, bindings, "request header value")
    return RequestTemplate(method, template_path, body, path_segments=segments,
                           declared_path=template_path, query=query, headers=headers)


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
        if check in header_ops.CHECKS:
            try:
                header_ops.validate_name(params["header"])
            except ValueError as exc:
                raise DeclarationError(str(exc)) from None
            if check == "header_equals":
                params["value"] = _header_value(params["value"], parameters, prior, bindings,
                                                "response header value")
        if check == "status_equals" and not http_status.valid(params["value"]):
            raise DeclarationError("status_equals.value must be a literal integer from 100 through 599")
        if check == "status_in":
            statuses = params["values"]
            if (not isinstance(statuses, list) or not statuses
                    or not all(http_status.valid(value) for value in statuses)
                    or len(statuses) != len(set(statuses))):
                raise DeclarationError("status_in.values must be a nonempty list of distinct literal integers from 100 through 599")
        for key in set(params) & {"anchor", "field", "span", "attr"}:
            _string(params[key], f"{point}.{check}.{key}")
        if check in numeric_comparison.CHECKS:
            value = _value(params["value"], parameters, prior, bindings,
                               f"{point}.{check}.value")
            if value is None:
                value = params["value"]
            known = _known(value, parameters)
            try:
                numeric_comparison.require_operator(params["op"])
                if known is not UNKNOWN:
                    numeric_comparison.require_expected(check, known)
            except ValueError as exc:
                raise DeclarationError(str(exc)) from None
            params["value"] = value
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
                value = _value(declared, parameters, prior, bindings, "collection matching value")
                if value is None:
                    if not is_scalar(declared):
                        raise DeclarationError("collection matching value must be a finite scalar or reference")
                    value = declared
                elif not _scalar_known(value, parameters):
                    raise DeclarationError("collection matching parameter must be a finite scalar")
                resolved[key] = value
            params["matching"] = resolved
        for key in set(params) & {"value", "id"}:
            if check == "header_equals" or check in numeric_comparison.CHECKS:
                continue
            value = _data(params[key], parameters, prior, bindings, f"{point}.{check}.{key}")
            if (check not in field_comparison.CHECKS and not isinstance(value, ValueRef)
                    and isinstance(value, (list, dict))):
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
    headers = [a.params["header"].lower() for a in assertions if a.check in header_ops.CHECKS]
    if len(headers) != len(set(headers)):
        raise DeclarationError("duplicate or contradictory response header constraint")
    if sum(a.check in http_status.CHECKS for a in assertions) > 1:
        raise DeclarationError("at most one HTTP status constraint is allowed per step")
    if {"success", "failure"} <= checks:
        raise DeclarationError("response success and failure are mutually exclusive")
    for check in ("field_equals", "field_not_equals", "field_absent"):
        fields = [a.params["field"] for a in assertions if a.check == check]
        if len(fields) != len(set(fields)):
            raise DeclarationError(f"duplicate {check} constraint")
    numeric = [(a.check, a.params["field"], a.params["op"])
               for a in assertions if a.check in numeric_comparison.CHECKS]
    if len(numeric) != len(set(numeric)):
        raise DeclarationError("duplicate response numeric comparison constraint")
    required = {a.params["field"] for a in assertions
                if a.check in ("has", "field_equals", "field_not_equals", "collection_matching_count")
                or a.check in numeric_comparison.CHECKS}
    forbidden = {a.params["field"] for a in assertions if a.check == "field_absent"}
    if required & forbidden:
        raise DeclarationError("field_absent conflicts with a response presence constraint")


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
    _mapping(raw, {"schema_version", "scenario", "description", "users", "parameters", "grid", "steps", "results"}, "top-level")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise DeclarationError("schema_version must be integer 1; old declarations are unsupported")
    scenario_id = _string(raw.get("scenario"), "scenario")
    users = raw.get("users")
    if (type(users) is not list or any(type(user) is not str or not user.strip() for user in users)
            or len(set(users)) != len(users)):
        raise DeclarationError("users must be a list of distinct non-empty literal names")
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
    for key, value in parameters.items():
        if type(value) is dict and "from_run" in value:
            if set(value) == {"from_run"} and value["from_run"] == "unique":
                parameters[key] = RunUnique()
            elif value["from_run"] == "time" and set(value) <= {"from_run", "offset"}:
                if "offset" not in value:
                    parameters[key] = RunTime()
                else:
                    offset = value["offset"]
                    if (type(offset) is not dict or len(offset) != 1
                            or next(iter(offset)) not in {"days", "hours", "minutes", "seconds"}
                            or type(next(iter(offset.values()))) is not int):
                        raise DeclarationError("time offset requires one supported unit and a strict integer")
                    parameters[key] = RunTime(*next(iter(offset.items())))
            else:
                raise DeclarationError("run parameter requires unique or time with an optional bounded offset")
        elif type(value) is dict and "concat" in value:
            parameters[key] = _concat(value, parameters, {}, [], "parameter concat", validate=False)
    try:
        validate_parameters(parameters)
    except (ValueError, RecursionError):
        raise DeclarationError("invalid parameter dependency or concat operand") from None
    declared_parameters = dict(parameters)
    grid = None
    if "grid" in raw:
        g = _mapping(raw["grid"], {"level", "module"}, "grid")
        grid = Grid(_string(g.get("level"), "grid.level"), _string(g.get("module"), "grid.module"))
    if not isinstance(raw.get("steps"), list) or not raw["steps"]:
        raise DeclarationError("steps must be a non-empty list")
    steps, prior, assertion_count = [], _ReferenceScope(), 0
    execution_ids = set()
    source_lookup, source_ids, include_user_mappings, reference_bindings = {}, set(), {}, {}
    for item in raw["steps"]:
        if dependencies is not None:
            from refracto.declaration.includes import instantiate, is_include, participant_mapping
            sid = _string(item.get("id"), "step.id") if isinstance(item, dict) else None
            if sid is None or "/" in sid or sid in source_ids:
                raise DeclarationError("composition source step IDs must be unique and contain no slash")
            source_ids.add(sid)
            if is_include(item):
                child = dependencies[item["do"]["include"]][0]
                mapping = participant_mapping(item, child.users, users)
                expanded, sources = instantiate(item, dependencies, parameters, prior, mapping,
                                                declared_parameters, implicit_anonymous=not users,
                                                reference_bindings=reference_bindings)
                include_user_mappings[sid] = dict(mapping)
                for step in expanded:
                    if step.id in execution_ids:
                        raise DeclarationError("expanded step ID collision")
                    steps.append(step)
                    execution_ids.add(step.id)
                    assertion_count += int(step.request_asserted) + len(step.expect.frontend) + len(step.expect.response) + len(step.expect.backend_state)
                source_lookup.update(sources)
                prior.include_results[sid] = {
                    name: ResultSource(f"{sid}/{alias.from_step}", alias.response_field)
                    for name, alias in child.results.items()}
                if len(steps) > 1000:
                    raise DeclarationError("composition exceeds 1000 expanded leaves")
                continue
        user = _step_user(item, users)
        _mapping(item, {"id", "do", "target", "value", "duration", "expect", "poll", "on_failure", "user", "session"}, "step")
        if "session" in item and (type(item["session"]) is not str or item["session"] != "new"):
            raise DeclarationError("session must be the literal string new; omit it to reuse")
        if "on_failure" in item and (type(item["on_failure"]) is not str or item["on_failure"] != "stop"):
            raise DeclarationError("on_failure must be the literal string stop; omit it to continue")
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
        step = Step(sid, request, expect, bindings, poll, action, target, value, duration, request_asserted,
                    on_failure=item.get("on_failure", "continue"), user=user, session=item.get("session"))
        steps.append(step)
        reference_bindings.update({binding.placeholder: binding for binding in bindings})
        execution_ids.add(sid)
        prior[sid] = step
        if source_hash is not None:
            source_lookup[sid] = {"scenario_id": scenario_id, "step_id": sid,
                                  "include_step_id": None, "sha256": source_hash,
                                  "source_user": user, "effective_user": user}
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
    result = Scenario(scenario_id, grid, "", [], [Input(k, v) for k, v in parameters.items()], description, steps,
                      source_lookup=source_lookup,
                      include_dependencies={key: {"path": value[2], "sha256": value[1]}
                                            for key, value in (dependencies or {}).items()},
                      results=aliases, included_results=prior.include_results, users=list(users),
                      include_user_mappings=include_user_mappings, reference_bindings=reference_bindings)
    if dependencies is not None:
        from refracto.declaration.includes import validate_instantiated
        if len(steps) > 1000:
            raise DeclarationError("composition exceeds 1000 expanded leaves")
        validate_instantiated(result)
    return result


def _step_user(item, users):
    if not isinstance(item, dict):
        raise DeclarationError("step must be a mapping")
    if not users:
        if "user" in item or "session" in item:
            raise DeclarationError("anonymous steps must omit user and session")
        return None
    if "user" not in item:
        if len(users) > 1:
            raise DeclarationError("every step in a multi-user Scenario must declare user")
        user = users[0]
    else:
        user = item["user"]
    if type(user) is not str or user not in users:
        raise DeclarationError("step.user must name a declared user")
    if user == "anonymous" and "session" in item:
        raise DeclarationError("anonymous steps must omit session")
    return user
