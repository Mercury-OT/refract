"""Pre-action browser identity checks that do not require browser installation."""
import dataclasses

import pytest

from refracto import ports
from refracto_browser import BrowserSupport, _support
from tests.test_browser_support_lifecycle import Resource


def permit(**changes):
    value = ports.UiActionPermit(execution_id="run", action_id="action", step_id="step",
        mode="live", action="click", target="button", value=None, token="token",
        user="creator", session_generation=1, context_id="context-one", resolved_bindings={})
    return dataclasses.replace(value, **changes)


@pytest.fixture
def support(monkeypatch):
    calls = []
    monkeypatch.setattr(_support, "_acquire_playwright", lambda: Resource("runtime", calls))
    monkeypatch.setattr(_support, "_release_playwright", lambda: calls.append("stop"))
    return BrowserSupport("http://example.com/", lambda page: {})


@pytest.mark.parametrize("changes", [
    {"user": "peer"}, {"user": None}, {"session_generation": True},
    {"session_generation": 2}, {"context_id": "another-context"},
])
def test_wrong_first_permit_is_rejected_before_browser_action(support, changes):
    context = support.open("live", user="creator", session_generation=1, context_id="context-one")
    try:
        with pytest.raises(ValueError, match="another user/session/context"):
            support._authorize(context, permit(**changes), None, "button")
        assert context.execution_id is None
        assert context.permits == {}
    finally:
        support.close(context)


def test_one_execution_can_keep_distinct_user_contexts_without_cross_admission(support):
    creator = support.open("live", user="creator", session_generation=1, context_id="creator-context")
    peer = support.open("live", user="peer", session_generation=1, context_id="peer-context")
    try:
        support._authorize(creator, permit(context_id="creator-context", token="creator-token"), None, "button")
        support._authorize(peer, permit(user="peer", context_id="peer-context", action_id="peer-action", token="peer-token"), None, "button")
        support.close(creator)
        renewed = support.open("live", user="creator", session_generation=2, context_id="creator-new")
        try:
            with pytest.raises(ValueError, match="another user/session/context"):
                support._authorize(renewed, permit(context_id="creator-context", action_id="old-action", token="old-token"), None, "button")
            support._authorize(renewed, permit(context_id="creator-new", session_generation=2,
                               action_id="new-action", token="new-token"), None, "button")
            assert not peer.closed
        finally:
            support.close(renewed)
    finally:
        support.close(creator)
        support.close(peer)


@pytest.mark.parametrize("options", [
    {"storage_state": {"cookies": [], "origins": []}},
    {"http_credentials": {"username": "account", "password": "secret"}},
    {"client_certificates": []},
    {"extra_http_headers": {"aUtHoRiZaTiOn": "secret"}},
    {"extra_http_headers": {"Cookie": "session=secret"}},
])
def test_bound_anonymous_context_rejects_ambient_auth_before_acquisition(monkeypatch, options):
    monkeypatch.setattr(_support, "_acquire_playwright", lambda: pytest.fail("browser acquired"))
    support = BrowserSupport("http://example.com/", lambda page: {})
    with pytest.raises(ValueError, match="anonymous"):
        support.open("live", user=None, session_generation=0, context_id="anonymous-context",
                     context_options=options)
