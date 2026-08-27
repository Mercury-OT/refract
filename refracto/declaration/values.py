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
            return None, f"value reference from_bind:{value.key} has no resolved bound value"
        return available[value.key], None

    if value.source == "input":
        matches = [item.value for item in (inputs or []) if item.kind == value.key]
        if len(matches) != 1:
            return None, (
                f"value reference from_input:{value.key} requires exactly one "
                f"declared scenario input, found {len(matches)}"
            )
        return matches[0], None

    return None, f"unsupported value reference source {value.source!r}"


def equal(actual, expected) -> bool:
    """Compare JSON-like values with exact type and value equality."""
    return type(actual) is type(expected) and actual == expected
