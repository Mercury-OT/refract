"""Reject secondary targets without reentering a paused renderer."""
from types import SimpleNamespace

import pytest

from refracto_browser._native import NativeCollector
from refracto.errors import ActionFailureReason as Reason


@pytest.mark.parametrize("target_id,closed", [("owned-page", False), ("new-page", True)])
def test_rejection_closes_only_the_owned_context_without_resuming_target(target_id, closed):
    calls = []
    collector = NativeCollector.__new__(NativeCollector)
    collector.target_id = "owned-page"
    collector.context = SimpleNamespace(errors=[], browser_context=SimpleNamespace(
        close=lambda: calls.append("owned-context")))
    collector.target_guard = SimpleNamespace(send=lambda *_a, **_k: pytest.fail("target command or resume"))
    collector._target({"targetInfo": {"targetId": target_id, "browserContextId": "untrusted"}})
    assert calls == (["owned-context"] if closed else [])
    assert collector.context.errors == ([Reason.POLICY_DENIED] if closed else [])
