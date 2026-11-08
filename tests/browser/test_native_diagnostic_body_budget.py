"""Slow optional body reads cannot consume an unbounded action window."""
import time

import pytest

from tests.browser.test_multi_origin_transport import origins, browser, click


@pytest.mark.parametrize("delay", [0.010, 0.030])
def test_slow_optional_body_reads_keep_a_real_foreground_request(browser, monkeypatch, delay):
    support, context = browser()
    native = context.native
    original = native.session.send
    reads = []
    active = maximum_active = 0

    def delayed_send(method, params=None):
        nonlocal active, maximum_active
        identity = (params or {}).get("requestId")
        optional = (method == "Network.getResponseBody"
                    and native.requests.get(identity, {}).get("action") is None)
        if not optional:
            return original(method, params)
        reads.append(identity)
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            # A controlled slow collector, not an increased action deadline or
            # a claim to reproduce every host's CPU/network performance.
            time.sleep(delay)
            return original(method, params)
        finally:
            active -= 1

    monkeypatch.setattr(native.session, "send", delayed_send)
    try:
        initial = click(support, context, "background")
        deadline = time.monotonic() + 5
        while "background diagnostics truncated" not in native.notes and time.monotonic() < deadline:
            context.page.wait_for_timeout(10)
        evidence = click(support, context, "simple")
        assert initial.traffic == []
        assert len(evidence.traffic) == 1
        actual = evidence.traffic[0]
        assert actual.request.path == "service/echo"
        assert actual.response.json["data"]["path"] == "/api/echo"
        assert actual.response.step_id == actual.step_id
        assert actual.browser_identity == actual.response.browser_identity
        assert len(reads) == len(set(reads)) == native.background_reads <= 100
        assert maximum_active == 1
        assert native.background_reads + len(native.deferred_diagnostics) <= 100
        assert len(context.diagnostics) <= 100 and native.background_bytes <= 256 * 1024
        assert all(record.step_id is None for record in context.diagnostics)
        assert "background diagnostics truncated" in evidence.diagnostic_notes
    finally:
        if not context.closed:
            context.page.evaluate("clearInterval(window.background)")
