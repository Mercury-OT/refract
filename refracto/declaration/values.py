"""Resolution and comparison for bounded assertion values.

Only parsed references and bounded string composition nodes are evaluated;
literal dictionaries and response values are never parsed as declarations.
This module is shared by projections so the same assertion cannot acquire
different semantics depending on where it is evaluated.
"""

from refracto.declaration.model import RunUnique, StringConcat, ValueRef


class ConcatOperandError(str):
    """A safe message carrying only the typed operand needed for provenance."""
    def __new__(cls, operand):
        instance = super().__new__(cls, "concat operands must resolve to strings")
        instance.operand = operand
        return instance


def resolve(value, *, bound_values=None, inputs=None, _active=None, _memo=None):
    """Return ``(concrete_value, error)`` for a literal or value reference."""
    memo = {} if _memo is None else _memo
    if isinstance(value, RunUnique):
        return None, "run values must be explicitly bound before projection execution"
    if isinstance(value, StringConcat):
        parts = []
        for part in value.parts:
            result, error = resolve(part, bound_values=bound_values, inputs=inputs, _active=_active, _memo=memo)
            if error is not None:
                return None, error
            if type(result) is not str:
                return None, ConcatOperandError(part)
            parts.append(result)
        return "".join(parts), None
    if not isinstance(value, ValueRef):
        return value, None

    if value.source == "bind":
        available = bound_values or {}
        if value.key not in available:
            return None, f"response reference {value.key!r} has no resolved value"
        return available[value.key], None

    if value.source == "input":
        if value.key in memo:
            return memo[value.key]
        matches = [item.value for item in (inputs or []) if item.kind == value.key]
        if len(matches) != 1:
            return None, (
                f"parameter reference {value.key!r} requires exactly one "
                f"declared parameter, found {len(matches)}"
            )
        active = set() if _active is None else _active
        if value.key in active:
            return None, "cyclic parameter dependency"
        active.add(value.key)
        try:
            memo[value.key] = resolve(matches[0], bound_values=bound_values, inputs=inputs,
                                      _active=active, _memo=memo)
            return memo[value.key]
        finally:
            active.remove(value.key)

    return None, f"unsupported value reference source {value.source!r}"


def equal(actual, expected) -> bool:
    """Compare JSON-like values with exact type and value equality."""
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            equal(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            equal(a, b) for a, b in zip(actual, expected))
    return actual == expected
