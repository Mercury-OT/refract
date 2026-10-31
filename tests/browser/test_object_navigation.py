"""Actual Chromium document association; no URL/timing-only credit."""
from dataclasses import replace
import json

import pytest

from refracto import ports
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport, ObjectTarget
from tests.browser.test_multi_origin_transport import Peer
from tests.browser.test_support import permit


@pytest.fixture
def navigation_lab():
    resources = []

    def create(*, native=False, mode='live', form='anchor', script='', destination_script='',
               destination_type='text/html', destination_status=200, mock_plan=None):
        peer = Peer()
        handler = peer.server.RequestHandlerClass
        original = handler.handle_request

        def respond(request):
            if request.path not in {'/editor/22', '/other'}:
                return original(request)
            peer.requests.append({'method': request.command, 'path': request.path,
                                  'headers': dict(request.headers), 'body': b''})
            body = ('<!doctype html><h1>Editor</h1><input id="name">'
                    '<button id="save">Save</button><script>'
                    "save.onclick=()=>fetch('/api/save');" + destination_script + '</script>').encode()
            request.send_response(destination_status)
            request.send_header('Content-Type', destination_type)
            request.send_header('Content-Length', str(len(body)))
            if destination_status == 302:
                request.send_header('Location', '/other')
            request.end_headers()
            try:
                request.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        handler.handle_request = respond
        control = ('<a class="edit" href="/editor/22"><span>Edit</span></a>' if form == 'anchor'
                   else '<button class="edit"><span>Edit</span></button>')
        page_script = ("document.querySelector('.edit').onclick=()=>location.href='/editor/22';"
                       if form == 'script' else '')
        peer.page = ('<!doctype html><section class="record"><a href="/records/22">Identity</a>'
                     + control + '</section><script>' + page_script + script + '</script>').encode()
        policy = BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(peer.url, '/api', 'api'),)) if native else None
        support = BrowserSupport(peer.url, lambda p: {'title': p.locator('h1').text_content()}
                                 if p.locator('h1').count() else {}, network_policy=policy)
        context = support.open(mode, mock_plan=mock_plan)
        resources.append((peer, support, context))
        support.perform(context, permit('open', mode=mode), url=peer.url + '/')
        return peer, support, context

    yield create
    for peer, support, context in reversed(resources):
        support.close(context)
        support.close(context)
        peer.close()


def scoped(support, context):
    return support.perform(context, replace(permit(mode=context.mode), object_id=22),
                           object_target=ObjectTarget('.record', '.edit',
                               "row => Number(new URL(row.querySelector('a').href).pathname.split('/').pop())")).evidence


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('mode', ['live', 'mock'])
@pytest.mark.parametrize('form', ['anchor', 'script'])
def test_document_navigation_retains_actual_receipt_and_next_action(navigation_lab, native, mode, form):
    fixture = ports.MockResponse(fixture_id='save', source='neutral fixture', method='GET',
                                 path='api/save', response={'saved': True})
    peer, support, context = navigation_lab(native=native, mode=mode, form=form,
                                            mock_plan=[fixture] if mode == 'mock' else None)
    browser_context = context.browser_context
    observed_clicks = []
    context.page.expose_function('countClick', lambda: observed_clicks.append(1))
    context.page.evaluate("document.addEventListener('click', () => { void countClick(); })")
    evidence = scoped(support, context)
    assert evidence.object_selection == ports.UiObjectSelection(object_id=22, object_matches=1, control_matches=1)
    assert evidence.traffic == [] and evidence.rendered == {'title': 'Editor'}
    assert observed_clicks == [1] and context.browser_context is browser_context
    assert sum(r['path'] == '/editor/22' for r in peer.requests) == 1
    support.perform(context, permit('fill', value='changed', mode=mode), selector='#name')
    saved = support.perform(context, permit(mode=mode), selector='#save').evidence
    assert len(saved.traffic) == 1 and saved.traffic[0].request.path == 'api/save'
    assert sum(r['path'] == '/api/save' for r in peer.requests) == (1 if mode == 'live' else 0)


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('script', [
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();setTimeout(()=>location.href='/editor/22',0)}",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();Promise.resolve().then(()=>location.href='/editor/22')}",
    "document.querySelector('.edit').onclick=async e=>{e.preventDefault();await Promise.resolve();location.href='/editor/22'}",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();const a=document.createElement('a');a.href='/editor/22';a.click()}",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();const b=document.createElement('button');b.onclick=()=>location.href='/editor/22';b.click()}",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();location.href='/editor/22';location.href='/other'}",
    "navigation.addEventListener('navigate', e=>e.preventDefault())",
    "document.querySelector('.edit').onclick=e=>{window.__refractBrowser.errors.push('private-error')}",
    "document.querySelector('.edit').onclick=e=>new Promise(()=>{})",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();location.href='/editor/22'};document.addEventListener('click',()=>new Promise(()=>{}))",
])
def test_unsupported_or_incomplete_navigation_never_passes(navigation_lab, native, script):
    peer, support, context = navigation_lab(native=native, script=script)
    if "navigation.addEventListener" in script:
        support._timeout_ms = 300
    with pytest.raises(RuntimeError) as error:
        scoped(support, context)
    assert context.closed and 'private-error' not in str(error.value)
    assert context.navigation.active['selection'] is not None


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('status,kind', [(404, 'text/html'), (200, 'application/json'), (302, 'text/html')])
def test_non_success_html_and_redirects_fail(navigation_lab, native, status, kind):
    _, support, context = navigation_lab(native=native, destination_status=status, destination_type=kind)
    with pytest.raises(RuntimeError):
        scoped(support, context)
    assert context.closed


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('mode', ['live', 'mock'])
def test_bootstrap_request_is_background_never_click_evidence(navigation_lab, native, mode):
    fixture = ports.MockResponse(fixture_id='startup', source='neutral fixture', method='GET',
                                 path='api/startup', response={'ready': True})
    peer, support, context = navigation_lab(native=native, mode=mode,
        destination_script="fetch('/api/startup')", mock_plan=[fixture] if mode == 'mock' else None)
    evidence = scoped(support, context)
    assert evidence.traffic == [] and evidence.object_selection.object_id == 22
    assert context.page.evaluate('window.__refractBrowser.armed') is None
    assert sum(r['path'] == '/api/startup' for r in peer.requests) == (1 if mode == 'live' else 0)


