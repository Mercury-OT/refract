"""Shared strict rules for declared and captured HTTP status values."""

CHECKS = frozenset({"status_equals", "status_in"})


def valid(value):
    return type(value) is int and 100 <= value <= 599


def require_observed(value):
    if not valid(value):
        # An adapter value may be arbitrary or sensitive: never interpolate it.
        raise ValueError("HTTP status evidence is missing or invalid")
    return value


def allowed(assertion):
    return frozenset([assertion.params["value"]] if assertion.check == "status_equals"
                     else assertion.params["values"])


def mismatch(expected, observed):
    if not valid(observed):
        return "HTTP status evidence is missing or invalid"
    return f"HTTP status expected one of {sorted(expected)}, observed {observed}"
