"""Binding resolution and placeholder substitution.

This module has two responsibilities:

* `resolve_bindings(step, prior_norms)` reads a step's declared bindings and
  resolves them against prior steps' normalized response fields.
* `substitute(template, values)` applies those resolved values to a
  RequestTemplate.

Structural correctness is validated at load time by `loader.py`. This module
therefore focuses on runtime value resolution and substitution. The remaining
runtime error case is a bound field resolving to `None`.
"""

import re
import urllib.parse
from dataclasses import replace

from refracto.declaration.model import RequestTemplate, ValueRef, Assertion, Expect
from refracto.declaration import values as value_ops
from refracto.declaration.collections import resolve_matching

_PLACEHOLDER_RE = re.compile(r"\{([^}]+)\}")


def resolve_bindings(step, prior_norms):
    """Return `{placeholder: value}` for every declared binding.

    Raises if a referenced prior step is missing, if the bound field is not
    present in that step's normalized fields, or if the resolved value is
    `None`. Falsy-but-present values remain valid.
    """
    values = {}
    for binding in step.bind:
        if binding.from_step not in prior_norms:
            raise KeyError(
                f"binding '{binding.placeholder}' refers to unknown prior step "
                f"'{binding.from_step}'"
            )
        norm = prior_norms[binding.from_step]
        if binding.field not in norm.fields:
            raise KeyError(
                f"binding '{binding.placeholder}' refers to field "
                f"'{binding.field}' not present in step '{binding.from_step}' "
                f"response"
            )
        value = norm.fields[binding.field]
        if value is None:
            raise ValueError(
                f"binding '{binding.placeholder}' (from step "
                f"'{binding.from_step}', field '{binding.field}') binds "
                f"{binding.placeholder} to a null value"
            )
        values[binding.placeholder] = value
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
    return RequestTemplate(method=template.method, path=new_path, body=new_body)


def prepare_step(step, scenario, prior_norms):
    """Resolve the complete step atomically without interpreting literal strings.

    The returned diagnostics isolate their top-level mapping; nested values retain
    the existing shallow-copy semantics. No declaration assertion is invented.
    """
    bound = resolve_bindings(step, prior_norms)

    def concrete(node):
        if isinstance(node, ValueRef):
            value, error = value_ops.resolve(node, bound_values=bound, inputs=scenario.inputs)
            if error:
                raise ValueError(error)
            return value
        if isinstance(node, dict):
            return {key: concrete(value) for key, value in node.items()}
        if isinstance(node, list):
            return [concrete(value) for value in node]
        return node

    request = step.request
    if request is not None:
        if request.path_segments is not None:
            segments = [concrete(v) for v in request.path_segments]
            if any(type(v) not in (str, int, bool) or v is None for v in segments):
                raise ValueError("response/parameter path segment is not a scalar")
            path = "/".join(urllib.parse.quote(str(v), safe="") for v in segments)
        else:
            # Internal programmatic models can still use legacy placeholders;
            # the declaration loader never accepts that syntax.
            path = _substitute_path(request.path, bound)
        body = concrete(request.body) if request.path_segments is not None else _substitute_body(request.body, bound)
        request = replace(request, path=path, body=body,
                          declared_path=request.declared_path or request.path)
    expect = Expect(**{
        point: [Assertion(a.check, concrete(a.params)) for a in getattr(step.expect, point)]
        for point in ("frontend", "response", "backend_state")
    })
    for assertion in expect.response:
        if assertion.check == "collection_matching_count":
            # Validate resolved references before any action or partial diagnostic
            # bindings are published by the projection's execution boundary.
            resolve_matching(assertion.params["matching"])
    prepared = replace(step, request=request, value=concrete(step.value), expect=expect)
    return prepared, bound
