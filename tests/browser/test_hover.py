"""Real pointer delivery and diagnostic-only hover traffic in Chromium."""
import json
from dataclasses import asdict, replace
import time
from uuid import uuid4

import pytest

from refracto import ports
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport
from tests.browser.test_multi_origin_transport import Peer


RECEIPT = {"target_matches": 1, "pointer_on_target": True}
MARKUP = '<input id="focus"><div id="trigger"><span>Menu</span><div id="menu">Archived records</div></div><button id="go">Read</button>'
STYLE = '''<style>#trigger{position:absolute;left:80px;top:80px;width:160px;height:60px;background:#ddd}
#menu{position:absolute;top:60px;display:none}#go{position:absolute;left:350px;top:80px}
.cover{position:absolute;left:70px;top:70px;width:200px;height:100px;background:#f00;z-index:10}</style>'''


def permit(action="hover", *, mode="live", value=None, object_id=None, key=None):
    identity = uuid4().hex
    return ports.UiActionPermit(execution_id="hover-run", action_id=identity,
                                step_id="step-" + identity, mode=mode, action=action,
                                target="neutral", value=value, token=uuid4().hex,
                                object_id=object_id, key=key)


@pytest.fixture
def lab():
    owned = []

    def create(script="", *, markup=MARKUP, style=STYLE, native=True, mode="live",
               fixtures=None, rendered=None):
        app, api = Peer(), Peer()
        destination = api.url if native else app.url
        app.page = (style + markup + '<script>const trigger=document.querySelector("#trigger"),'
                    'menu=document.querySelector("#menu"),go=document.querySelector("#go");'
                    'window.events=[];window.done=[];'
                    'for(const type of ["mousemove","mouseenter","click","focus","input"])'
                    'document.addEventListener(type,e=>events.push({type,trusted:e.isTrusted,target:e.target.id}),true);'
                    'function send(tag="hover"){return fetch(' + json.dumps(destination + '/api/echo') +
                    ',{method:"POST",headers:{"Content-Type":"text/plain"},body:JSON.stringify({tag})})'
                    '.then(r=>r.json()).finally(()=>done.push(tag))};' + script + '</script>').encode()
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


def hover(support, context, *, selector="#trigger"):
    return support.perform(context, permit(mode=context.mode), selector=selector).evidence


@pytest.mark.parametrize("kind", ["css", "javascript"])
def test_real_hover_reveals_menu_without_click_focus_scroll_or_repair(lab, monkeypatch, kind):
    script = "trigger.onmouseenter=()=>menu.style.display='block'" if kind == "javascript" else ""
    style = STYLE + ('<style>#trigger:hover #menu{display:block}</style>' if kind == "css" else '')
    support, context, _, api = lab(script, style=style)
    context.page.locator('#focus').focus()
    context.page.evaluate('events=[]')
    assert context.page.locator('#menu').is_visible() is False
    move = context.page.mouse.move
    moves = []

    def record_move(*args, **kwargs):
        moves.append((args, kwargs))
        return move(*args, **kwargs)

    monkeypatch.setattr(context.page.mouse, 'move', record_move)
    monkeypatch.setattr(context.page.mouse, 'click', lambda *_a, **_k: pytest.fail('hidden click'))
    monkeypatch.setattr(context.page, 'locator', lambda *_a, **_k: pytest.fail('locator repair'))
    evidence = hover(support, context)
    assert asdict(evidence.hover) == RECEIPT
    assert evidence.traffic == [] and api.requests == []
    assert len(moves) == 1
    assert context.page.evaluate('getComputedStyle(menu).display') == 'block'
    assert context.page.evaluate('document.activeElement.id') == 'focus'
    assert context.page.evaluate('[scrollX,scrollY]') == [0, 0]
    assert not any(e['type'] in {'click', 'focus', 'input'} for e in context.page.evaluate('events'))
    assert any(e['type'] == 'mousemove' and e['trusted'] for e in context.page.evaluate('events'))


def test_already_positioned_pointer_has_fresh_receipt_without_fabricated_enter(lab):
    support, context, _, _ = lab()
    first = hover(support, context)
    context.page.evaluate('events=[]')
    second = hover(support, context)
    assert asdict(first.hover) == asdict(second.hover) == RECEIPT
    assert first.hover is not second.hover and first.action_id != second.action_id
    assert not any(e['type'] == 'mouseenter' for e in context.page.evaluate('events'))
    assert any(e['type'] == 'mousemove' and e['trusted'] for e in context.page.evaluate('events'))


