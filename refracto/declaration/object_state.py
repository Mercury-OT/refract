"""Bounded values for semantic object-state observations, without coercion."""
import math


CHECK = "object_field_equals"
ABSENT_CHECK = "object_absent"
CHECKS = (CHECK, ABSENT_CHECK)


class PollSelectionError(ValueError):
    """Resolved IDs cannot supply the single selection an object wait requires."""


def require_poll(step, known=None, *, unknown=()):
    """Validate an opt-in policy and any selectors already known at this boundary."""
    from refracto.declaration.model import PollPolicy

    if step.object_poll is None:
        return
    if type(step.object_poll) is not PollPolicy or step.object_poll.on_timeout != "FAIL":
        raise ValueError("object_poll requires on_timeout: FAIL")
    if (step.request is None or step.action not in {"request", "open", "click", "fill", "press"}
            or step.action == "press" and step.key != "Enter"):
        raise ValueError("object_poll requires a request-bearing action")
    if step.poll is not None:
        raise ValueError("object_poll must not be combined with poll")
    selected = step.expect.backend_state
    if not selected or any(item.check not in CHECKS for item in selected):
        raise ValueError("object_poll requires only object-state assertions")
    if len({item.params["object"] for item in selected}) != 1:
        raise ValueError("object_poll requires one business object and one exact typed ID")
    if known is None:
        return
    identities = set()
    for item in selected:
        identity = known(item.params["id"])
        if any(identity is marker for marker in unknown):
            continue
        require_id(identity)
        identities.add((type(identity), identity))
    if len(identities) > 1:
        raise PollSelectionError("object_poll requires one business object and one exact typed ID")


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
