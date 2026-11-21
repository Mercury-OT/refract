"""Socket permission does not imply an action, successful mock, or HTTP evidence."""
from contextlib import contextmanager
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

from refracto import ports
from refracto.errors import ActionFailure
from refracto.errors import ActionFailureReason as Reason
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from refracto_browser import ApiEndpoint, BackgroundWebSocket, BrowserNetworkPolicy, BrowserSupport
from tests.browser.socket_peer import SocketPeer
from tests.browser.test_background_http_compatibility import ScenarioDriver
from tests.browser.test_framework_failure_reporting import Auth, NoResponse


def test_socket_denial_close_failure_aborts_before_driver_can_synthesize_open():
    from playwright._impl._network import WebSocketRouteHandler
    from refracto_browser._websocket import SocketBoundary

    class Route:
        completed = False

        def close(self, **kwargs):
            raise ValueError('private-sentinel')

        async def _after_handle(self):
            self.completed = True

    ctx, route = SimpleNamespace(errors=[]), Route()
    boundary = SocketBoundary(ctx, 'https://example.com:443', ())
    with pytest.raises(ActionFailure) as failure:
        asyncio.run(WebSocketRouteHandler(None, '**/*', boundary.reject).handle(route))
    assert failure.value.reason is Reason.POLICY_DENIED and failure.value.cleanup_failed
    assert 'private-sentinel' not in str(failure.value) and failure.value.__context__ is None
    assert ctx.errors == [Reason.POLICY_DENIED, Reason.CLEANUP_FAILED]
    assert not route.completed


def permit(action='open', mode='live'):
    step = uuid4().hex
    return ports.UiActionPermit(execution_id='records', action_id=step, step_id=step,
                                mode=mode, action=action, target='page', value=None,
                                token=uuid4().hex)


@contextmanager
def opened(peer, *, mode='live', configured=True, options=None):
    policy = BrowserNetworkPolicy(
        api_endpoints=(ApiEndpoint(peer.url, '/api', 'records'),),
        credential_origins=(peer.url,),
        background_websockets=(BackgroundWebSocket('/socket', query_keys=('cursor',)),) if configured else (),
    )
    support = BrowserSupport(peer.url, lambda page: {}, timeout_ms=12000, network_policy=policy)
    ctx = support.open(mode, context_options=options)
    try:
        support.perform(ctx, permit(mode=mode), url=peer.url + '/')
        yield support, ctx
    finally:
        support.close(ctx)


ATTEMPT = """([url, protocols]) => new Promise(resolve => {
    const timer = setTimeout(() => resolve('timeout'), 4000);
    const finish = s => {clearTimeout(timer); resolve(s)};
    try {
        const ws = protocols === null ? new WebSocket(url) : new WebSocket(url, protocols);
        window.lastSocket = ws;
        ws.onopen = () => finish('open');
        ws.onerror = () => finish('error');
        ws.onclose = () => finish('closed');
    } catch { finish('denied'); }
})"""


def attempt(ctx, url, protocols=None):
    return ctx.page.evaluate(ATTEMPT, [url, protocols])


def assert_visible_failure(support, ctx, *, mode='live'):
    with pytest.raises(ActionFailure) as failure:
        support.perform(ctx, permit('click', mode), selector='#idle')
    assert ctx.closed
    assert 'private-sentinel' not in repr(failure.value) + str(failure.value)
    assert not ctx.traffic


@pytest.mark.parametrize(('mode', 'configured'), [('live', False), ('mock', False), ('mock', True)])
def test_default_and_mock_do_not_connect_or_fake_open(mode, configured):
    with SocketPeer() as peer, opened(peer, mode=mode, configured=configured) as (support, ctx):
        assert attempt(ctx, peer.socket) in {'denied', 'error', 'closed'}
        assert_visible_failure(support, ctx, mode=mode)
        assert not peer.upgrades and not ctx.mock_recordings and ctx.mock_queue.index == 0


