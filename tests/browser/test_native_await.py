"""Actual Chromium invocation ownership across native asynchronous continuations."""
import json
from uuid import uuid4

import pytest

from refracto import ports
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport
from tests.browser.test_multi_origin_transport import Peer


def _permit(action='click', *, user=None, generation=0, context_id=''):
    key = uuid4().hex
    return ports.UiActionPermit(execution_id='await-run', action_id=key,
                                step_id='step-'+key, mode='live', action=action,
                                target='neutral', value='text' if action == 'fill' else None,
                                token=uuid4().hex, user=user, session_generation=generation,
                                context_id=context_id)


@pytest.fixture
def setup():
    owned = []

    def create(script, *, user=None, generation=0, context_id=''):
        app, api = Peer(), Peer()
        app.page = ('<button id="go">go</button><button id="other">other</button>'
                    '<input id="entry"><script>const api=' + json.dumps(api.url) + ';' +
                    'const go=document.querySelector("#go"), other=document.querySelector("#other");' +
                    script + '</script>').encode()
        support = BrowserSupport(app.url, lambda page: {}, network_policy=BrowserNetworkPolicy(
            api_endpoints=(ApiEndpoint(api.url, '/api', 'records'),)))
        context = support.open('live', user=user, session_generation=generation, context_id=context_id)
        owned.append((support, context, app, api))
        support.perform(context, _permit('open', user=user, generation=generation, context_id=context_id), url=app.url+'/')
        return support, context, api

    yield create
    for support, context, app, api in owned:
        support.close(context)
        app.close()
        api.close()


def _click(support, context, target='go'):
    permit = _permit(user=context.user, generation=context.session_generation, context_id=context.context_id)
    return support.perform(context, permit, selector='#'+target).evidence


@pytest.mark.parametrize('script', [
    "go.onclick=async()=>{await Promise.resolve();await fetch(api+'/api/echo')}",
    "go.addEventListener('click',async()=>{await Promise.resolve();await Promise.resolve();await fetch(api+'/api/echo')})",
    "async function inner(){await Promise.resolve();await fetch(api+'/api/echo')};async function outer(){await Promise.resolve();await inner()};go.onclick=()=>outer()",
    "go.onclick=async()=>{await Promise.resolve();await Promise.resolve().then(()=>fetch(api+'/api/echo'))}",
    "go.onclick=()=>Promise.resolve().then(async()=>{await Promise.resolve();await fetch(api+'/api/echo')})",
    "go.onclick=async()=>{await new Promise(resolve=>setTimeout(resolve,10));await fetch(api+'/api/echo')}",
    "go.onclick=async()=>{await Promise.all([Promise.resolve(),Promise.resolve()]);await fetch(api+'/api/echo')}",
    "go.onclick=async()=>{await Promise.resolve();const r=new XMLHttpRequest();r.open('GET',api+'/api/echo');r.send()}",
])
def test_native_await_preserves_invocation_and_actual_http(setup, script):
    support, context, api = setup(script)
    evidence = _click(support, context)
    assert len(evidence.traffic) == 1
    traffic = evidence.traffic[0]
    assert traffic.action_id == evidence.action_id
    assert traffic.response.step_id == evidence.step_id
    assert traffic.request.path == 'records/echo'
    assert traffic.browser_identity == traffic.response.browser_identity
    assert traffic.browser_identity.origin == api.url
    assert [(r['method'], r['path']) for r in api.requests] == [('GET', '/api/echo')]
    assert not any(name.lower().startswith('x-refract-') or name.lower() == 'traceparent'
                   for name in api.requests[0]['headers'])


def test_native_input_await_is_the_fill_invocation(setup):
    support, context, api = setup("document.querySelector('#entry').oninput=async()=>{await Promise.resolve();await fetch(api+'/api/echo')}")
    evidence = support.perform(context, _permit('fill'), selector='#entry').evidence
    assert len(evidence.traffic) == 1
    assert evidence.traffic[0].action_id == evidence.action_id
    assert len(api.requests) == 1


def test_unconsumed_large_awaited_fetch_preserves_response_and_completion(setup):
    support, context, api = setup("go.onclick=async()=>{await Promise.resolve();window.originalResponse=await fetch(api+'/api/unconsumed')}")
    handler = api.server.RequestHandlerClass
    original = handler.handle_request
    payload = json.dumps({'data': {'value': 'x' * (1024 * 1024)}}).encode()

    def large_response(request):
        if request.path != '/api/unconsumed':
            return original(request)
        api.requests.append({'method': request.command, 'path': request.path})
        request.send_response(200)
        request.send_header('Content-Type', 'application/json')
        request.send_header('Content-Length', str(len(payload)))
        request.send_header('Access-Control-Allow-Origin', request.headers['Origin'])
        request.end_headers()
        request.wfile.write(payload)

    handler.handle_request = large_response
    evidence = _click(support, context)
    assert len(evidence.traffic) == 1
    assert len(evidence.traffic[0].response.json['data']['value']) == 1024 * 1024
    assert context.page.evaluate('originalResponse.bodyUsed') is False
    assert context.page.evaluate('(async()=> (await originalResponse.json()).data.value.length)()') == 1024 * 1024
    assert api.requests == [{'method': 'GET', 'path': '/api/unconsumed'}]


