"""Binding resolution and placeholder substitution.

This module has two responsibilities:

* `resolve_bindings(step, prior_norms)` reads a step's declared bindings and
  resolves them against prior steps' normalized response fields.
* `substitute(template, values)` applies those resolved values to a
  RequestTemplate.

Structural correctness is validated at load time by `loader.py`. This module
resolves runtime values and validates them at their use sites before an action.
Missing/null response bindings and invalid response-derived use sites block only
the consumer. Other runtime errors still stop execution; literals are never code.
"""

import copy
import re
import urllib.parse
from dataclasses import replace

from refracto.declaration.model import RequestTemplate, ValueRef, Assertion, Expect, RunUnique, StringConcat
from refracto.declaration.run_values import ensure_bound_run_values
from refracto.declaration import values as value_ops
from refracto.declaration import field_comparison
from refracto.declaration import numeric_comparison
from refracto.declaration.collections import is_scalar, resolve_matching
from refracto.query import wire_query, request_path
from refracto import headers as header_ops

_PLACEHOLDER_RE = re.compile(r"\{([^}]+)\}")


class DependencyUnavailable(Exception):
    """Only a response reference unavailable for its declared use; no raw values."""
    def __init__(self, message, sources):
        super().__init__(message)
        self.sources = list(dict.fromkeys(sources))


class MissingDependency(DependencyUnavailable, KeyError):
    pass


class InvalidDependency(DependencyUnavailable, ValueError):
    pass


def _require_data(value):
    """Mirror the loader's finite JSON-like domain without printing values."""
    try:
        field_comparison.require_data(value)
    except (ValueError, RecursionError):
        raise ValueError("resolved action value requires finite JSON-like data") from None


def _sources(node, inputs, by_key, active=None, _memo=None):
    """Follow typed dependencies only, preserving source steps through concat."""
    active = set() if active is None else active
    memo = {} if _memo is None else _memo
    if isinstance(node, ValueRef):
        if node.source == "bind":
            return [by_key[node.key]] if node.key in by_key else []
        if node.key in memo:
            return memo[node.key]
        if node.key in active or node.key not in inputs:
            return []
        active.add(node.key)
        try:
            memo[node.key] = _sources(inputs[node.key], inputs, by_key, active, memo)
            return memo[node.key]
        finally:
            active.remove(node.key)
    if isinstance(node, StringConcat):
        items = node.parts
    elif isinstance(node, (dict, list)):
        items = node.values() if isinstance(node, dict) else node
    else:
        return []
    return list(dict.fromkeys(source for item in items for source in _sources(item, inputs, by_key, active, memo)))