@pytest.mark.parametrize('native', [False, True])
def test_missing_bootstrap_mock_never_falls_through(navigation_lab, native):
    peer, support, context = navigation_lab(native=native, mode='mock', destination_script="fetch('/api/startup')")
    with pytest.raises(RuntimeError):
        scoped(support, context)
    assert context.closed and not any(r['path'] == '/api/startup' for r in peer.requests)


@pytest.mark.parametrize('native', [False, True])
def test_new_document_receipt_cannot_replay_source(navigation_lab, native):
    payload = json.dumps({'kind': 'selection', 'action': 'not-current',
                          'selection': {'object_id': 22, 'object_matches': 1, 'control_matches': 1}})
    _, support, context = navigation_lab(native=native,
        destination_script='__refractNavigationReceipt('+json.dumps(payload)+')')
    with pytest.raises(RuntimeError):
        scoped(support, context)
    assert context.closed


@pytest.mark.parametrize('native', [False, True])
def test_same_document_anchor_and_history_keep_existing_behavior(navigation_lab, native):
    _, support, context = navigation_lab(native=native,
        script="document.querySelector('.edit').href='#editor'")
    assert scoped(support, context).object_selection.object_id == 22
    assert context.page.url.endswith('#editor')


def test_source_receipt_requires_default_world_unique_context_and_active_action():
    from copy import deepcopy
    from types import SimpleNamespace
    from refracto_browser._navigation import NavigationCollector

    original = {'id': 3, 'unique': 'old-document', 'frame': 'main-frame', 'default': True, 'alive': True}
    for change in ('unknown', 'world', 'frame', 'reused-id', 'dead', 'action', 'duplicate'):
        collector = NavigationCollector.__new__(NavigationCollector)
        collector.context = SimpleNamespace(errors=[])
        collector.contexts = {3: deepcopy(original)}
        collector.active = {'permit': SimpleNamespace(action_id='active', object_id=22),
                            'source': deepcopy(original), 'selection': None, 'navigation': None}
        payload = {'kind': 'selection', 'action': 'active',
                   'selection': {'object_id': 22, 'object_matches': 1, 'control_matches': 1}}
        if change == 'unknown':
            collector.contexts.clear()
        elif change == 'world':
            collector.contexts[3]['default'] = False
        elif change == 'frame':
            collector.contexts[3]['frame'] = 'other-frame'
        elif change == 'reused-id':
            collector.contexts[3]['unique'] = 'new-document'
        elif change == 'dead':
            collector.contexts[3]['alive'] = False
        elif change == 'action':
            payload['action'] = 'completed-action'
        elif change == 'duplicate':
            collector.active['selection'] = deepcopy(payload['selection'])
        collector._binding({'name': '__refractNavigationReceipt', 'executionContextId': 3,
                            'payload': json.dumps(payload)})
        assert collector.context.errors == ['browser navigation evidence failed'], change


