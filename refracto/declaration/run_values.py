"""Symbolic parameter analysis and explicit, isolated run-value freezing."""
import copy
from dataclasses import replace
from uuid import uuid4

from refracto.declaration.model import Input, RunUnique, StringConcat, ValueRef


UNKNOWN = object()
STRING = object()


def known_value(node, parameters, active=None, _memo=None):
    """Inspect typed declarations without randomness or interpreting dictionaries.

    STRING means a string whose content depends on this run or a response;
    UNKNOWN means a response value whose type is not yet known.
    """
    active = set() if active is None else active
    memo = {} if _memo is None else _memo
    if isinstance(node, ValueRef):
        if node.source != "input":
            return UNKNOWN
        if node.key not in parameters:
            raise ValueError("unknown parameter dependency")
        if node.key in memo:
            return memo[node.key]
        if node.key in active:
            raise ValueError("cyclic parameter dependency")
        active.add(node.key)
        try:
            memo[node.key] = known_value(parameters[node.key], parameters, active, memo)
            return memo[node.key]
        finally:
            active.remove(node.key)
    if isinstance(node, RunUnique):
        return STRING
    if isinstance(node, StringConcat):
        parts = [known_value(part, parameters, active, memo) for part in node.parts]
        if any(type(part) is not str and part is not STRING and part is not UNKNOWN for part in parts):
            raise ValueError("concat operands must resolve to strings")
        return STRING if any(part is STRING or part is UNKNOWN for part in parts) else "".join(parts)
    return node


def validate_parameters(parameters):
    memo = {}
    for name in parameters:
        known_value(ValueRef("input", name), parameters, _memo=memo)


def _has_unique(node):
    if isinstance(node, RunUnique):
        return True
    if isinstance(node, StringConcat):
        return any(_has_unique(part) for part in node.parts)
    if isinstance(node, dict):
        return any(_has_unique(value) for value in node.values())
    if isinstance(node, list):
        return any(_has_unique(value) for value in node)
    # Walking a container never interprets its keys as declaration markers.
    return False


def ensure_bound_run_values(scenario):
    """Low-level projections must not generate a token or pass an unbound run."""
    if any(_has_unique(item.value) for item in scenario.inputs):
        raise ValueError("run values must be explicitly bound before projection execution")


def bind_run_values(scenario):
    """Return an independent declaration copy and its single token, if needed.

    Input-only expressions are frozen. Include arguments depending on a response
    remain typed expressions for atomic preparation of each consuming step.
    """
    bound = copy.deepcopy(scenario)
    parameters = bound.parameters
    try:
        validate_parameters(parameters)
    except RecursionError:
        raise ValueError("parameter dependency graph exceeds available recursion capacity") from None
    token = uuid4().hex if any(_has_unique(value) for value in parameters.values()) else None
    resolved, active = {}, set()

    def parameter(name):
        if name in resolved:
            return resolved[name]
        if name in active:
            raise ValueError("cyclic parameter dependency")
        active.add(name)
        try:
            resolved[name] = freeze(parameters[name])
            return resolved[name]
        finally:
            active.remove(name)

    def freeze(node):
        if isinstance(node, RunUnique):
            return token
        if isinstance(node, ValueRef) and node.source == "input":
            value = parameter(node.key)
            # Keep a pointer when the dependency remains response-derived.
            return node if isinstance(value, (ValueRef, StringConcat)) else copy.deepcopy(value)
        if isinstance(node, StringConcat):
            parts = tuple(freeze(part) for part in node.parts)
            if all(type(part) is str for part in parts):
                return "".join(parts)
            return replace(node, parts=parts)
        if isinstance(node, dict):
            return {key: freeze(value) for key, value in node.items()}
        if isinstance(node, list):
            return [freeze(value) for value in node]
        return copy.deepcopy(node)

    try:
        bound.inputs = [Input(name, parameter(name)) for name in parameters]
    except RecursionError:
        raise ValueError("parameter dependency graph exceeds available recursion capacity") from None
    bound.run_values_bound = True
    return bound, token