def test_page_bootstrap_socket_does_not_escape_mock_before_action_collection():
    with SocketPeer() as peer:
        peer.page += b"""<script>try {
            const s = new WebSocket('ws://' + location.host + '/socket');
            s.onopen = () => console.info('synthetic-open');
        } catch { console.info('synthetic-denied') }</script>"""
        support = BrowserSupport(peer.url, lambda _: {}, timeout_ms=12000, network_policy=BrowserNetworkPolicy(
            credential_origins=(peer.url,), background_websockets=(BackgroundWebSocket('/socket'),)))
        ctx = support.open('mock')
        fixed_events = []
        ctx.page.on('console', lambda message: fixed_events.append(message.text)
                    if message.text in {'synthetic-open', 'synthetic-denied'} else None)
        try:
            with pytest.raises(ActionFailure):
                support.perform(ctx, permit(mode='mock'), url=peer.url + '/')
            assert ctx.closed and fixed_events == ['synthetic-denied'] and not peer.upgrades
        finally:
            support.close(ctx)


@pytest.mark.parametrize('kind', [
    'port', 'different-path', 'descendant', 'unknown-key', 'duplicate-key', 'encoding',
    'userinfo', 'fragment', 'subprotocol', 'large-value',
])
def test_undeclared_destinations_and_shapes_have_zero_upgrades(kind):
    with SocketPeer() as peer, SocketPeer() as other, opened(peer) as (support, ctx):
        urls = {
            'port': other.socket, 'different-path': peer.socket + 's', 'descendant': peer.socket + '/sub',
            'unknown-key': peer.socket + '?unknown=private-sentinel', 'duplicate-key': peer.socket + '?cursor=a&cursor=b',
            'encoding': peer.socket + '?cursor=%2F', 'userinfo': peer.socket.replace('://', '://account@'),
            'fragment': peer.socket + '#private-sentinel', 'subprotocol': peer.socket,
            'large-value': peer.socket + '?cursor=' + 'a' * 2048,
        }
        protocols = ['private-sentinel'] if kind == 'subprotocol' else None
        assert attempt(ctx, urls[kind], protocols) in {'denied', 'closed', 'error'}
        assert_visible_failure(support, ctx)
        assert not peer.upgrades and not other.upgrades


def test_redirect_cannot_open_or_deliver_credentials_to_another_service():
    with SocketPeer() as peer, SocketPeer() as other, opened(peer) as (_, ctx):
        peer.redirect = other.socket
        ctx.browser_context.add_cookies([dict(url=peer.url, name='session', value='private-sentinel', httpOnly=True)])
        assert attempt(ctx, peer.socket) in {'closed', 'error'}
        assert len(peer.upgrades) == 1
        assert peer.upgrades[0]['cookie'] == 'session=private-sentinel'
        assert not other.upgrades and not ctx.traffic


def test_bidirectional_background_socket_has_no_primary_and_closes_with_context():
    with SocketPeer() as peer:
        with opened(peer) as (support, ctx):
            ctx.browser_context.add_cookies([dict(url=peer.url, name='session', value='private-sentinel', httpOnly=True)])
            assert attempt(ctx, peer.socket + '?cursor=private-sentinel', []) == 'open'
            reply = ctx.page.evaluate("""() => new Promise(resolve => {
                lastSocket.onmessage = event => resolve(event.data);
                lastSocket.send('private-sentinel-frame');
            })""")
            assert reply == 'private-sentinel-frame'
            assert peer.upgrades == [dict(path='/socket?cursor=private-sentinel', cookie='session=private-sentinel',
                                          origin=peer.url, subprotocol=None)]
            evidence = support.perform(ctx, permit('click'), selector='#idle').evidence
            assert not evidence.traffic and not evidence.diagnostic_recorded and not evidence.mock_recordings
            assert 'private-sentinel' not in repr(evidence) + repr(evidence.diagnostic_notes)
        assert peer.disconnected.wait(2) and peer.closed_count == 1


def test_active_socket_is_closed_on_limit_failure():
    with SocketPeer() as peer, opened(peer) as (support, ctx):
        assert attempt(ctx, peer.socket) == 'open'
        assert attempt(ctx, peer.socket) in {'denied', 'closed', 'error'}
        assert_visible_failure(support, ctx)
        assert len(peer.upgrades) == 1 and peer.disconnected.wait(2)


