"""Actual Chromium Enter delivery, focus ownership, and request causality.

These neutral HTTP probes preserve the feasibility controls: keyboard/property
callbacks, native await, same-path background work, and nested synthetic events.
"""
import json
from dataclasses import asdict, replace
import time
from uuid import uuid4

import pytest

from refracto import ports
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport, ObjectTarget
from tests.browser.test_multi_origin_transport import Peer


def permit(action="press", *, mode="live", value=None, key=None, object_id=None):
    identity = uuid4().hex
    return ports.UiActionPermit(execution_id="enter-run", action_id=identity,
                                step_id="step-" + identity, mode=mode, action=action,
                                target="neutral", value=value, token=uuid4().hex,
                                key="Enter" if action == "press" and key is None else key,
                                object_id=object_id)


@pytest.fixture
def lab():
    owned = []

    def create(script="", *, markup='<input id="entry"><input id="other"><button id="go">go</button>',
               mode="live", native=True, fixtures=None, rendered=None):
        app, api = Peer(), Peer()
        destination = api.url if native else app.url
        app.page = (markup + '<script>const entry=document.querySelector("#entry"),'
                    'other=document.querySelector("#other"),go=document.querySelector("#go");'
                    'window.events=[];'
                    'for(const type of ["keydown","keypress","keyup","focus","blur","click"])'
                    'document.addEventListener(type,e=>events.push({type:e.type,key:e.key,'
                    'trusted:e.isTrusted,target:e.target.id}),true);'
                    'function send(tag="action"){return fetch(' + json.dumps(destination + '/api/echo') +
                    ',{method:"POST",headers:{"Content-Type":"text/plain"},'
                    'body:JSON.stringify({tag})}).then(r=>r.json())};' + script + '</script>').encode()
        support = BrowserSupport(app.url, rendered or (lambda page: {}), timeout_ms=5000,
                                 network_policy=BrowserNetworkPolicy(api_endpoints=(
                                     ApiEndpoint(api.url, '/api', 'records'),)) if native else None)
        context = support.open(mode, mock_plan=fixtures)
        owned.append((support, context, app, api))
        support.perform(context, permit("open", mode=mode), url=app.url + '/')
        return support, context, app, api

    yield create
    for support, context, app, api in owned:
        support.close(context)
        app.close()
        api.close()


def press(support, context, *, selector="#entry"):
    return support.perform(context, permit(mode=context.mode), selector=selector).evidence


def focus(context):
    context.page.locator('#entry').focus()
    context.page.evaluate('events=[]')


def test_one_trusted_pair_and_receipt_without_request_or_focus_repair(lab, monkeypatch):
    support, context, _, api = lab()
    focus(context)
    # Any locator-based interaction would be an implicit focus/selection repair.
    monkeypatch.setattr(context.page, 'locator', lambda *_: pytest.fail('locator interaction'))
    evidence = press(support, context)
    assert asdict(evidence.key_press) == dict(key='Enter', target_matches=1, focused=True,
                                            keydown_count=1, keyup_count=1)
    assert evidence.traffic == [] and api.requests == []
    assert context.page.evaluate('events') == [
        {'type': kind, 'key': 'Enter', 'trusted': True, 'target': 'entry'}
        for kind in ('keydown', 'keypress', 'keyup')]


@pytest.mark.parametrize('script', [
    "entry.addEventListener('keydown',()=>send())",
    "entry.onkeydown=()=>send()",
    "entry.onkeyup=()=>send()",
    "document.addEventListener('keyup',e=>e.target===entry&&send())",
    "entry.onkeypress=()=>send()",
    "entry.onkeydown=()=>Promise.resolve().then(()=>send())",
    "entry.onkeyup=async()=>{await Promise.resolve();await send()}",
    "document.addEventListener('keydown',async e=>{if(e.target===entry){await Promise.resolve();await send()}})",
    "async function inner(){await Promise.resolve();await send()};entry.onkeydown=async()=>{await Promise.resolve();await inner()}",
])
def test_handler_forms_and_supported_async_ancestry(lab, script):
    support, context, _, api = lab(script)
    focus(context)
    evidence = press(support, context)
    assert len(evidence.traffic) == 1
    traffic = evidence.traffic[0]
    assert traffic.action_id == evidence.action_id
    assert traffic.request.body == {'tag': 'action'}
    assert traffic.request.path == 'records/echo'
    assert traffic.browser_identity == traffic.response.browser_identity
    assert len(api.requests) == 1
    assert not any(name.lower().startswith('x-refract-') for name in api.requests[0]['headers'])