@pytest.mark.parametrize('setup', [
    'trigger.remove()',
    'trigger.style.display="none"',
    'trigger.style.visibility="hidden"',
    'document.body.append(trigger.cloneNode(true))',
    'document.body.insertAdjacentHTML("beforeend", "<div class=cover></div>")',
    'trigger.style.top="3000px"',
    'trigger.style.pointerEvents="none"',
])
def test_unavailable_ambiguous_covered_offscreen_targets_fail_before_movement(lab, monkeypatch, setup):
    support, context, _, api = lab()
    context.page.evaluate('()=>' + '{' + setup + '}')
    support._timeout_ms = 150
    monkeypatch.setattr(context.page.mouse, 'move', lambda *_a, **_k: pytest.fail('action attempted'))
    with pytest.raises(RuntimeError, match='browser action'):
        hover(support, context)
    assert context.closed and api.requests == []


@pytest.mark.parametrize('change', [
    'trigger.replaceWith(trigger.cloneNode(true))',
    'trigger.remove()',
    'trigger.style.left="400px"',
    'document.body.append(trigger.cloneNode(true))',
    'document.body.insertAdjacentHTML("beforeend", "<div class=cover></div>")',
])
def test_pinned_target_cannot_be_reselected_between_selection_and_delivery(lab, monkeypatch, change):
    support, context, _, _ = lab()
    move = context.page.mouse.move

    def mutate_then_move(*args, **kwargs):
        context.page.evaluate('()=>' + '{' + change + '}')
        return move(*args, **kwargs)

    monkeypatch.setattr(context.page.mouse, 'move', mutate_then_move)
    with pytest.raises(RuntimeError, match='browser action'):
        hover(support, context)
    assert context.closed


@pytest.mark.parametrize('change', [
    'trigger.replaceWith(trigger.cloneNode(true))',
    'trigger.style.visibility="hidden"',
    'document.body.append(trigger.cloneNode(true))',
    'document.body.insertAdjacentHTML("beforeend", "<div class=cover></div>")',
])
def test_target_change_during_event_or_snapshot_cannot_escape_receipt(lab, change):
    def rendered(page):
        if page.evaluate('window.__refractBrowser?.armed?.type === "hover"'):
            page.evaluate('()=>' + '{' + change + '}')
        return {}

    support, context, _, _ = lab(rendered=rendered)
    with pytest.raises(RuntimeError, match='browser action'):
        hover(support, context)
    assert context.closed


def test_product_moving_target_during_mouseover_is_not_repaired(lab):
    support, context, _, _ = lab("trigger.onmouseover=()=>trigger.style.left='400px'")
    with pytest.raises(RuntimeError, match='browser action'):
        hover(support, context)


@pytest.mark.parametrize('replacement', ['nothing', 'synthetic'])
def test_missing_trusted_movement_cannot_use_synthetic_or_stale_events(lab, monkeypatch, replacement):
    support, context, _, _ = lab()
    hover(support, context)

    def fake_move(**position):
        if replacement == 'synthetic':
            context.page.evaluate('p=>trigger.dispatchEvent(new MouseEvent("mousemove",{bubbles:true,clientX:p.x,clientY:p.y}))', position)

    monkeypatch.setattr(context.page.mouse, 'move', fake_move)
    with pytest.raises(RuntimeError, match='browser action'):
        hover(support, context)


@pytest.mark.parametrize('script', [
    "trigger.addEventListener('mouseenter',()=>send())",
    "trigger.onmouseover=()=>send()",
    "trigger.onpointerenter=async()=>{await Promise.resolve();await send()}",
    "document.addEventListener('mouseover',e=>e.target.closest('#trigger')&&send())",
    "trigger.onmouseenter=()=>Promise.resolve().then(()=>send())",
    "trigger.onmouseenter=()=>setTimeout(()=>send(),0)",
    "trigger.onmouseenter=()=>{const x=new XMLHttpRequest();x.open('POST','API/api/echo');x.onload=()=>done.push('hover');x.send(JSON.stringify({tag:'hover'}))}",
])
def test_hover_http_is_diagnostic_and_has_no_wire_action_marker(lab, script):
    # The XHR URL is assigned from the public synthetic peer after creation.
    if 'API' in script:
        script = script.replace("'API/api/echo'", "window.destination")
    support, context, _, api = lab(script)
    context.page.evaluate('url=>window.destination=url', api.url + '/api/echo')
    evidence = hover(support, context)
    context.page.wait_for_function('done.includes("hover")')
    context.native.collect(evidence.action_id)
    assert evidence.traffic == [] and context.traffic == []
    assert any(recording.request.path == 'records/echo' for recording in context.diagnostics)
    assert len(api.requests) == 1
    assert not any(name.lower().startswith('x-refract-') for name in api.requests[0]['headers'])