def test_denial_flood_does_not_retain_urls_or_grow_an_error_per_attempt():
    with SocketPeer() as peer, opened(peer) as (support, ctx):
        denied = ctx.page.evaluate("""base => {
            let refusals = 0;
            for (let i = 0; i < 200; i++) {
                try { new WebSocket(base + '?unknown=private-sentinel-' + i); }
                catch { refusals++; }
            }
            return refusals;
        }""", peer.socket)
        assert denied == 200
        page_errors = ctx.page.evaluate('window.__refractBrowser.errors')
        assert len(page_errors) < 200 and len(ctx.errors) < 200
        assert 'private-sentinel' not in repr(page_errors) + repr(ctx.errors)
        assert_visible_failure(support, ctx)
        assert not peer.upgrades


def test_uncaught_socket_denials_keep_a_visible_but_bounded_page_error():
    with SocketPeer() as peer, opened(peer) as (support, ctx):
        count = 32
        ctx.page.evaluate("""([url, count]) => new Promise(done => {
            let seen = 0;
            addEventListener('error', () => { if (++seen === count) done(true) });
            for (let n = 0; n < count; n++) setTimeout(() => {
                new WebSocket(url + '?unknown=private-sentinel-' + n)
            }, 0);
        })""", [peer.socket, count])
        assert 0 < ctx.errors.count(Reason.PAGE_ERROR) < count
        assert_visible_failure(support, ctx)
        assert not peer.upgrades


def test_closed_sockets_do_not_reset_context_lifetime_budget():
    with SocketPeer() as peer, opened(peer) as (support, ctx):
        for i in range(4):
            assert attempt(ctx, peer.socket) == 'open'
            ctx.page.evaluate("""() => new Promise(resolve => {
                lastSocket.onclose = () => resolve(true); lastSocket.close();
            })""")
            if i == 1:
                support.perform(ctx, permit(), url=peer.url + '/?page=two')
        assert attempt(ctx, peer.socket) in {'denied', 'closed', 'error'}
        assert_visible_failure(support, ctx)
        assert len(peer.upgrades) == 4


def test_subframe_cannot_use_an_approved_top_document_endpoint():
    with SocketPeer() as peer, opened(peer) as (_, ctx):
        ctx.page.evaluate("""() => new Promise(resolve => {
            const frame = document.createElement('iframe');
            frame.onload = () => resolve(true);
            frame.srcdoc = '<!doctype html><p>Child</p>'; document.body.append(frame);
        })""")
        child, = ctx.page.frames[1:]
        assert child.evaluate(ATTEMPT, [peer.socket, None]) in {'denied', 'closed', 'error'}
        assert not peer.upgrades and not ctx.traffic


def test_unresolved_frame_identity_denies_the_connection_without_synthetic_open():
    with SocketPeer() as peer, opened(peer) as (support, ctx):
        ctx.page.evaluate("""() => new Promise(resolve => {
            const frame = document.createElement('iframe');
            frame.onload = () => resolve(true);
            frame.srcdoc = '<!doctype html><p>Child</p>'; document.body.append(frame);
        })""")
        assert len(ctx.page.frames) == 2
        assert attempt(ctx, peer.socket) in {'closed', 'denied', 'error'}
        assert_visible_failure(support, ctx)
        assert not peer.upgrades


def test_new_window_cannot_use_an_approved_top_document_endpoint():
    with SocketPeer() as peer, opened(peer) as (support, ctx):
        ctx.page.evaluate("""url => {
          document.querySelector('#go').onclick=() => {
              const child = open('about:blank');
              if (child) child.document.write('<script>new WebSocket('+JSON.stringify(url)+')<\\/script>');
          };
        }""", peer.socket)
        with pytest.raises(ActionFailure):
            support.perform(ctx, permit('click'), selector='#go')
        assert not peer.upgrades and ctx.closed


