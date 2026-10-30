"""Native browser and independent HTTP observations for explicit origin policy."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
import time
import socket
from uuid import uuid4
from urllib.parse import urlsplit

import pytest

from refracto import ports
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport


def _origin(authority, *, scheme="https"):
    return scheme + "://" + authority


class Peer:
    def __init__(self):
        self.requests = []
        self.page = b''
        self.redirect = ''
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def do_OPTIONS(self):
                self.handle_request()

            def handle_request(self):
                path = urlsplit(self.path).path
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                outer.requests.append({'method': self.command, 'path': path,
                                       'headers': dict(self.headers), 'body': raw})
                if path == '/api/abort':
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if path == '/':
                    body, kind = outer.page, 'text/html'
                elif path == '/asset.js':
                    body, kind = b'window.assetReady=true;', 'application/javascript'
                else:
                    body = json.dumps({'success': True, 'data': {'reply': 'observed', 'path': path}}).encode()
                    if path == '/api/large':
                        body = json.dumps({'data': {'reply': 'x' * (8 * 1024 * 1024)}}).encode()
                    kind = 'text/event-stream' if path == '/api/stream' else 'application/json'
                self.send_response(307 if path == '/api/redirect' else 204 if self.command == 'OPTIONS' else 200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body) if self.command != 'OPTIONS' else 0))
                if path != '/api/cors-denied':
                    self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin', '*'))
                    self.send_header('Access-Control-Allow-Credentials', 'true')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                if path != '/api/preflight-denied':
                    self.send_header('Access-Control-Allow-Headers', 'authorization, content-type, traceparent')
                if path == '/api/redirect':
                    self.send_header('Location', outer.redirect)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Observed', 'real-peer')
                if path == '/api/cookies':
                    self.send_header('Set-Cookie', 'first=1')
                    self.send_header('Set-Cookie', 'second=2')
                self.end_headers()
                if self.command != 'OPTIONS':
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@pytest.fixture
def origins():
    app, api, static, other = [Peer() for _ in range(4)]
    app.page = f'''<script src="{static.url}/asset.js"></script><button id="simple">simple</button>
<button id="xhr">xhr</button><button id="auth">auth</button><button id="cors">cors</button>
<button id="preflight">preflight</button><button id="unknown">unknown</button>
<button id="redirect">redirect</button><button id="stream">stream</button>
<button id="awaited">awaited</button><button id="timer">timer</button>
<button id="background">background</button><button id="trace">trace</button><button id="opaque">opaque</button><button id="large">large</button><button id="abort-bg">abort-bg</button>
<button id="cookie">cookie</button><button id="duplicate">duplicate</button><pre id="result"></pre>
<script>
const api={json.dumps(api.url)}, other={json.dumps(other.url)};
const result=document.querySelector('#result');
const read = response => response.json().then(value => {{result.textContent=value.data.reply;}});
const request = (path, options) => fetch(api+path,options).then(read).catch(()=>{{result.textContent='denied';}});
document.querySelector('#simple').onclick=()=>request('/api/echo');
document.querySelector('#opaque').onclick=()=>fetch(api+'/api/echo',{{mode:'no-cors'}});
document.querySelector('#large').onclick=()=>request('/api/large');
document.querySelector('#abort-bg').onclick=()=>{{setTimeout(()=>request('/api/abort'),0);}};
document.querySelector('#xhr').onclick=()=>{{const r=new XMLHttpRequest();r.open('GET',api+'/api/xhr');r.onload=()=>{{result.textContent='xhr';}};r.send();}};
document.querySelector('#auth').onclick=()=>request('/api/auth',{{method:'POST',headers:{{Authorization:'Bearer app-owned','Content-Type':'application/json'}},body:JSON.stringify({{name:'literal',flag:false}})}});
document.querySelector('#cors').onclick=()=>request('/api/cors-denied');
document.querySelector('#preflight').onclick=()=>request('/api/preflight-denied',{{method:'POST',headers:{{Authorization:'Bearer app-owned'}}}});
document.querySelector('#unknown').onclick=()=>fetch(other+'/api/echo').catch(()=>{{}});
document.querySelector('#redirect').onclick=()=>request('/api/redirect');
document.querySelector('#stream').onclick=()=>request('/api/stream');
document.querySelector('#awaited').onclick=async()=>{{await Promise.resolve();await request('/api/echo');}};
document.querySelector('#timer').onclick=()=>{{setTimeout(()=>request('/api/echo'),0);}};
document.querySelector('#background').onclick=()=>{{window.background=setInterval(()=>request('/api/echo'),5);}};
document.querySelector('#trace').onclick=()=>request('/api/echo',{{headers:{{traceparent:'00-11111111111111111111111111111111-2222222222222222-01'}}}});
document.querySelector('#cookie').onclick=()=>request('/api/cookies',{{credentials:'include'}});
document.querySelector('#duplicate').onclick=()=>Promise.all([request('/api/echo'),request('/api/echo')]);
</script>'''.encode()
    api.redirect = other.url + '/api/echo'
    try:
        yield app, api, static, other
    finally:
        for peer in (app, api, static, other):
            peer.close()


def permit(action='click', mode='live'):
    key = uuid4().hex
    return ports.UiActionPermit(execution_id='native-run', action_id=key, step_id='step-'+key,
                                mode=mode, action=action, target='neutral', value=None, token=uuid4().hex)


def rendered(page):
    return {'page': {'identified': [{'id': 'page', 'fields': {
        'result': page.locator('#result').text_content() if page.locator('#result').count() else '',
        'asset': page.evaluate('window.assetReady === true'),
    }}], 'anonymous': []}}


@pytest.fixture
def browser(origins):
    app, api, static, other = origins
    owned = []

    def create(*, mode='live', fixtures=None, credentials=True, endpoints=None, options=None):
        policy = BrowserNetworkPolicy(
            api_endpoints=tuple(endpoints) if endpoints is not None else (ApiEndpoint(api.url, '/api', 'service'),),
            resource_origins=(static.url,), credential_origins=(api.url,) if credentials else (),
        )
        support = BrowserSupport(app.url, rendered, network_policy=policy)
        context = support.open(mode, mock_plan=fixtures, context_options=options)
        owned.append((support, context))
        support.perform(context, permit('open', mode), url=app.url+'/')
        return support, context

    yield create
    for support, context in owned:
        support.close(context)


def click(support, context, target):
    return support.perform(context, permit(mode=context.mode), selector='#'+target).evidence


@pytest.mark.parametrize('target,path', [('simple','echo'),('xhr','xhr')])
def test_native_simple_requests_keep_cors_and_real_origin_without_wire_markers(browser, origins, target, path):
    support, context = browser()
    evidence = click(support, context, target)
    assert evidence.rendered['page']['identified'][0]['fields']['asset'] is True
    assert len(evidence.traffic) == 1
    traffic = evidence.traffic[0]
    assert traffic.request.path == 'service/'+path
    assert traffic.browser_identity.origin == origins[1].url
    assert traffic.browser_identity == traffic.response.browser_identity
    assert traffic.request_id.endswith(':' + traffic.browser_identity.request_id)
    assert traffic.request.traceparent is traffic.response.trace_id is None
    actual = origins[1].requests
    assert [(item['method'],item['path']) for item in actual] == [('GET','/api/'+path)]
    assert not any(k.lower().startswith('x-refract-') or k.lower() == 'traceparent' for k in actual[0]['headers'])
    assert ('X-Observed','real-peer') in traffic.response.header_items
    assert evidence.diagnostic_notes == []


def test_app_authorization_preflight_is_native_and_body_is_not_replayed(browser, origins):
    support, context = browser()
    evidence = click(support, context, 'auth')
    traffic = evidence.traffic[0]
    assert traffic.request.body == {'name':'literal','flag':False}
    assert traffic.request.traceparent is None
    assert [(r['method'],r['path']) for r in origins[1].requests] == [('OPTIONS','/api/auth'),('POST','/api/auth')]
    assert origins[1].requests[-1]['headers']['Authorization'] == 'Bearer app-owned'
    assert all('Authorization' not in r['headers'] for peer in (origins[0],origins[2]) for r in peer.requests)


@pytest.mark.parametrize('target', ['cors','preflight','unknown','redirect','stream'])
def test_cors_policy_and_unsupported_responses_cannot_create_success(browser, origins, target):
    support, context = browser()
    with pytest.raises(RuntimeError, match='browser action'):
        click(support, context, target)
    assert context.closed
    assert origins[3].requests == []
    if target == 'preflight':
        assert [r['method'] for r in origins[1].requests] == ['OPTIONS']


def test_unauthorized_credential_request_is_blocked_without_stripping_or_forwarding(browser, origins):
    support, context = browser(credentials=False)
    with pytest.raises(RuntimeError):
        click(support, context, 'auth')
    assert not any(r['method'] == 'POST' for r in origins[1].requests)


def test_global_credential_configuration_is_rejected_before_navigation(browser, origins):
    with pytest.raises(ValueError, match='global browser header'):
        browser(options={'extra_http_headers': {'Authorization':'secret'}})
    assert all(peer.requests == [] for peer in origins)


@pytest.mark.parametrize('target', ['awaited','timer'])
def test_native_async_and_timer_are_diagnostics_not_current_action(browser, target):
    support, context = browser()
    first = click(support, context, target)
    context.page.wait_for_timeout(50)
    second = click(support, context, 'simple')
    assert first.traffic == []
    assert len(second.traffic) == 1
    assert any(r.request.path == 'service/echo' for r in first.diagnostic_recorded + second.diagnostic_recorded)
    assert all(r.step_id is None for r in first.diagnostic_recorded + second.diagnostic_recorded)


def test_same_endpoint_calls_keep_distinct_browser_request_identities(browser):
    support, context = browser()
    evidence = click(support, context, 'duplicate')
    assert len(evidence.traffic) == 2
    assert len({t.request_id for t in evidence.traffic}) == 2


def test_application_trace_is_preserved_and_observed(browser, origins):
    support, context = browser()
    evidence = click(support, context, 'trace')
    recording = evidence.traffic[0].response
    assert recording.trace_id == '1'*32
    assert ('traceparent', recording.request.traceparent) in [(n.lower(),v) for n,v in recording.request_header_items]
    assert origins[1].requests[-1]['headers']['traceparent'] == recording.request.traceparent


def test_live_header_pairs_preserve_repeated_response_cookie(browser):
    support, context = browser()
    evidence = click(support, context, 'cookie')
    assert [v for n,v in evidence.traffic[0].response.header_items if n.lower()=='set-cookie'] == ['first=1','second=2']


def test_missing_mock_has_zero_live_api_requests(browser, origins):
    support, context = browser(mode='mock', fixtures=[])
    with pytest.raises(RuntimeError):
        click(support, context, 'simple')
    assert origins[1].requests == []


def test_explicit_cross_origin_mock_is_not_live_or_complete_header_evidence(browser, origins):
    fixture = ports.MockResponse(fixture_id='mock', source='independent synthetic fixture', method='GET',
                                path='service/echo', response={'success':True,'data':{'reply':'mocked'}},
                                response_headers={'access-control-allow-origin':origins[0].url})
    support, context = browser(mode='mock', fixtures=[fixture])
    evidence = click(support, context, 'simple')
    recording = evidence.traffic[0].response
    assert recording.json['data']['reply'] == 'mocked'
    assert recording.mock_fixture_id == 'mock'
    assert recording.header_items is None
    assert origins[1].requests == []
    assert len(evidence.mock_recordings) == 1


def test_mock_preflight_is_not_invented_or_sent_live(browser, origins):
    fixture = ports.MockResponse(fixture_id='mock', source='synthetic', method='POST', path='service/auth', response={})
    support, context = browser(mode='mock', fixtures=[fixture])
    with pytest.raises(RuntimeError):
        click(support, context, 'auth')
    assert origins[1].requests == []


@pytest.mark.parametrize('entries', [
    [ApiEndpoint(_origin('example.com:8001', scheme='http'),'/api','records'),ApiEndpoint(_origin('example.org:8002', scheme='http'),'/api','records')],
    [ApiEndpoint(_origin('example.com:8001', scheme='http'),'/api','one'),ApiEndpoint(_origin('example.com:8001', scheme='http'),'/api/nested','two')],
    [ApiEndpoint(_origin('example.com:8001', scheme='http'),'/api',''),ApiEndpoint(_origin('example.org:8002', scheme='http'),'/api','two')],
])
def test_ambiguous_actual_or_logical_prefixes_rejected(entries):
    with pytest.raises(ValueError, match='overlaps'):
        BrowserNetworkPolicy(api_endpoints=entries)


@pytest.mark.parametrize('origin', [_origin('*.example.com'),_origin('example.com/path'),_origin('user:pass@' + 'example.com'),_origin('/tmp/a', scheme='file'),_origin('example.com?x=1'),_origin('example.com#fragment')])
def test_invalid_origin_configuration_rejected(origin):
    with pytest.raises(ValueError):
        ApiEndpoint(origin,'/api','api')


def test_actual_cookie_delivery_is_checked_before_an_unauthorized_request(browser, origins):
    support, context = browser(credentials=False)
    context.browser_context.add_cookies([{'name':'native-cookie','value':'credential-sentinel','url':origins[1].url}])
    with pytest.raises(RuntimeError):
        click(support, context, 'cookie')
    assert origins[1].requests == []


def test_same_path_at_two_sources_has_distinct_logical_ownership(browser, origins):
    endpoints = [ApiEndpoint(origins[1].url,'/api','first'),ApiEndpoint(origins[3].url,'/api','second')]
    support, context = browser(endpoints=endpoints)
    first = click(support, context, 'simple')
    second = click(support, context, 'unknown')
    assert first.traffic[0].request.path == 'first/echo'
    assert second.traffic[0].request.path == 'second/echo'
    assert first.traffic[0].browser_identity.origin != second.traffic[0].browser_identity.origin


def test_continuous_background_is_bounded_without_holding_action_open(browser):
    support, context = browser()
    click(support, context, 'background')
    # Wait for the independent source to exceed the fixed diagnostic count.
    deadline = time.monotonic() + 5
    while 'background diagnostics truncated' not in context.native.notes and time.monotonic() < deadline:
        context.page.wait_for_timeout(10)
    before = time.monotonic()
    evidence = click(support, context, 'simple')
    assert time.monotonic()-before < 5
    assert len(evidence.traffic) == 1
    assert len(context.diagnostics) <= 100
    assert context.native.background_bytes <= 256*1024
    assert 'background diagnostics truncated' in evidence.diagnostic_notes
    assert all(r.step_id is None for r in context.diagnostics)
    context.page.evaluate('clearInterval(window.background)')


def test_context_namespaces_keep_outer_request_ids_distinct(browser):
    first_support, first_context = browser()
    second_support, second_context = browser()
    first = click(first_support, first_context, 'simple').traffic[0]
    second = click(second_support, second_context, 'simple').traffic[0]
    assert first.request_id != second.request_id
    assert first.request_id.startswith(first_context.native.request_namespace + ':')
    assert second.request_id.startswith(second_context.native.request_namespace + ':')
    first_support.close(first_context)
    assert len(click(second_support, second_context, 'simple').traffic) == 1


@pytest.mark.parametrize('origin', [_origin('%65xample.com'),_origin('example.com.'),_origin('-bad.example.com'),_origin('bad_.example.com'),_origin('example.com:0'),_origin('example.com:65536')])
def test_noncanonical_or_ambiguous_hostname_rules_rejected(origin):
    with pytest.raises(ValueError):
        ApiEndpoint(origin,'/api','api')


@pytest.mark.parametrize('path', ['/api//echo','/api/a//echo'])
def test_duplicate_separators_are_not_normalized_to_another_endpoint(path):
    policy = BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(_origin('example.com:8001', scheme='http'),'/api','service'),))
    with pytest.raises(ValueError, match='normalized'):
        policy.classify(_origin('example.org:8002', scheme='http'),_origin('example.com:8001', scheme='http')+path,'Fetch','GET',{})


@pytest.mark.parametrize('resource,method', [('Ping','POST'),('Document','POST'),('Other','POST'),('WebSocket','GET')])
def test_resource_permission_does_not_authorize_other_transports(resource,method):
    policy = BrowserNetworkPolicy(resource_origins=(_origin('example.net:8003', scheme='http'),))
    with pytest.raises(ValueError):
        policy.classify(_origin('example.org:8002', scheme='http'),_origin('example.net:8003/endpoint', scheme='http'),resource,method,{})


def test_opaque_cross_origin_response_cannot_be_promoted_from_devtools(browser, origins):
    support, context = browser()
    with pytest.raises(RuntimeError):
        click(support, context, 'opaque')
    assert origins[1].requests == []
    assert context.traffic == []


def test_custom_credential_name_is_not_a_business_header(origins):
    app, api, static, _ = origins
    policy = BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(api.url,'/api','service'),),
                                  resource_origins=(static.url,),
                                  credential_headers={'x-account-key': (api.url,)})
    support = BrowserSupport(app.url, rendered, network_policy=policy)
    context = support.open('live')
    try:
        with pytest.raises(ValueError, match='collide'):
            support.validate_request_header_names(context, ('x-account-key',))
        assert all(peer.requests == [] for peer in origins)
    finally:
        support.close(context)


def test_unassociated_background_disconnect_does_not_poison_current_operation(browser):
    support, context = browser()
    first = click(support, context, 'abort-bg')
    context.page.wait_for_timeout(50)
    current = click(support, context, 'simple')
    assert first.traffic == []
    assert len(current.traffic) == 1
    assert 'background HTTP acquisition failed' in current.diagnostic_notes


def test_associated_body_over_native_capture_budget_is_error(browser):
    support, context = browser()
    with pytest.raises(RuntimeError):
        click(support, context, 'large')
    assert context.closed
    assert context.traffic == []


def test_missing_cors_in_mock_is_not_repaired(browser, origins):
    fixture = ports.MockResponse(fixture_id='no-cors',source='synthetic',method='GET',path='service/echo',response={})
    support, context = browser(mode='mock',fixtures=[fixture])
    with pytest.raises(RuntimeError):
        click(support, context, 'simple')
    assert origins[1].requests == []
    assert context.traffic == []


@pytest.mark.parametrize('kind', ['window', 'anchor', 'form', 'blank-then-navigate'])
def test_new_browser_targets_are_denied_before_their_first_http(browser, origins, kind):
    app, api, static, other = origins
    target = json.dumps(other.url+'/api/echo')
    actions = {
        'window': f"window.open({target}, '_blank')",
        'anchor': f"const a=document.createElement('a');a.href={target};a.target='_blank';document.body.append(a);a.click()",
        'form': f"const f=document.createElement('form');f.action={target};f.target='_blank';f.method='POST';document.body.append(f);f.submit()",
        'blank-then-navigate': f"const w=window.open('about:blank','_blank');w.location={target}",
    }
    app.page += ('<button id="popup">popup</button><script>document.querySelector("#popup").onclick=()=>{'+actions[kind]+'};</script>').encode()
    support, context = browser()
    with pytest.raises(RuntimeError):
        click(support, context, 'popup')
    assert other.requests == []
    assert context.closed
    assert context.traffic == []


def test_diagnostic_retention_budget_counts_request_body_and_all_record_fields(browser, origins):
    app, api, _, _ = origins
    app.page += (f"<button id='large-background'>background</button><script>document.querySelector('#large-background').onclick=()=>{{setTimeout(()=>fetch('{api.url}/api/echo',{{method:'POST',body:JSON.stringify({{data:'x'.repeat(400000)}})}}).then(r=>r.json()),0)}};</script>").encode()
    support, context = browser()
    click(support, context, 'large-background')
    context.page.wait_for_timeout(100)
    evidence = click(support, context, 'simple')
    assert len(evidence.traffic) == 1
    assert context.diagnostics == []
    assert context.native.background_bytes == 0
    assert 'background diagnostics truncated' in evidence.diagnostic_notes
    assert len(api.requests[0]['body']) > 256 * 1024


def test_ipv6_endpoint_uses_chromium_canonical_address():
    endpoint = ApiEndpoint(_origin('[0:0:0:0:0:0:0:1]:8888', scheme='http'),'/api','service')
    assert endpoint.origin == _origin('[::1]:8888', scheme='http')
    policy = BrowserNetworkPolicy(api_endpoints=(endpoint,))
    assert policy.classify(_origin('example.org:8002', scheme='http'),_origin('[::1]:8888/api/echo', scheme='http'),'Fetch','GET',{}) == (_origin('[::1]:8888', scheme='http'),'service/echo')
