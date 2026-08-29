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
        "object_field_equals": ("anchor", "id", "field", "value"),
        "no_anonymous": ("anchor",),
    },
    "request": {
        # Optional key `async` names a response field carrying an async handle.
        # It is a contract hint, not a poll trigger.
        "request": ("method", "path"),
    },
    "response": {
        "success": (),
        "failure": (),
        "has": ("field",),
        "field_equals": ("field", "value"),
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

# Value-reference sources for bounded assertion values. A reference is a data-only
# pointer (no expressions/arithmetic/concatenation) written as a single-key
# mapping `{<source_tag>: <key>}`.
#   tag in scenario YAML -> canonical source name stored on model.ValueRef
VALUE_REF_SOURCES = {
    "from_bind": "bind",
    "from_input": "input",
}

# A value reference may only be compared with equality in this step. Ordering
# comparisons against a reference have no clear identity semantics and would
# force type checks to be deferred to runtime, so they are rejected at load.
VALUE_REF_OPS = ("==",)

# Poll policy for v2 step polling.
POLL_ON_TIMEOUT = ("FAIL", "SKIP")
POLL_SAFE_METHODS = ("GET",)


def is_valid(point: str, check: str) -> bool:
    return point in _TERMS and check in _TERMS[point]


def required_params(point: str, check: str) -> tuple:
    return _TERMS.get(point, {}).get(check, ())


def optional_params(point: str, check: str) -> tuple:
    return _OPTIONAL.get(point, {}).get(check, ())