@pytest.mark.parametrize('kind', ['listener', 'property', 'inline'])
def test_deferred_hover_request_during_following_click_never_becomes_click_evidence(lab, kind):
    callback = "async()=>{await pending;await send('hover')}"
    script = "window.release=null;window.pending=new Promise(r=>release=r);go.onclick=()=>{release();return send('click')};"
    markup = MARKUP
    if kind == 'listener':
        script += "trigger.addEventListener('mouseenter'," + callback + ")"
    elif kind == 'property':
        script += "trigger.onmouseenter=" + callback
    else:
        markup = MARKUP.replace('<div id="trigger">', '<div id="trigger" onmouseenter="return (async()=>{await pending;await send(\'hover\')})()">')
    support, context, _, api = lab(script, markup=markup)
    assert hover(support, context).traffic == []
    evidence = support.perform(context, permit('click'), selector='#go').evidence
    context.page.wait_for_function('done.includes("hover") && done.includes("click")')
    context.native.collect(evidence.action_id)
    assert [t.request.body for t in evidence.traffic] == [{'tag': 'click'}]
    assert any(r.request.body == {'tag': 'hover'} for r in context.diagnostics)
    assert len(api.requests) == 2


@pytest.mark.parametrize('native', [False, True])
def test_same_path_hover_request_cannot_rescue_a_click_that_sent_nothing(lab, native):
    support, context, _, _ = lab("trigger.onmouseenter=()=>send();go.onclick=()=>{}", native=native)
    assert hover(support, context).traffic == []
    context.page.wait_for_function('done.includes("hover")')
    evidence = support.perform(context, permit('click'), selector='#go').evidence
    assert evidence.traffic == []


@pytest.mark.parametrize('native', [False, True])
def test_frontend_hover_background_cannot_consume_click_fixture_or_reach_live_api(lab, native):
    fixture = ports.MockResponse(fixture_id='click-fixture', source='neutral', method='POST',
                                path='records/echo' if native else 'api/echo',
                                response={'success': True}, status=200,
                                response_headers={'access-control-allow-origin': '*'})
    support, context, app, api = lab("trigger.onmouseenter=()=>send().catch(()=>{});go.onclick=()=>send('click')",
                                     native=native, mode='mock', fixtures=[fixture])
    evidence = hover(support, context)
    assert evidence.traffic == [] and evidence.mock_recordings == []
    click = support.perform(context, permit('click', mode='mock'), selector='#go').evidence
    assert len(click.mock_recordings) == 1
    assert click.mock_recordings[0].mock_fixture_id == 'click-fixture'
    assert api.requests == []
    assert not any(r['path'].startswith('/api/') for r in app.requests)


@pytest.mark.parametrize('transition', [
    "location.href='/other'",
    "history.pushState({},'', '/other')",
    "window.open('/other')",
    "document.body.insertAdjacentHTML('beforeend','<iframe src=/other></iframe>')",
    "const a=document.createElement('a');a.href='data:text/plain,synthetic';a.download='synthetic.txt';a.click()",
    "document.open();document.write('<p>replacement</p>');document.close()",
])
def test_unsupported_transitions_during_hover_are_visible_errors(lab, transition):
    support, context, _, _ = lab('trigger.onmouseenter=()=>{' + transition + '}')
    with pytest.raises(RuntimeError, match='browser action'):
        hover(support, context)
    assert context.closed


def test_unsupported_idle_gap_transition_blocks_next_authorized_action(lab, monkeypatch):
    support, context, _, _ = lab()
    hover(support, context)
    context.page.evaluate("history.pushState({},'', '/late')")
    monkeypatch.setattr(context.page, 'locator', lambda *_a, **_k: pytest.fail('next action attempted'))
    with pytest.raises(RuntimeError, match='browser action'):
        support.perform(context, permit('click'), selector='#go')
    assert context.closed


@pytest.mark.parametrize('failure', ['host_error', 'deadline'])
def test_final_receipt_rechecks_host_errors_and_budget(lab, monkeypatch, failure):
    from refracto_browser._hover import PinnedHover

    support, context, _, _ = lab()
    receipt = PinnedHover.receipt

    def delayed_receipt(pinned):
        result = receipt(pinned)
        if failure == 'host_error':
            context.errors.append('browser hover transition is unsupported')
        else:
            context.deadline = time.monotonic() - 1
        return result

    monkeypatch.setattr(PinnedHover, 'receipt', delayed_receipt)
    with pytest.raises(RuntimeError, match='browser action'):
        hover(support, context)
    assert context.closed