@pytest.mark.parametrize('event', ['keydown', 'keyup'])
def test_parsed_inline_native_await_handler(lab, event):
    markup = '<input id="entry" on' + event + '=\"return (async()=>{await Promise.resolve();await send()})()\"><input id="other">'
    support, context, _, api = lab(markup=markup)
    focus(context)
    evidence = press(support, context)
    assert len(evidence.traffic) == len(api.requests) == 1


@pytest.mark.parametrize('mode,native', [('live', False), ('mock', False), ('mock', True)])
def test_legacy_transport_and_explicit_mock(lab, mode, native):
    fixtures = [ports.MockResponse(fixture_id='enter-fixture', source='neutral', method='POST',
                                  path='records/echo' if native else 'api/echo',
                                  response={'success': True},
                                  response_headers={'access-control-allow-origin': '*'})] if mode == 'mock' else None
    support, context, app, api = lab("entry.onkeyup=()=>send()", mode=mode, native=native, fixtures=fixtures)
    focus(context)
    evidence = press(support, context)
    assert len(evidence.traffic) == 1
    assert evidence.key_press.key == 'Enter'
    if mode == 'mock':
        assert evidence.traffic[0].mock_fixture_id == 'enter-fixture'
        assert len(evidence.mock_recordings) == 1
        assert api.requests == [] and not any(r['path'] == '/api/echo' for r in app.requests)


@pytest.mark.parametrize('markup,selector', [
    ('<input id="other">', '#entry'),
    ('<input id="entry"><input id="other">', 'input'),
    ('<input id="entry" disabled><input id="other">', '#entry'),
    ('<input id="entry" aria-disabled="true">', '#entry'),
    ('<div aria-disabled="true"><input id="entry"></div>', '#entry'),
    ('<input id="entry" aria-readonly="true">', '#entry'),
    ('<div inert><input id="entry"></div>', '#entry'),
    ('<fieldset disabled><input id="entry"></fieldset>', '#entry'),
    ('<input id="entry" readonly>', '#entry'),
    ('<input id="entry" type="number">', '#entry'),
    ('<input id="entry" type="password">', '#entry'),
    ('<textarea id="entry"></textarea>', '#entry'),
    ('<div id="entry" contenteditable>text</div>', '#entry'),
    ('<button id="entry">go</button>', '#entry'),
    ('<input id="entry" style="display:none">', '#entry'),
])
def test_unusable_target_rejects_before_sending_key(lab, monkeypatch, markup, selector):
    support, context, _, api = lab(markup=markup)
    context.page.evaluate("document.querySelector('#entry')?.focus()")
    sent = []
    monkeypatch.setattr(context.page.keyboard, 'down', lambda key: sent.append(key))
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context, selector=selector)
    assert sent == [] and api.requests == [] and context.closed


def test_wrong_focus_rejects_before_sending_key(lab, monkeypatch):
    support, context, _, api = lab("other.onkeydown=()=>send('wrong')")
    context.page.locator('#other').focus()
    sent = []
    monkeypatch.setattr(context.page.keyboard, 'down', lambda key: sent.append(key))
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context)
    assert sent == [] and api.requests == []


@pytest.mark.parametrize('key', [None, '', 'Tab', 'enter', 'Control+Enter', ['Enter'], 13, True])
def test_invalid_key_rejected_without_browser_delivery(lab, monkeypatch, key):
    support, context, _, _ = lab()
    focus(context)
    monkeypatch.setattr(context.page.keyboard, 'down', lambda _: pytest.fail('unexpected key'))
    with pytest.raises(ValueError, match='key'):
        support.perform(context, replace(permit(), key=key), selector='#entry')


@pytest.mark.parametrize('fault', ['synthetic', 'missing_up', 'wrong_key', 'repeat'])
def test_invalid_or_synthetic_delivery_cannot_supply_receipt(lab, monkeypatch, fault):
    support, context, _, _ = lab()
    focus(context)
    down = context.page.keyboard.down
    if fault == 'synthetic':
        for method, event in [('down', 'keydown'), ('up', 'keyup')]:
            monkeypatch.setattr(context.page.keyboard, method,
                                lambda _, event=event: context.page.evaluate(
                                    "type=>entry.dispatchEvent(new KeyboardEvent(type,{key:'Enter',code:'Enter',bubbles:true}))", event))
    elif fault == 'missing_up':
        monkeypatch.setattr(context.page.keyboard, 'up', lambda _: None)
    elif fault == 'wrong_key':
        monkeypatch.setattr(context.page.keyboard, 'down', lambda _: down('Escape'))
    else:
        def twice(key):
            down(key)
            down(key)
        monkeypatch.setattr(context.page.keyboard, 'down', twice)
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context)
    assert context.closed


