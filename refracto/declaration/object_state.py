"""Bounded values for semantic object-state observations, without coercion."""
import math


CHECK = "object_field_equals"


def require_id(value):
    """Accept only an actual integer or a nonempty string business identity."""
    if type(value) is int or (type(value) is str and value != ""):
        return
    raise ValueError("object-state id must be a non-empty string or integer")


def require_expected(value):
    """Keep null and falsy scalars distinct; never accept containers or infinity."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    raise ValueError("object-state expected value must be a finite scalar")
