"""Bounded numeric and list-length checks over actual response evidence."""
import math

from refracto.declaration import field_comparison, values, vocabulary

CHECKS = frozenset({"field_compare", "collection_length"})


def is_number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def require_expected(check, value):
    if check == "field_compare" and is_number(value):
        return
    if check == "collection_length" and type(value) is int and value >= 0:
        return
    domain = "finite number" if check == "field_compare" else "non-negative integer"
    raise ValueError(f"{check} value must be a {domain}")


def require_operator(op):
    if type(op) is not str or op not in vocabulary.COMPARISON_OPS:
        raise ValueError("response numeric comparison operator is unsupported")


def resolve_expected(check, node, *, bound_values=None, inputs=None):
    expected, error = field_comparison.resolve_expected(
        node, bound_values=bound_values, inputs=inputs)
    if error is not None:
        raise ValueError(f"{check} expected reference is unavailable")
    require_expected(check, expected)
    return expected


def evaluate(check, fields, field, op, expected):
    """Validate examined evidence before comparing; never print operand data."""
    require_operator(op)
    require_expected(check, expected)
    prefix = f"{check} field={field!r} op={op!r}"
    if field not in fields:
        return False, f"{prefix}: missing field"
    observed = fields[field]
    field_comparison.require_data(observed)
    if check == "collection_length":
        if type(observed) is not list:
            return False, f"{prefix}: observed field is not a list"
        actual = len(observed)
    else:
        if not is_number(observed):
            return False, f"{prefix}: observed field is not a number"
        actual = observed
    # Python compares built-in integers and floats without first rounding an
    # arbitrary-size integer to float. Equality retains the exact-type policy.
    if op == "==":
        ok = values.equal(actual, expected)
    elif op == ">":
        ok = actual > expected
    elif op == ">=":
        ok = actual >= expected
    elif op == "<":
        ok = actual < expected
    else:
        ok = actual <= expected
    return ok, "" if ok else f"{prefix}: comparison does not hold"
