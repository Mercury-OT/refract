"""Bounded assertion vocabulary.

Each observation point allows a fixed set of assertion terms, and each term has
one defined meaning. New assertion kinds must be registered here rather than
embedded as ad-hoc logic inside scenario YAML.
"""

OBSERVATION_POINTS = ("frontend", "request", "response", "backend_state")

# point -> {term -> required param keys}
_TERMS = {
    "frontend": {
        "visible": ("anchor",),
        "count_gt": ("anchor", "n"),
    },
    "request": {
        # Optional key `async` names a response field carrying an async handle.
        # It is a contract hint, not a poll trigger.
        "request": ("method", "path"),
    },
    "response": {
        "success": (),
        "has": ("field",),
    },
    "backend_state": {
        "span_exists": ("span",),
        "span_attr": ("span", "attr", "op", "value"),
    },
}

# point -> {term -> optional param keys}
_OPTIONAL = {
    "request": {"request": ("async",)},
}

# Comparison operators accepted by `span_attr`. Ordering operators require a
# numeric value.
COMPARISON_OPS = (">", ">=", "<", "<=", "==")
ORDERING_OPS = (">", ">=", "<", "<=")

# Poll policy for v2 step polling.
POLL_ON_TIMEOUT = ("FAIL", "SKIP")
POLL_SAFE_METHODS = ("GET",)


def is_valid(point: str, check: str) -> bool:
    return point in _TERMS and check in _TERMS[point]


def required_params(point: str, check: str) -> tuple:
    return _TERMS.get(point, {}).get(check, ())


def optional_params(point: str, check: str) -> tuple:
    return _OPTIONAL.get(point, {}).get(check, ())