@pytest.mark.parametrize('path', ['large', 'abort', 'cors-denied'])
def test_awaited_fetch_overflow_or_failure_cannot_supply_success(setup, path):
    support, context, api = setup("go.onclick=async()=>{await Promise.resolve();await fetch(api+'/api/"+path+"')}")
    with pytest.raises(RuntimeError, match='browser action'):
        _click(support, context)
    assert context.closed
    assert len(api.requests) == 1


def test_debugger_statements_do_not_pause_initial_or_repeated_navigation(setup):
    support, context, api = setup("debugger;go.onclick=async()=>{debugger;await Promise.resolve();debugger;await fetch(api+'/api/echo')}")
    paused = []
    context.native.session.on('Debugger.paused', lambda event: paused.append(event))
    first = _click(support, context)
    support.perform(context, _permit('open'), url=context.page.url)
    second = _click(support, context)
    assert len(first.traffic) == len(second.traffic) == 1
    assert len(api.requests) == 2
    assert paused == []


def test_debugger_configuration_survives_click_driven_navigation(setup):
    support, context, api = setup("debugger;other.onclick=()=>{location.href='/?next'};go.onclick=async()=>{await Promise.resolve();debugger;await fetch(api+'/api/echo')}")
    paused = []
    context.native.session.on('Debugger.paused', lambda event: paused.append(event))
    navigation = _click(support, context, 'other')
    result = _click(support, context)
    assert navigation.traffic == []
    assert len(result.traffic) == 1
    assert len(api.requests) == 1
    assert paused == []


def test_completion_claim_does_not_accept_unknown_or_repeated_handle(setup):
    support, context, api = setup("go.onclick=async()=>{await Promise.resolve();await fetch(api+'/api/echo')}")
    assert context.page.evaluate("__refractBrowser.claimNative('unknown','not-an-action')") is False
    result = _click(support, context)
    assert len(result.traffic) == 1
    nonce = next(iter(context.native.markers))
    assert context.page.evaluate("nonce=>__refractBrowser.claimNative(nonce,'not-an-action')", nonce) is False
    assert len(api.requests) == 1


@pytest.mark.parametrize('result', ['false', 'null', '1'])
def test_missing_or_invalid_completion_claim_fails_before_delivery(setup, result):
    support, context, api = setup("go.onclick=async()=>{await Promise.resolve();await fetch(api+'/api/echo')}")
    context.page.evaluate('window.__refractBrowser.claimNative=()=>'+result)
    with pytest.raises(RuntimeError, match='browser action'):
        _click(support, context)
    assert context.closed
    assert api.requests == []


def test_unclaimed_fetch_handle_budget_fails_closed_without_extra_delivery(setup):
    support, context, api = setup("go.onclick=async()=>{await Promise.resolve();const pending=[];for(let i=0;i<129;i++)pending.push(fetch(api+'/api/echo'));await Promise.all(pending)}")
    with pytest.raises(RuntimeError, match='browser action'):
        _click(support, context)
    assert context.closed
    assert len(api.requests) <= 128


def test_rejected_fetch_handles_are_cleaned_before_next_request(setup):
    support, context, api = setup("go.onclick=async()=>{for(let i=0;i<129;i++){try{await fetch('http://[')}catch{}}await fetch(api+'/api/echo')}")
    evidence = _click(support, context)
    assert len(evidence.traffic) == 1
    assert len(api.requests) == 1


@pytest.mark.parametrize('schedule', [
    "setTimeout(()=>send(),0);await send()",
    "const shared=Promise.resolve();setTimeout(()=>send(shared),0);await send(shared)",
    "const shared=new Promise(resolve=>setTimeout(resolve,20));setTimeout(()=>send(shared),0);await send(shared)",
])
def test_same_helper_and_same_request_background_never_substitute(setup, schedule):
    support, context, api = setup("async function send(shared=Promise.resolve()){await shared;await (await fetch(api+'/api/echo')).json()};go.onclick=async()=>{"+schedule+"};other.onclick=()=>Promise.resolve()")
    first = _click(support, context)
    context.page.wait_for_timeout(50)
    second = _click(support, context, 'other')
    assert len(first.traffic) == 1
    assert second.traffic == []
    assert len(api.requests) == 2
    diagnostics = first.diagnostic_recorded + second.diagnostic_recorded
    assert len(diagnostics) == 1
    assert diagnostics[0].step_id is None
    assert diagnostics[0].request.path == first.traffic[0].request.path