@pytest.mark.parametrize('changed', [dict(value='payload'), dict(key='Enter'), dict(object_id=1)])
def test_hover_permit_rejects_other_action_inputs(lab, changed):
    support, context, _, _ = lab()
    with pytest.raises(ValueError):
        support.perform(context, replace(permit(), **changed), selector='#trigger')


def test_hover_authorization_cannot_be_replayed(lab):
    support, context, _, _ = lab()
    authorization = permit()
    support.perform(context, authorization, selector='#trigger')
    with pytest.raises(ValueError, match='already used'):
        support.perform(context, authorization, selector='#trigger')


@pytest.mark.parametrize('css,expected', [
    ('left:80.2px;top:80.3px;width:160.5px;height:60.6px', True),
    ('left:80.7px;top:80.7px;width:.1px;height:.1px;overflow:hidden', False),
])
def test_fractional_geometry_uses_one_observed_integer_point(lab, css, expected):
    support, context, _, _ = lab(style=STYLE + '<style>#trigger{' + css + '}</style>')
    if expected:
        assert asdict(hover(support, context).hover) == RECEIPT
    else:
        with pytest.raises(RuntimeError, match='browser action'):
            hover(support, context)


def test_center_hit_on_real_descendant_is_allowed(lab):
    support, context, _, _ = lab(style=STYLE + '<style>#trigger>span{position:absolute;inset:0}</style>')
    assert asdict(hover(support, context).hover) == RECEIPT


@pytest.mark.parametrize('native', [False, True])
def test_deferred_mock_hover_keeps_later_steps_fixture_on_reused_context(lab, native):
    fixture = ports.MockResponse(fixture_id='later-click', source='neutral', method='POST',
                                path='records/echo' if native else 'api/echo',
                                response={'success': True},
                                response_headers={'access-control-allow-origin': '*'})
    script = """window.release=null;window.pending=new Promise(r=>release=r);
    trigger.onmouseenter=async()=>{await pending;await send('hover').catch(()=>{})};
    go.onclick=()=>{release();return send('click')}"""
    support, context, app, api = lab(script, native=native, mode='mock', fixtures=[fixture])
    assert hover(support, context).mock_recordings == []
    next_node = replace(permit('click', mode='mock'), step_id='later_node/read')
    result = support.perform(context, next_node, selector='#go').evidence
    context.page.wait_for_function('done.includes("hover")')
    assert [r.mock_fixture_id for r in result.mock_recordings] == ['later-click']
    assert [t.request.body for t in result.traffic] == [{'tag': 'click'}]
    assert context.mock_queue.index == 1
    assert api.requests == [] and not any(r['path'].startswith('/api/') for r in app.requests)


def test_mock_hover_preflight_is_blocked_without_inventing_response(lab):
    support, context, _, api = lab("trigger.onmouseenter=()=>fetch(window.destination,{headers:{'X-Extra':'synthetic'}}).catch(()=>done.push('blocked'))", mode='mock', fixtures=[])
    context.page.evaluate('url=>window.destination=url', api.url + '/api/echo')
    evidence = hover(support, context)
    context.page.wait_for_function('done.includes("blocked")')
    context.native.collect(evidence.action_id)
    assert evidence.traffic == [] and evidence.mock_recordings == []
    assert context.diagnostics == []
    assert 'background HTTP acquisition failed' in context.native.notes
    assert context.errors == [] and api.requests == []


def test_nested_hover_property_await_cannot_inherit_trusted_click_origin(lab):
    markup = MARKUP.replace('<div id="trigger">', '<div id="trigger" onmouseenter="return (async()=>{await Promise.resolve();await send(\'hover\')})()">')
    support, context, _, api = lab("go.onclick=()=>{trigger.dispatchEvent(new MouseEvent('mouseenter'));return send('click')}", markup=markup)
    evidence = support.perform(context, permit('click'), selector='#go').evidence
    context.page.wait_for_function('done.includes("hover") && done.includes("click")')
    context.native.collect(evidence.action_id)
    assert [t.request.body for t in evidence.traffic] == [{'tag': 'click'}]
    assert any(r.request.body == {'tag': 'hover'} for r in context.diagnostics)
    assert len(api.requests) == 2
