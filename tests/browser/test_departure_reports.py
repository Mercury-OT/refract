"""Synthetic browser navigation and fail-closed policy controls for departure reports."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from refracto.errors import ActionFailure
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport
from refracto_browser._native import NativeCollector
from tests.browser.test_background_http_compatibility import Peer, permit, received


NOTE = "background request body not represented"


@pytest.fixture
def lab():
    servers, opened = [], []

    def peer():
        server = Peer()
        servers.append(server)
        return server

    def create(script, *, paths=("/api/events",), mode="live"):
        server = peer()
        server.page = ("<title>Records</title><button id='go'>Add</button><script>"
                       + script + "</script>").encode()
        policy = BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(server.url, "/api", ""),),
            credential_origins=(server.url,), background_beacon_paths=paths)
        support = BrowserSupport(server.url, lambda p: {"title": p.title()}, network_policy=policy)
        ctx = support.open(mode, mock_plan=[] if mode == "mock" else None)
        opened.append((support, ctx))
        support.perform(ctx, permit(mode=mode), url=server.url + "/")
        return server, support, ctx

    create.peer = peer
    yield create
    for support, ctx in reversed(opened):
        support.close(ctx)
    for server in servers:
        server.close()


def on_departure(path):
    return f"addEventListener('pagehide',()=>navigator.sendBeacon('{path}','departed'));"


def test_reopen_preserves_distinct_business_post_and_excludes_same_path_beacon(lab):
    # The same endpoint receives two POSTs. Only the click has primary evidence.
    page, support, ctx = lab(on_departure("/api/events") + """
        go.onclick=()=>fetch('/api/events',{method:'POST',body:'{"action":"add"}'});
    """)
    posted = support.perform(ctx, permit("click"), selector="#go").evidence
    reopened = support.perform(ctx, permit(), url=page.url + "/").evidence
    assert [(r.request.method, r.request.path, r.request.body) for r in posted.traffic] == [
        ("POST", "events", {"action": "add"})]
    assert [r["body"] for r in received(page, "/api/events")] == [b'{"action":"add"}', b"departed"]
    assert reopened.rendered == {"title": "Records"}
    assert reopened.traffic == reopened.diagnostic_recorded == reopened.mock_recordings == []
    assert reopened.diagnostic_notes == [NOTE]


@pytest.mark.parametrize("mode,path,configured", [
    ("mock", "/api/events", True), ("live", "/api/events", False),
    ("live", "/api/events/child", True), ("live", "/api/events?q=1", True),
])
def test_unapproved_departure_never_reaches_server(lab, mode, path, configured):
    page, support, ctx = lab(on_departure(path), mode=mode, paths=("/api/events",) if configured else ())
    with pytest.raises(ActionFailure):
        support.perform(ctx, permit(mode=mode), url=page.url + "/")
    assert not any(r["method"] == "POST" for r in page.requests)
    assert ctx.traffic == ctx.mock_recordings == []


def test_foreign_destination_denied_before_delivery(lab):
    foreign = lab.peer()
    page, support, ctx = lab(on_departure(foreign.url + "/api/events"))
    with pytest.raises(ActionFailure):
        support.perform(ctx, permit(), url=page.url + "/")
    assert not received(foreign, "/api/events")


def test_redirect_response_cannot_forward_to_next_hop(lab):
    page, support, ctx = lab(on_departure("/api/redirect"), paths=("/api/redirect",))
    with pytest.raises(ActionFailure):
        support.perform(ctx, permit(), url=page.url + "/")
    assert [r["body"] for r in received(page, "/api/redirect")] == [b"departed"]
    assert not received(page, "/api/after-redirect")


def test_beacon_outside_reopen_cannot_stand_in_for_click(lab):
    page, support, ctx = lab("go.onclick=()=>navigator.sendBeacon('/api/events','clicked');")
    with pytest.raises(ActionFailure):
        support.perform(ctx, permit("click"), selector="#go")
    assert not received(page, "/api/events") and not ctx.traffic


def collector():
    native = object.__new__(NativeCollector)
    native.base, native.frame = "https://example.com:8443", "main"
    native.policy = BrowserNetworkPolicy(background_beacon_paths=("/events",), credential_origins=(native.base,))
    native.context = SimpleNamespace(mode="live", errors=[])
    native.target_guard = Mock()
    native.owner = SimpleNamespace(_reason=lambda context, error, default: getattr(error, "reason", default))
    native.report_handles, native.notes = {}, []
    native.reopening = True
    return native


def event():
    return {"frameId": "main", "resourceType": "Ping", "requestId": "handle",
            "request": {"method": "POST", "url": "https://example.com:8443/events", "headers": {}}}


@pytest.mark.parametrize("change", [
    {"frameId": "other"}, {"resourceType": "XHR"}, {"networkId": ""},
    {"responseStatusCode": 200}, {"responseErrorReason": "Failed"},
    {"redirectedRequestId": "prior"},
])
def test_incomplete_or_unmatched_pause_is_aborted(change):
    native = collector()
    native._paused(event() | change)
    assert native.context.errors and not native.report_handles
    assert native.target_guard.send.call_args.args[0] == "Fetch.failRequest"


def test_restricted_header_cannot_be_admitted():
    native = collector()
    e = event()
    e["request"]["headers"] = {"x-refract-private": "unused"}
    native._paused(e)
    assert native.context.errors and native.target_guard.send.call_args.args[0] == "Fetch.failRequest"


def test_fetch_handle_pairs_response_even_after_open_and_cannot_be_reused():
    native = collector()
    native._paused(event())
    native.reopening = False
    native._paused(event() | {"responseStatusCode": 204})
    assert not native.context.errors
    assert [call.args[0] for call in native.target_guard.send.call_args_list] == [
        "Fetch.continueRequest", "Fetch.continueResponse"]
    native._paused(event() | {"responseStatusCode": 204})
    assert native.context.errors and native.target_guard.send.call_args.args[0] == "Fetch.failRequest"


def test_context_cannot_grow_report_history_unbounded():
    native = collector()
    for i in range(32):
        e = event() | {"requestId": str(i)}
        native._paused(e)
        native._paused(e | {"responseStatusCode": 204})
    assert not native.context.errors
    native._paused(event())
    assert len(native.report_handles) == 32 and native.context.errors


@pytest.mark.parametrize("paths", ["/events", ["/"], ["/*"], ["/a%2fb"], ["//foreign/path"],
                                   ["/x/../events"], ["/events?"], ["/events", "/events"], ["/x"] * 17])
def test_beacon_configuration_requires_finite_distinct_literal_paths(paths):
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(background_beacon_paths=paths)


@pytest.mark.parametrize(("variation", "optional_loss"), [
    ("retired", True), ("current-document", False), ("no-old-loader", False),
    ("foreign-frame", False), ("uncommitted", False), ("foreground", False),
    ("mock", False), ("different-error", False),
])
def test_lost_body_requires_a_retired_optional_resource(variation, optional_loss):
    native = collector()
    native.session = Mock()
    native.document_loader = "new"
    native.departing_loader = None if variation == "no-old-loader" else "old"
    native.background_reads = native.background_bytes = native.body_reads_active = 0
    native.deferred_diagnostics = []
    native.mock_pending = []
    if variation == "mock":
        native.context.mode = "mock"
    error = "CDPSession.send: Protocol error (Network.getResponseBody): No resource with given identifier found"

    def dispatch(method, params=None):
        if method == "Network.getResponseBody":
            raise RuntimeError("failure" if variation == "different-error" else error)
        assert method == "Page.getFrameTree"
        return {"frameTree": {"frame": {"id": "main", "loaderId": "old" if variation == "uncommitted" else "new"}}}

    native.session.send.side_effect = dispatch
    native.requests = {"req": {
        "action": "click" if variation == "foreground" else None,
        "logical": "records", "header_items": [],
        "event": {"frameId": "sub" if variation == "foreign-frame" else "main",
                  "loaderId": "new" if variation == "current-document" else "old"},
    }}
    native._finished({"requestId": "req", "encodedDataLength": 0})
    assert not native.requests and native.body_reads_active == 0
    assert native.notes == (["background HTTP acquisition failed"] if optional_loss else [])
    assert bool(native.context.errors) is not optional_loss