@pytest.mark.parametrize('event', ["other.click()", "other.dispatchEvent(new Event('custom'))"])
def test_null_nested_event_scope_blocks_outer_trusted_identity(setup, event):
    support, context, api = setup("const send=async()=>{await Promise.resolve();await (await fetch(api+'/api/echo')).json()};other.addEventListener('click',send);other.addEventListener('custom',send);go.onclick=()=>{"+event+"}")
    first = _click(support, context)
    context.page.wait_for_timeout(50)
    second = _click(support, context, 'go')
    assert first.traffic == second.traffic == []
    assert len(api.requests) == 2
    assert all(r.step_id is None for r in first.diagnostic_recorded + second.diagnostic_recorded)


def test_background_created_promise_does_not_own_its_action_waiter(setup):
    support, context, api = setup("let release;const shared=new Promise(r=>release=r);async function send(){await shared;await (await fetch(api+'/api/echo')).json()};void send();go.onclick=async()=>{setTimeout(release,10);await send()};other.onclick=()=>Promise.resolve()")
    first = _click(support, context)
    context.page.wait_for_timeout(30)
    second = _click(support, context, 'other')
    assert len(first.traffic) == 1
    assert second.traffic == []
    assert len(api.requests) == 2
    diagnostics = first.diagnostic_recorded + second.diagnostic_recorded
    assert len(diagnostics) == 1 and diagnostics[0].step_id is None


def test_separate_callbacks_waiting_on_same_promise_preserve_invocations(setup):
    support, context, api = setup("let release;const shared=new Promise(r=>release=r);async function send(){await shared;await (await fetch(api+'/api/echo')).json()};go.addEventListener('click',()=>send());go.addEventListener('click',()=>send());go.addEventListener('click',()=>setTimeout(release,10))")
    evidence = _click(support, context)
    assert len(evidence.traffic) == 2
    assert len({t.request_id for t in evidence.traffic}) == 2
    assert all(t.action_id == evidence.action_id for t in evidence.traffic)
    assert len(api.requests) == 2


def test_detached_late_continuation_keeps_old_action_not_next_action(setup):
    support, context, api = setup("let release;const gate=new Promise(r=>release=r);async function send(){await gate;await (await fetch(api+'/api/echo')).json()};go.onclick=()=>{void send()};other.onclick=()=>{release();return Promise.resolve()}")
    first = _click(support, context)
    second = _click(support, context, 'other')
    context.page.wait_for_timeout(50)
    third = _click(support, context, 'other')
    assert first.traffic == second.traffic == third.traffic == []
    assert len(api.requests) == 1
    diagnostics = second.diagnostic_recorded + third.diagnostic_recorded
    assert len(diagnostics) == 1
    assert diagnostics[0].step_id == first.step_id


def test_two_steps_call_same_async_function_keep_separate_identity(setup):
    support, context, api = setup("async function send(){await Promise.resolve();await (await fetch(api+'/api/echo')).json()};go.onclick=()=>send()")
    first, second = _click(support, context), _click(support, context)
    assert first.action_id != second.action_id
    assert len(first.traffic) == len(second.traffic) == 1
    assert first.traffic[0].action_id == first.action_id
    assert second.traffic[0].action_id == second.action_id
    assert first.traffic[0].request_id != second.traffic[0].request_id
    assert len(api.requests) == 2


def test_truncated_async_chain_does_not_guess_current_action(setup):
    support, context, api = setup("async function deep(n){await Promise.resolve();if(n)return await deep(n-1);await (await fetch(api+'/api/echo')).json()};go.onclick=()=>deep(40);other.onclick=()=>Promise.resolve()")
    first = _click(support, context)
    context.page.wait_for_timeout(30)
    second = _click(support, context, 'other')
    assert first.traffic == second.traffic == []
    assert len(api.requests) == 1
    diagnostics = first.diagnostic_recorded + second.diagnostic_recorded
    assert len(diagnostics) == 1 and diagnostics[0].step_id is None


def test_independent_user_contexts_cannot_inherit_async_origin(setup):
    script = "go.onclick=async()=>{await Promise.resolve();await (await fetch(api+'/api/echo')).json()}"
    first = setup(script, user='owner', generation=1, context_id='owner-context')
    second = setup(script, user='peer', generation=2, context_id='peer-context')
    a, b = _click(*first[:2]), _click(*second[:2])
    assert (a.user, a.session_generation, a.context_id) == ('owner', 1, 'owner-context')
    assert (b.user, b.session_generation, b.context_id) == ('peer', 2, 'peer-context')
    assert a.traffic[0].action_id == a.action_id != b.action_id == b.traffic[0].action_id
    assert a.traffic[0].request_id != b.traffic[0].request_id