def resolve_bindings(step, prior_norms, *, inputs=None):
    """Return `{placeholder: value}` for every declared binding.

    Raises if a referenced prior step is missing, if the bound field is not
    present in that step's normalized fields, or if the resolved value is
    `None`. Falsy-but-present values remain valid.
    """
    values = {}
    source_by_key = {binding.placeholder: binding.from_step for binding in step.bind}
    input_values = {item.kind: item.value for item in inputs or []}
    for binding in step.bind:
        if binding.from_step not in prior_norms:
            raise MissingDependency(
                f"binding '{binding.placeholder}' refers to unknown prior step "
                f"'{binding.from_step}'", [binding.from_step]
            )
        norm = prior_norms[binding.from_step]
        if not isinstance(norm.fields, dict) or any(type(key) is not str for key in norm.fields):
            raise ValueError("normalized response fields must be a string-keyed mapping")
        if binding.field not in norm.fields:
            raise MissingDependency(
                f"binding '{binding.placeholder}' refers to field "
                f"'{binding.field}' not present in step '{binding.from_step}' "
                f"response", [binding.from_step]
            )
        value = norm.fields[binding.field]
        if binding.key is not None:
            if type(value) is not dict or any(type(key) is not str for key in value):
                raise InvalidDependency("response dictionary selection requires a string-keyed dictionary", [binding.from_step])
            if binding.key not in value:
                raise MissingDependency("response dictionary selection key is missing", [binding.from_step])
            value = value[binding.key]
        elif binding.matching is not None:
            if (type(value) is not list or any(type(member) is not dict
                    or any(type(key) is not str for key in member) for member in value)):
                raise InvalidDependency("response collection selection requires a list of string-keyed dictionaries", [binding.from_step])
            predicates = {}
            for key, declared in binding.matching.items():
                predicate_sources = _sources(declared, input_values, source_by_key)
                expected, error = value_ops.resolve(declared, bound_values=values, inputs=inputs)
                if isinstance(error, value_ops.ConcatOperandError):
                    predicate_sources = _sources(error.operand, input_values, source_by_key)
                if error is not None or not is_scalar(expected):
                    raise InvalidDependency("response collection predicate is unavailable or not a finite scalar",
                                            predicate_sources or [binding.from_step])
                predicates[key] = expected
            matches = [member for member in value if all(
                key in member and value_ops.equal(member[key], expected)
                for key, expected in predicates.items())]
            if len(matches) != 1:
                raise InvalidDependency("response collection selection requires exactly one matching member", [binding.from_step])
            if binding.member_field not in matches[0]:
                raise MissingDependency("response collection selected member field is missing", [binding.from_step])
            value = matches[0][binding.member_field]
        if value is None:
            raise InvalidDependency(
                f"binding '{binding.placeholder}' (from step "
                f"'{binding.from_step}', field '{binding.field}') binds "
                f"{binding.placeholder} to a null value", [binding.from_step]
            )
        try:
            _require_data(value)
        except ValueError:
            raise InvalidDependency("response-derived value requires finite JSON-like data",
                                    [binding.from_step]) from None
        # Each consumer owns its values; callbacks cannot rewrite the retained
        # prior observation through a response-derived container.
        values[binding.placeholder] = copy.deepcopy(value)
    return values


def _substitute_path(path, values):
    def replace(match):
        name = match.group(1)
        return urllib.parse.quote(str(values[name]), safe="")

    return _PLACEHOLDER_RE.sub(replace, path)


def _substitute_body(node, values):
    if isinstance(node, dict):
        return {key: _substitute_body(value, values) for key, value in node.items()}
    if isinstance(node, list):
        return [_substitute_body(item, values) for item in node]
    if isinstance(node, str):
        match = _PLACEHOLDER_RE.fullmatch(node)
        if match:
            return values[match.group(1)]
        return node
    return node


def substitute(template, values):
    """Return a new RequestTemplate with placeholders replaced.

    * Path placeholders are URL-encoded per segment.
    * A body scalar exactly equal to `{name}` is replaced by the raw value,
      preserving type.
    * Body dict values and list items are substituted recursively.
    * Body keys remain untouched.
    * The input template is not mutated.
    """
    new_path = _substitute_path(template.path, values)
    new_body = None if template.body is None else _substitute_body(template.body, values)
    return replace(template, path=new_path, body=new_body,
                   query=None if template.query is None else dict(template.query),
                   headers=None if template.headers is None else dict(template.headers))


