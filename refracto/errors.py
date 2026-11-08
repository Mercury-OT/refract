"""Finite action failure reasons, independent of optional browser dependencies.

Only exact instances with validated fields cross the core diagnostic boundary.
This is cooperative error reporting, not an attestation of adapter behavior.
"""
from enum import Enum


class ActionFailureReason(Enum):
    COLLECTION_TIMEOUT = "collection_timeout"
    PAGE_ERROR = "page_error"
    POLICY_DENIED = "policy_denied"
    TARGET_UNAVAILABLE = "target_unavailable"
    EVIDENCE_INVALID = "evidence_invalid"
    MOCK_BACKGROUND_BLOCKED = "mock_background_blocked"
    COLLECTION_FAILED = "collection_failed"
    CLEANUP_FAILED = "cleanup_failed"


# Fixed strings, not arbitrary exception attributes or an enum's mutable value.
_REASON_CODES = (
    (ActionFailureReason.COLLECTION_TIMEOUT, "collection_timeout"),
    (ActionFailureReason.PAGE_ERROR, "page_error"),
    (ActionFailureReason.POLICY_DENIED, "policy_denied"),
    (ActionFailureReason.TARGET_UNAVAILABLE, "target_unavailable"),
    (ActionFailureReason.EVIDENCE_INVALID, "evidence_invalid"),
    (ActionFailureReason.MOCK_BACKGROUND_BLOCKED, "mock_background_blocked"),
    (ActionFailureReason.COLLECTION_FAILED, "collection_failed"),
    (ActionFailureReason.CLEANUP_FAILED, "cleanup_failed"),
)


def _reason_code(reason):
    if type(reason) is ActionFailureReason:
        return next((code for member, code in _REASON_CODES if reason is member), None)
    return None


class ActionFailure(RuntimeError):
    """A safe fixed reason plus a separate owned-cleanup failure indicator."""

    def __init__(self, reason, *, cleanup_failed=False):
        if _reason_code(reason) is None or type(cleanup_failed) is not bool:
            raise ValueError("invalid action failure category")
        self.reason = reason
        self.cleanup_failed = cleanup_failed
        super().__init__(self.__str__())

    def __str__(self):
        detail = safe_action_failure(self)
        code, cleanup = detail if detail is not None else ("collection_failed", False)
        suffix = "; cleanup_failed" if cleanup else ""
        return f"browser action or evidence collection failed ({code}{suffix})"

    def __repr__(self):
        detail = safe_action_failure(self)
        code, cleanup = detail if detail is not None else ("collection_failed", False)
        return f"ActionFailure(reason='{code}', cleanup_failed={cleanup})"


def safe_action_failure(error):
    """Return only fixed data from an exact, still-valid category exception."""
    if type(error) is not ActionFailure:
        return None
    code = _reason_code(getattr(error, "reason", None))
    cleanup = getattr(error, "cleanup_failed", None)
    if code is None or type(cleanup) is not bool:
        return None
    return code, cleanup
