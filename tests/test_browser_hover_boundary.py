"""Offline control for the exact request suppressed by hover mock isolation."""
from types import SimpleNamespace

import pytest

from refracto_browser._native import NativeCollector


@pytest.mark.parametrize('marked,action,error', [
    (False, None, True),  # An older unassociated request still has real CORS failure.
    (True, None, False),  # Only this exact request was deliberately blocked.
    (True, 'authorized', True),  # Foreground evidence never becomes diagnostic.
])
def test_hover_context_flag_cannot_mask_unrelated_cors_failure(marked, action, error):
    collector = NativeCollector.__new__(NativeCollector)
    collector.context = SimpleNamespace(mode='mock', block_unassociated_mock=True, errors=[])
    collector.notes = []
    collector.requests = {'request': {'action': action, 'blocked_mock_background': marked}}
    collector._failed({'requestId': 'request', 'corsErrorStatus': {'corsError': 'InvalidAllowOriginValue'}})
    assert bool(collector.context.errors) is error
    assert collector.requests == {}
    if not error:
        assert collector.notes == ['background HTTP acquisition failed']
