"""Complete, finite response-field comparisons with value-free diagnostics."""
import copy
import math

from refracto.declaration import values
from refracto.declaration.model import ValueRef

CHECKS = frozenset({"field_equals", "field_not_equals"})


def require_data(value, active=None):
    """Reject malformed data before equality can short-circuit on its type."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) not in (list, dict):
        raise ValueError("response field comparison requires finite JSON-like data")
    active = set() if active is None else active
    if id(value) in active:
        raise ValueError("response field comparison contains cyclic data")
    if type(value) is dict and any(type(key) is not str for key in value):
        raise ValueError("response field comparison requires string-keyed objects")
    active.add(id(value))
    try:
        for item in value.values() if type(value) is dict else value:
            require_data(item, active)
    finally:
        active.remove(id(value))


def resolve_expected(node, *, bound_values=None, inputs=None):
    """Resolve compiled references, never interpret response dictionaries as code."""
    def visit(item):
        if isinstance(item, ValueRef):
            resolved, error = values.resolve(item, bound_values=bound_values, inputs=inputs)
            if error is not None:
                raise LookupError(error)
            if item.source == "input":
                return visit(resolved)
            require_data(resolved)
            return copy.deepcopy(resolved)
        if type(item) is dict:
            return {key: visit(value) for key, value in item.items()}
        if type(item) is list:
            return [visit(value) for value in item]
        return item

    try:
        expected = visit(node)
    except LookupError as exc:
        return None, str(exc)
    except RecursionError:
        raise ValueError("response field comparison contains cyclic data") from None
    require_data(expected)
    return expected, None


def evaluate(check, fields, field, expected):
    """Return (passed, detail); missing is never evidence for inequality."""
    require_data(expected)
    present = field in fields
    if present:
        observed = fields[field]
        require_data(observed)
        equal = values.equal(observed, expected)
        ok = equal if check == "field_equals" else not equal
    else:
        observed, ok = None, False
    if ok:
        return True, ""
    # Preserve established scalar equality details, but never print container
    # contents (including nested keys), malformed values, or inequality values.
    if check == "field_equals" and type(expected) not in (dict, list) and type(observed) not in (dict, list):
        suffix = repr(observed) if present else "<missing>"
        return False, f"field={field!r} expected={expected!r} observed={suffix}"
    reason = "missing field" if not present else "values differ" if check == "field_equals" else "values are equal"
    return False, f"{check} field={field!r}: {reason}"
