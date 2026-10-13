"""Bounded, read-only comparison of normalized response collections."""
import math

from refracto.declaration import values


def is_scalar(value):
    """The finite JSON scalar domain, with null allowed as an expectation."""
    return (value is None or type(value) in (str, bool, int)
            or (type(value) is float and math.isfinite(value)))


def resolve_matching(matching, *, bound_values=None, inputs=None):
    """Resolve matching values without including their contents in errors."""
    resolved = {}
    for key, declared in matching.items():
        value, error = values.resolve(declared, bound_values=bound_values, inputs=inputs)
        if error is not None:
            raise ValueError(error)
        if not is_scalar(value):
            raise ValueError(f"collection matching field {key!r} requires a finite scalar")
        resolved[key] = value
    return resolved


def evaluate(fields, field, matching, count, *, bound_values=None, inputs=None):
    """Return (passed, safe detail), never silently discarding malformed rows."""
    prefix = f"collection={field!r} matching_keys={sorted(matching)!r}"
    try:
        expected = resolve_matching(matching, bound_values=bound_values, inputs=inputs)
    except ValueError as exc:
        return False, f"{prefix} {exc}"
    if field not in fields:
        return False, f"{prefix} collection is missing"
    collection = fields[field]
    if not isinstance(collection, list):
        return False, f"{prefix} collection is not a list"
    if any(not isinstance(member, dict) for member in collection):
        return False, f"{prefix} collection contains a non-object member"
    actual = sum(all(key in member and values.equal(member[key], value)
                     for key, value in expected.items()) for member in collection)
    if actual == count:
        return True, ""
    return False, f"{prefix} expected_count={count} actual_count={actual}"