@pytest.mark.parametrize('change', [
    "entry.replaceWith(entry.cloneNode())",
    "entry.after(entry.cloneNode())",
    "entry.readOnly=true",
    "entry.disabled=true",
    "other.focus()",
])
def test_dispatch_time_identity_and_focus_are_revalidated(lab, monkeypatch, change):
    support, context, _, api = lab("entry.onkeydown=()=>send();other.onkeydown=()=>send('wrong')")
    focus(context)
    down = context.page.keyboard.down

    def race(key):
        context.page.evaluate(change)
        down(key)

    monkeypatch.setattr(context.page.keyboard, 'down', race)
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context)
    assert api.requests == [] and context.closed


@pytest.mark.parametrize('phase', ['keydown', 'keyup'])
@pytest.mark.parametrize('handler', ["()=>send('focus')", "async()=>{await Promise.resolve();await send('focus')}"])
def test_transient_focus_displacement_invalidates_action(lab, phase, handler):
    script = "other.onfocus=" + handler + ";entry.on" + phase + "=()=>{other.focus();entry.focus();return send()}"
    support, context, _, _ = lab(script)
    focus(context)
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context)
    assert context.closed


def test_focus_change_during_final_snapshot_cannot_escape_receipt(lab):
    def rendered(page):
        if page.evaluate("window.__refractBrowser?.armed?.type === 'press'"):
            page.evaluate('other.focus();entry.focus()')
        return {}

    support, context, _, _ = lab(rendered=rendered)
    focus(context)
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context)


def test_idle_host_error_arriving_during_initial_read_blocks_next_action(lab, monkeypatch):
    support, context, _, _ = lab()
    focus(context)
    press(support, context)
    check = support._check

    def delayed_error(ctx):
        check(ctx)
        ctx.errors.append('browser keyboard transition is unsupported')

    monkeypatch.setattr(support, '_check', delayed_error)
    monkeypatch.setattr(context.page, 'locator', lambda *_: pytest.fail('next action dispatched'))
    with pytest.raises(RuntimeError, match='browser action'):
        support.perform(context, permit('click'), selector='#go')


@pytest.mark.parametrize('failure', ['host_error', 'deadline'])
def test_final_receipt_read_rechecks_host_errors_and_deadline(lab, monkeypatch, failure):
    from refracto_browser._key_press import PinnedKeyPress

    support, context, _, _ = lab()
    focus(context)
    receipt = PinnedKeyPress.receipt

    def delayed_result(pinned):
        result = receipt(pinned)
        if failure == 'host_error':
            context.errors.append('browser keyboard transition is unsupported')
        else:
            context.deadline = time.monotonic() - 1
        return result

    monkeypatch.setattr(PinnedKeyPress, 'receipt', delayed_result)
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context)
    assert context.closed


@pytest.mark.parametrize('nested', [
    "other.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter'}))",
    "other.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter'}))",
    "other.dispatchEvent(new Event('change'))",
    "other.click()",
])
def test_nested_inline_synthetic_native_await_is_diagnostic(lab, nested):
    markup = '<input id="entry"><input id="other" ' + ' '.join(
        'on' + name + '=\"(async()=>{await Promise.resolve();await send(\'synthetic\')})()\"'
        for name in ('keydown', 'keyup', 'change', 'click')) + '><button id="go">go</button>'
    support, context, _, api = lab("entry.onkeydown=async()=>{" + nested + ";await send()}", markup=markup)
    focus(context)
    first = press(support, context)
    context.page.wait_for_timeout(50)
    second = support.perform(context, permit('click'), selector='#go').evidence
    assert [t.request.body for t in first.traffic] == [{'tag': 'action'}]
    assert second.traffic == []
    diagnostics = first.diagnostic_recorded + second.diagnostic_recorded
    assert [r.request.body for r in diagnostics] == [{'tag': 'synthetic'}]
    assert diagnostics[0].step_id is None
    assert len(api.requests) == 2


def test_retained_trusted_event_redispatch_has_no_action_origin(lab):
    script = """let replayed=false;
    entry.onkeyup=async event=>{
      if(replayed)return send('synthetic');
      replayed=true;
      await new Promise(resolve=>setTimeout(resolve,0));
      entry.dispatchEvent(event);return send();
    }"""
    support, context, _, api = lab(script)
    focus(context)
    first = press(support, context)
    context.page.wait_for_timeout(50)
    second = support.perform(context, permit('click'), selector='#go').evidence
    assert [t.request.body for t in first.traffic] == [{'tag': 'action'}]
    assert second.traffic == []
    assert [r.request.body for r in first.diagnostic_recorded + second.diagnostic_recorded] == [{'tag': 'synthetic'}]
    assert len(api.requests) == 2


