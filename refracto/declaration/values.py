"""Resolution and comparison for bounded assertion values.

Values are deliberately data-only: either a literal scalar or a ``ValueRef``
resolved from the current step's bindings or the scenario's declared inputs.
This module is shared by projections so the same assertion cannot acquire
different semantics depending on where it is evaluated.
"""

from refracto.declaration.model import ValueRef


def resolve(value, *, bound_values=None, inputs=None):
    """Return ``(concrete_value, error)`` for a literal or value reference."""
    if not isinstance(value, ValueRef):
        return value, None

    if value.source == "bind":
        available = bound_values or {}
        if value.key not in available:
            return None, f"response reference {value.key!r} has no resolved value"
        return available[value.key], None

    if value.source == "input":
        matches = [item.value for item in (inputs or []) if item.kind == value.key]
        if len(matches) != 1:
            return None, (
                f"parameter reference {value.key!r} requires exactly one "
                f"declared parameter, found {len(matches)}"
            )
        return matches[0], None

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