def prepare_step(step, scenario, prior_norms):
    """Resolve the complete step atomically without interpreting literal strings.

    The returned diagnostics isolate their top-level mapping; nested values retain
    the existing shallow-copy semantics. No declaration assertion is invented.
    """
    ensure_bound_run_values(scenario)
    bound = resolve_bindings(step, prior_norms, inputs=scenario.inputs)
    by_key = {item.placeholder: item.from_step for item in step.bind}
    inputs = scenario.parameters

    def invalid(node, message):
        dependencies = _sources(node, inputs, by_key)
        if dependencies:
            raise InvalidDependency(message, dependencies)
        raise ValueError(message)

    def concrete(node):
        if isinstance(node, (ValueRef, StringConcat, RunUnique)):
            value, error = value_ops.resolve(node, bound_values=bound, inputs=scenario.inputs)
            if error:
                operand = error.operand if isinstance(error, value_ops.ConcatOperandError) else node
                invalid(operand, str(error))
            # Compiled include parameters may contain typed response references.
            # Literal dictionaries are never parsed as reference syntax here.
            if isinstance(node, ValueRef) and node.source == "input":
                return concrete(value)
            try:
                _require_data(value)
            except ValueError:
                invalid(node, "response-derived value requires finite JSON-like data")
            return copy.deepcopy(value)
        if isinstance(node, dict):
            return {key: concrete(value) for key, value in node.items()}
        if isinstance(node, list):
            return [concrete(value) for value in node]
        return node

    request = step.request
    if request is not None:
        if request.path_segments is not None:
            segments = [concrete(v) for v in request.path_segments]
            for original, resolved in zip(request.path_segments, segments):
                if type(resolved) not in (str, int) or resolved == "":
                    invalid(original, "resolved path segment must be a non-empty string or integer")
                if resolved in (".", ".."):
                    invalid(original, "resolved path must not contain a dot segment")
            path = "/".join(urllib.parse.quote(str(v), safe="") for v in segments)
        else:
            # Internal programmatic models can still use legacy placeholders;
            # the declaration loader never accepts that syntax.
            path = _substitute_path(request.path, bound)
        body = concrete(request.body) if request.path_segments is not None else _substitute_body(request.body, bound)
        if body is not None and not isinstance(body, dict):
            invalid(request.body, "resolved request body must be a mapping or null")
        _require_data(body)
        query = None if request.query is None else concrete(request.query)
        if query is not None:
            try:
                wire_query(query)
            except ValueError:
                invalid(request.query, "resolved query requires nonempty string keys and finite scalar values")
        request_path(path, {})
        headers = None if request.headers is None else concrete(request.headers)
        if headers is not None:
            try:
                header_ops.business_headers(headers)
            except ValueError:
                invalid(request.headers, "resolved business headers require valid names and bounded string values")
        request = replace(request, path=path, body=body,
                          declared_path=request.declared_path or request.path, query=query, headers=headers)
    expect = Expect(**{
        point: [Assertion(a.check, concrete(a.params)) for a in getattr(step.expect, point)]
        for point in ("frontend", "response", "backend_state")
    })
    for point in ("frontend", "response", "backend_state"):
        for original, assertion in zip(getattr(step.expect, point), getattr(expect, point)):
            if assertion.check == "header_equals":
                try:
                    header_ops.validate_value(assertion.params["value"])
                except ValueError:
                    invalid(original.params["value"], "resolved response header value must be a bounded string")
            for key in {"value", "id"} & set(assertion.params):
                if assertion.check in numeric_comparison.CHECKS and key == "value":
                    try:
                        numeric_comparison.require_expected(assertion.check, assertion.params[key])
                    except ValueError as exc:
                        invalid(original.params[key], str(exc))
                    continue
                if assertion.check in field_comparison.CHECKS and key == "value":
                    try:
                        field_comparison.require_data(assertion.params[key])
                    except (ValueError, RecursionError):
                        invalid(original.params[key], "resolved response comparison value must be finite JSON-like data")
                    continue
                if not is_scalar(assertion.params[key]):
                    invalid(original.params[key], "resolved assertion value/id must be a finite scalar")
            if assertion.check == "collection_matching_count":
                # Validate before actions or partial diagnostic bindings are
                # published by the projection's execution boundary.
                for key, value in assertion.params["matching"].items():
                    if not is_scalar(value):
                        invalid(original.params["matching"][key], "resolved collection matching value must be a finite scalar")
                resolve_matching(assertion.params["matching"])
    action_value = concrete(step.value)
    _require_data(action_value)
    prepared = replace(step, request=request, value=action_value, expect=expect)
    return prepared, bound