@pytest.mark.parametrize('schedule', [
    "setTimeout(()=>helper('background'),0);await helper('action')",
    "const shared=new Promise(r=>setTimeout(r,10));setTimeout(()=>helper('background',shared),0);await helper('action',shared)",
])
def test_same_path_timer_and_shared_promise_background_cannot_substitute(lab, schedule):
    script = "async function helper(tag,gate=Promise.resolve()){await gate;await send(tag)};entry.onkeydown=async()=>{" + schedule + "}"
    support, context, _, api = lab(script)
    focus(context)
    first = press(support, context)
    context.page.wait_for_timeout(50)
    second = support.perform(context, permit('click'), selector='#go').evidence
    assert [t.request.body for t in first.traffic] == [{'tag': 'action'}]
    assert second.traffic == []
    diagnostics = first.diagnostic_recorded + second.diagnostic_recorded
    assert [r.request.body for r in diagnostics] == [{'tag': 'background'}]
    assert diagnostics[0].step_id is None
    assert len(api.requests) == 2


def test_both_key_phases_keep_two_requests_separate(lab):
    support, context, _, api = lab("entry.onkeydown=()=>send('down');entry.onkeyup=()=>send('up')")
    focus(context)
    evidence = press(support, context)
    assert [t.request.body for t in evidence.traffic] == [{'tag': 'down'}, {'tag': 'up'}]
    assert len({t.request_id for t in evidence.traffic}) == len(api.requests) == 2


@pytest.mark.parametrize('script', [
    "entry.onkeydown=()=>{location.href='/?next'}",
    "entry.onkeyup=async()=>{await Promise.resolve();location.href='/?next'}",
    "entry.onkeyup=()=>{setTimeout(()=>location.href='/?next',0)}",
    "entry.onkeydown=()=>{window.open('about:blank')}",
    "entry.onkeydown=()=>{const frame=document.createElement('iframe');document.body.append(frame)}",
    "entry.onkeydown=()=>{const form=document.createElement('form');form.action='/?next';document.body.append(form);form.submit()}",
    "entry.onkeydown=()=>{const a=document.createElement('a');a.href='data:text/plain,neutral';a.download='neutral';a.click()}",
])
def test_unsupported_transitions_fail(lab, script):
    support, context, _, _ = lab(script)
    focus(context)
    with pytest.raises(RuntimeError, match='browser action'):
        press(support, context)
    assert context.closed


def test_native_form_click_handler_is_not_submit_evidence(lab):
    markup = '<form onsubmit="event.preventDefault()"><input id="entry"><button id="go">go</button></form>'
    support, context, _, api = lab("go.onclick=()=>send('activation').then(()=>window.done=true)", markup=markup)
    focus(context)
    evidence = press(support, context)
    assert evidence.traffic == []
    context.page.wait_for_function('window.done === true')
    assert context.traffic == []
    assert len(api.requests) == 1


def test_post_press_idle_navigation_rejected_before_next_action(lab):
    support, context, _, _ = lab("entry.onkeyup=()=>{window.later=()=>location.href='/?next'}")
    focus(context)
    assert press(support, context).key_press is not None
    context.page.evaluate('later()')
    context.page.wait_for_timeout(30)
    with pytest.raises(RuntimeError, match='browser action'):
        support.perform(context, permit('click'), selector='#go')
    assert context.closed


@pytest.mark.parametrize('action', ['fill', 'click', 'open', 'scoped-click'])
def test_next_explicit_action_preserves_existing_behavior(lab, action):
    markup = '<input id="entry"><input id="other"><div class="record" data-id="one"><a id="go" href="/?next">go</a></div>'
    support, context, app, _ = lab(markup=markup)
    focus(context)
    assert press(support, context).key_press is not None
    if action == 'open':
        evidence = support.perform(context, permit('open'), url=app.url + '/?next').evidence
    elif action == 'scoped-click':
        mapping = ObjectTarget('.record', 'a', '(row)=>row.dataset.id')
        evidence = support.perform(context, permit('click', object_id='one'), object_target=mapping).evidence
        assert evidence.object_selection.object_id == 'one'
    else:
        evidence = support.perform(context, permit(action, value='next' if action == 'fill' else None),
                                   selector='#entry' if action == 'fill' else '#go').evidence
    assert evidence.key_press is None


def test_press_receipts_and_action_origins_are_fresh(lab):
    support, context, _, api = lab("entry.onkeyup=()=>send()")
    focus(context)
    first, second = press(support, context), press(support, context)
    assert first.key_press is not second.key_press
    assert first.action_id != second.action_id
    assert first.traffic[0].action_id == first.action_id
    assert second.traffic[0].action_id == second.action_id
    assert len(api.requests) == 2