def test_outstanding_old_action_ledger_cannot_be_erased_by_new_context():
    from copy import deepcopy
    from types import SimpleNamespace
    from refracto_browser._navigation import NavigationCollector

    collector = NavigationCollector.__new__(NavigationCollector)
    source = {'id': 3, 'unique': 'old-document', 'frame': 'main-frame', 'default': True, 'alive': True}
    collector.context = SimpleNamespace(errors=[])
    collector.contexts, collector.current = {3: deepcopy(source)}, deepcopy(source)
    collector.active = {'permit': SimpleNamespace(action_id='active'), 'source': deepcopy(source),
                        'selection': {'object_id': 22}, 'navigation': {'form': 'script'}, 'pending': 0}
    collector._binding({'name': '__refractNavigationReceipt', 'executionContextId': 3,
                        'payload': json.dumps({'kind': 'state', 'action': 'active', 'pending': 1, 'errors': False})})
    collector._cleared({})
    assert collector.active['retired'] is True
    assert collector.context.errors == ['browser navigation evidence failed']


@pytest.mark.parametrize('native', [False, True])
def test_late_navigation_during_snapshot_invalidates_receipt(navigation_lab, native):
    _, support, context = navigation_lab(native=native)
    def read(page):
        page.evaluate("location.href='/other'")
        page.wait_for_load_state('domcontentloaded')
        return {'title': 'Editor'}
    support._read_rendered = read
    with pytest.raises(RuntimeError):
        scoped(support, context)
    assert context.closed


@pytest.mark.parametrize('native', [False, True])
def test_missing_receipt_channel_fails_without_error_recursion(navigation_lab, native):
    _, support, context = navigation_lab(native=native,
        script="document.addEventListener('pointerdown',()=>{delete window.__refractNavigationReceipt})")
    with pytest.raises(RuntimeError) as error:
        scoped(support, context)
    assert context.closed and 'call stack' not in str(error.value).lower()
    assert context.navigation.active['selection'] is None


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('script', [
    "document.querySelector('.edit').target='_blank'",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();window.open('about:blank')}",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();const f=document.createElement('iframe');f.srcdoc='frame';document.body.append(f)}",
    "document.querySelector('.edit').onclick=e=>{e.preventDefault();const f=document.createElement('form');f.action='/editor/22';document.body.append(f);f.submit()}",
])
def test_other_target_and_form_transitions_cannot_claim_navigation(navigation_lab, native, script):
    _, support, context = navigation_lab(native=native, script=script)
    with pytest.raises(RuntimeError):
        scoped(support, context)
    assert context.closed and context.navigation.active['selection'] is not None


@pytest.mark.parametrize('native', [False, True])
def test_cross_origin_navigation_is_blocked_before_destination_request(navigation_lab, native):
    other = Peer()
    try:
        _, support, context = navigation_lab(native=native,
            script="document.querySelector('.edit').href=" + json.dumps(other.url + '/editor/22'))
        with pytest.raises(RuntimeError):
            scoped(support, context)
        assert context.closed and other.requests == []
    finally:
        other.close()


@pytest.mark.parametrize('native', [False, True])
def test_receipt_error_delivered_during_final_browser_read_cannot_pass(navigation_lab, native, monkeypatch):
    _, support, context = navigation_lab(native=native)
    state = {'rendered': False, 'checks': 0, 'injected': False}
    original_read = support._read_rendered
    original_evaluate = context.page.evaluate

    def read(page):
        rendered = original_read(page)
        state['rendered'] = True
        return rendered

    def evaluate(expression, *args, **kwargs):
        result = original_evaluate(expression, *args, **kwargs)
        if state['rendered'] and expression == '() => window.__refractBrowser?.errors || []':
            state['checks'] += 1
            if state['checks'] == 2:
                # Deterministic CDP delivery inside the last _check() browser
                # read: valid old transition, but a new-document source tries
                # to replay its selection before receipt finalization.
                collector = context.navigation
                collector._binding({'name': '__refractNavigationReceipt',
                    'executionContextId': collector.current['id'],
                    'payload': json.dumps({'kind': 'selection',
                        'action': collector.active['permit'].action_id,
                        'selection': {'object_id': 22, 'object_matches': 1, 'control_matches': 1}})})
                state['injected'] = True
        return result

    support._read_rendered = read
    monkeypatch.setattr(context.page, 'evaluate', evaluate)
    with pytest.raises(RuntimeError):
        scoped(support, context)
    assert state['injected'] and context.closed
    assert context.errors == ['browser navigation evidence failed']
