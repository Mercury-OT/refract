"""Owned, current-request trace facts shared by live execution projections."""
import copy

from refracto import ports


def require_trace_id(trace_id):
    if type(trace_id) is not str or not trace_id:
        raise ValueError("state requires current selected request trace")
    return trace_id


def _require_facts(facts, trace_id):
    if type(facts) is not ports.StateFacts:
        raise TypeError("StateProbe.observe must return StateFacts")
    if type(facts.trace_id) is not str or facts.trace_id != trace_id:
        raise ValueError("state trace mismatch")


def validate_state_facts(facts, trace_id):
    """Validate raw identity and the owned copy without disclosing either trace."""
    require_trace_id(trace_id)
    _require_facts(facts, trace_id)
    try:
        owned = copy.deepcopy(facts)
    except Exception:
        raise ValueError("state evidence could not be copied") from None
    _require_facts(owned, trace_id)
    return owned
