"""Fault injection at browser lifecycle boundaries, with actual owned Chromium.

Injected failures only exercise error paths; they never alter successful
evidence, application requests, or the helper's association decisions.
"""
import pytest
from playwright import sync_api
from playwright.sync_api import Browser, BrowserContext, BrowserType, Page

from refracto_browser import BrowserSupport
from tests.browser.adapter import SyntheticUi, read_rendered
from tests.browser.test_support import permit, run_live, synthetic_scenario


@pytest.mark.parametrize("boundary", ["launch", "context", "page", "navigation"])
def test_partial_open_and_navigation_failures_release_every_acquired_resource(http_peer, monkeypatch, tmp_path, boundary):
    secret = "synthetic-lifecycle-secret-219"
    browsers, contexts, stops = [], [], []
    real_launch = BrowserType.launch
    real_context = Browser.new_context
    real_page = BrowserContext.new_page
    real_factory = sync_api.sync_playwright

    def launch(self, *args, **kwargs):
        if boundary == "launch":
            return real_launch(self, executable_path=str(tmp_path / secret))
        browser = real_launch(self, *args, **kwargs)
        browsers.append(browser)
        return browser

    def new_context(self, *args, **kwargs):
        if boundary == "context":
            raise RuntimeError(secret)
        context = real_context(self, *args, **kwargs)
        contexts.append(context)
        return context

    def new_page(self, *args, **kwargs):
        if boundary == "page":
            raise RuntimeError(secret)
        return real_page(self, *args, **kwargs)

    def factory():
        manager = real_factory()
        real_start = manager.start
        def start():
            runtime = real_start()
            real_stop = runtime.stop
            def stop():
                stops.append(True)
                return real_stop()
            runtime.stop = stop
            return runtime
        manager.start = start
        return manager

    monkeypatch.setattr(BrowserType, "launch", launch)
    monkeypatch.setattr(Browser, "new_context", new_context)
    monkeypatch.setattr(BrowserContext, "new_page", new_page)
    monkeypatch.setattr(sync_api, "sync_playwright", factory)
    if boundary == "navigation":
        def fail_navigation(self, *args, **kwargs):
            raise RuntimeError(secret)
        monkeypatch.setattr(Page, "goto", fail_navigation)
    helper = BrowserSupport(http_peer.base_url, read_rendered)
    with pytest.raises(Exception) as error:
        context = helper.open("live")
        helper.perform(context, permit("open"), url=http_peer.base_url)
    assert secret not in str(error.value)
    assert stops == [True]
    assert all(not browser.is_connected() for browser in browsers)
    assert all(context.pages == [] for context in contexts)
    assert http_peer.requests == []


def test_cleanup_failure_is_visible_while_other_owned_resources_are_released(http_peer, monkeypatch):
    secret = "synthetic-close-secret-125"
    pages = []
    def read(page):
        pages.append(page)
        return read_rendered(page)
    support = BrowserSupport(http_peer.base_url, read)
    context = support.open("live")
    support.snapshot(context)
    real_close = BrowserContext.close
    def close_then_fail(self, *args, **kwargs):
        real_close(self, *args, **kwargs)
        raise RuntimeError(secret)
    monkeypatch.setattr(BrowserContext, "close", close_then_fail)
    with pytest.raises(Exception) as error:
        support.close(context)
    assert secret not in str(error.value)
    assert pages[0].is_closed()
    support.close(context)
    with pytest.raises(Exception):
        support.snapshot(context)


def test_core_reports_cleanup_error_after_browser_resources_are_released(http_peer, monkeypatch):
    secret = "synthetic-close-report-secret-610"
    pages = []
    def read(page):
        pages.append(page)
        return read_rendered(page)
    real_close = BrowserContext.close
    def close_then_fail(self, *args, **kwargs):
        real_close(self, *args, **kwargs)
        raise RuntimeError(secret)
    monkeypatch.setattr(BrowserContext, "close", close_then_fail)
    ui = SyntheticUi(http_peer.base_url, read=read)
    result = run_live(synthetic_scenario(), ui)
    assert result.status == "FAILED"
    assert result.steps[-1].status == "ERROR"
    assert secret not in result.steps[-1].detail
    assert ui.close_calls == 1
    assert pages[-1].is_closed()
