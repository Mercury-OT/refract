"""Offline lifecycle checks, including failures before a page can exist."""

import gc
import weakref

import pytest

from refracto import ports
from refracto_browser import BrowserSupport
from refracto_browser import _support


class Resource:
    def __init__(self, name, calls, fail=None):
        self.name, self.calls, self.fail = name, calls, fail
        self.chromium = self

    def _call(self, operation):
        self.calls.append(operation)
        if operation == self.fail:
            raise ValueError("sensitive-runtime-sentinel")

    def launch(self, **kwargs):
        self._call("launch")
        return Resource("browser", self.calls, self.fail)

    def new_context(self, **kwargs):
        self._call("new_context")
        return Resource("context", self.calls, self.fail)

    def set_default_timeout(self, value):
        pass

    def set_default_navigation_timeout(self, value):
        pass

    def add_init_script(self, script):
        self._call("instrument")

    def route(self, pattern, callback):
        self._call("route")

    def new_page(self):
        self._call("new_page")
        return Resource("page", self.calls, self.fail)

    def on(self, event, callback):
        pass

    def close(self):
        self._call("close_" + self.name)


@pytest.mark.parametrize("failure,closed", [
    ("launch", []),
    ("new_context", ["close_browser"]),
    ("instrument", ["close_context", "close_browser"]),
    ("route", ["close_context", "close_browser"]),
    ("new_page", ["close_context", "close_browser"]),
])
def test_partial_open_releases_all_acquired_resources(monkeypatch, failure, closed):
    calls = []
    monkeypatch.setattr(_support, "_acquire_playwright", lambda: Resource("runtime", calls, failure))
    monkeypatch.setattr(_support, "_release_playwright", lambda: calls.append("stop"))
    support = BrowserSupport("http://example.com/", lambda page: {})
    with pytest.raises(RuntimeError) as error:
        support.open("live", context_options={"extra_http_headers": {"Authorization": "secret-options"}})
    assert calls[-len(closed) - 1:] == [*closed, "stop"]
    assert "sensitive-runtime-sentinel" not in str(error.value)
    assert "secret-options" not in str(error.value)


def test_close_failure_still_closes_browser_and_releases_runtime(monkeypatch):
    calls = []
    monkeypatch.setattr(_support, "_acquire_playwright", lambda: Resource("runtime", calls, "close_context"))
    monkeypatch.setattr(_support, "_release_playwright", lambda: calls.append("stop"))
    support = BrowserSupport("http://example.com/", lambda page: {})
    context = support.open("live")
    with pytest.raises(RuntimeError) as error:
        support.close(context)
    assert calls[-3:] == ["close_context", "close_browser", "stop"]
    assert str(error.value) == "browser resource cleanup failed"
    support.close(context)
    with pytest.raises(ValueError, match="closed"):
        support.snapshot(context)


def test_invalid_open_arguments_do_not_acquire_browser_resources(monkeypatch):
    def forbidden():
        pytest.fail("invalid arguments started a browser")
    monkeypatch.setattr(_support, "_acquire_playwright", forbidden)
    support = BrowserSupport("http://example.com/", lambda page: {})
    for kwargs in ({"mode": "other"}, {"mode": "live", "mock_plan": []},
                   {"mode": "mock", "mock_plan": [object()]},
                   {"mode": "live", "context_options": {"service_workers": "allow"}}):
        with pytest.raises(ValueError):
            support.open(**kwargs)


def test_closed_context_is_collectible_without_reauthorizing_its_execution(monkeypatch):
    calls = []
    monkeypatch.setattr(_support, "_acquire_playwright", lambda: Resource("runtime", calls))
    monkeypatch.setattr(_support, "_release_playwright", lambda: calls.append("stop"))
    support = BrowserSupport("http://example.com/", lambda page: {})
    context = support.open("live")
    permit = ports.UiActionPermit(execution_id="closed-run", action_id="closed-action",
        step_id="step", mode="live", action="click", target="button", value=None,
        token="closed-token", resolved_bindings={})
    # Exercise admission independently of Playwright so this stays core-only.
    support._authorize(context, permit, None, "button")
    reference = weakref.ref(context)
    support.close(context)
    del context
    gc.collect()
    assert reference() is None

    fresh = support.open("live")
    try:
        next_permit = ports.UiActionPermit(execution_id="closed-run", action_id="new-action",
            step_id="next-step", mode="live", action="click", target="button", value=None,
            token="new-token", resolved_bindings={})
        with pytest.raises(ValueError, match="already bound"):
            support.perform(fresh, next_permit, selector="button")
    finally:
        support.close(fresh)
    other = BrowserSupport("http://example.com/", lambda page: {})
    other_context = other.open("live")
    try:
        with pytest.raises(ValueError, match="already used"):
            other.perform(other_context, permit, selector="button")
    finally:
        other.close(other_context)