@pytest.mark.parametrize(('style', 'background_fetch', 'foreground_fetch'), [
    ('property', True, False), ('listener', True, True), ('property', False, True),
])
def test_callback_http_cannot_borrow_action_but_click_resuming_after_message_can(
        style, background_fetch, foreground_fetch):
    with SocketPeer() as peer, opened(peer) as (support, ctx):
        assert attempt(ctx, peer.socket) == 'open'
        ctx.page.evaluate("""([style, bg, fg]) => {
            window.received = {};
            const read = async () => (await (await fetch('/api/read', {cache: 'no-store'})).json()).serial;
            document.querySelector('#go').onclick = async () => {
                let signal;
                const notified = new Promise(resolve => {signal = resolve});
                const message = async () => {
                    await Promise.resolve();
                    if (bg) received.fromMessage = await read();
                    signal();
                };
                if (style === 'property') lastSocket.onmessage = message;
                else lastSocket.addEventListener('message', message, {once: true});
                lastSocket.send('read');
                await notified;
                if (fg) received.fromClick = await read();
                received.done = true;
            };
        }""", [style, background_fetch, foreground_fetch])
        p = permit('click')
        ev = support.perform(ctx, p, selector='#go').evidence
        drain = support.perform(ctx, permit('click'), selector='#idle').evidence
        actual = ctx.page.evaluate('received')
        assert actual['done'] and peer.echoes == [b'read']
        primary = [t.response.json['serial'] for t in ev.traffic]
        diagnostics = ev.diagnostic_recorded + drain.diagnostic_recorded
        assert primary == ([actual['fromClick']] if foreground_fetch else [])
        assert [r.json['serial'] for r in diagnostics] == ([actual['fromMessage']] if background_fetch else [])
        assert all(r.step_id is None for r in diagnostics)
        assert all(t.action_id == p.action_id and t.response.step_id == p.step_id for t in ev.traffic)
        assert not drain.traffic and sorted(primary + [r.json['serial'] for r in diagnostics]) == peer.http_replies


def test_background_only_http_does_not_pass_the_declared_click_or_publish_a_recording(tmp_path):
    declaration = {'schema_version': 1, 'scenario': 'records.read', 'users': ['reader'], 'steps': [
        {'id': 'open', 'do': 'open', 'target': 'page'},
        {'id': 'read', 'do': 'click', 'target': 'go', 'expect': {
            'request': {'method': 'GET', 'path': ['records', 'read']},
            'response': [{'check': 'status_equals', 'value': 200}]}}]}
    path = tmp_path / 'read.yaml'
    path.write_text(yaml.safe_dump(declaration))
    with SocketPeer() as peer:
        peer.page += b"""<script>
        const ws = new WebSocket('ws://' + location.host + '/socket');
        const ready = new Promise(resolve => ws.onopen = resolve);
        let received; const response = new Promise(resolve => received = resolve);
        ws.onmessage = async () => received(await (await fetch('/api/read')).json());
        document.querySelector('#go').onclick = async () => {await ready; ws.send('read'); await response};
        </script>"""
        driver = ScenarioDriver(peer)
        driver.browser = BrowserSupport(peer.url, lambda _: {}, timeout_ms=12000, network_policy=BrowserNetworkPolicy(
            api_endpoints=(ApiEndpoint(peer.url, '/api', 'records'),),
            credential_origins=(peer.url,), background_websockets=(BackgroundWebSocket('/socket'),)))
        adapters = Adapters(Auth(), None, None, driver, InMemoryRecorder,
            lambda action: ports.RequestSpec(action.method, action.path, action.body), NoResponse())
        try:
            report = run_scenario(path, adapters, projections=('e2e',))
            assert peer.http_replies == [1] and peer.echoes == [b'read']
            assert [s.status for s in report.domains[0].steps] == ['COMPLETED', 'ERROR']
            assert report.domains[0].steps[-1].detail == 'declared UI request missing or ambiguous among associated traffic'
            assert not report.passed and not report.domains[0].provider_recordings
            assert not driver.evidence[-1].traffic and peer.disconnected.wait(2)
        finally:
            for ctx in driver.contexts:
                driver.browser.close(ctx)
