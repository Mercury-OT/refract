"""Independent HTTP receipts guard bounded background/resource exceptions."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import yaml

from refracto import ports
from refracto.errors import ActionFailure, ActionFailureReason as Reason
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport, ResourceRoute
from tests.browser.test_framework_failure_reporting import Auth, NoResponse


CSS = b"body { color: rgb(7, 8, 9); }"
ARRAY = '[ "record", 0, false, null, {"tag":"two"} ]'
NOTE = "background request body not represented"


class Peer:
    def __init__(self):
        self.page = b""
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.reply()

            do_HEAD = do_POST = do_OPTIONS = do_GET

            def reply(self):
                path = urlsplit(self.path).path
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                outer.requests.append({"method": self.command, "path": path,
                                       "body": raw, "headers": dict(self.headers)})
                body = (outer.page if path == "/" else CSS if path.endswith(".css") else
                        b'{"success":true,"data":{"reply":"seen"}}')
                kind = ("text/html" if path == "/" else "text/css" if path.endswith(".css") else
                        "text/event-stream" if path == "/api/stream" else "application/json")
                status = 307 if path == "/api/redirect" else 204 if self.command == "OPTIONS" else 200
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body) if status != 204 else 0))
                self.send_header("Cache-Control", "no-store")
                if path != "/api/cors-denied":
                    self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
                    self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "content-type, authorization, traceparent")
                if status == 307:
                    self.send_header("Location", "/api/after-redirect")
                self.end_headers()
                if self.command != "HEAD" and status != 204:
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def request(url, *, transport="fetch", method="GET", body=None, headers=None):
    options = {"method": method, "headers": headers or {}}
    if body is not None:
        options["body"] = body
    if transport == "fetch":
        return "fetch(" + json.dumps(url) + "," + json.dumps(options) + ").then(r=>r.text())"
    return """new Promise((resolve,reject)=>{
      const r=new XMLHttpRequest();r.open(%s,%s);
      for(const [key,value] of Object.entries(%s)) r.setRequestHeader(key,value);
      r.onload=()=>resolve(r.responseText);r.onerror=()=>reject(new Error('request failed'));
      r.send(%s);
    })""" % (json.dumps(method), json.dumps(url), json.dumps(options["headers"]), json.dumps(body))


def page(script):
    return ("<!doctype html><button id='go'>Read</button><div id='result'></div><script>"
            "window.done=false;window.result='';" + script + "</script>").encode()


def complete(expression):
    return (expression + ".then(value=>{window.result=value;})"
            ".catch(()=>{window.result='unavailable';}).finally(()=>{window.done=true;});")


def permit(action="open", mode="live"):
    key = uuid4().hex
    return ports.UiActionPermit(execution_id="resource-run", action_id=key, step_id=key,
        mode=mode, action=action, target="page" if action == "open" else "go",
        value=None, token=uuid4().hex)


def snapshot(page):
    page.wait_for_function("window.done === true", timeout=5000)
    return {"page": {"identified": [], "anonymous": [{"fields": {
        "result": page.evaluate("window.result"),
        "color": page.evaluate("getComputedStyle(document.body).color"),
    }}]}}


@pytest.fixture
def lab():
    peers, contexts = [], []

    def create(script, *, mode="live", routes=True, credentials=False,
               api=None, mock_plan=None, open_now=True):
        peer = Peer()
        peers.append(peer)
        peer.page = page(script)
        policy = BrowserNetworkPolicy(
            api_endpoints=(ApiEndpoint(api or peer.url, "/api", "api"),),
            resource_routes=(ResourceRoute(peer.url, "/assets"),) if routes else (),
            credential_origins=(peer.url,) if credentials else ())
        support = BrowserSupport(peer.url, snapshot, timeout_ms=5000, network_policy=policy)
        context = support.open(mode, mock_plan=mock_plan)
        contexts.append((support, context))
        evidence = None
        if open_now:
            evidence = support.perform(context, permit(mode=mode), url=peer.url + "/").evidence
        return peer, support, context, evidence

    create.peers = peers
    yield create
    for support, context in reversed(contexts):
        support.close(context)
    for peer in reversed(peers):
        peer.close()


def received(peer, path):
    return [r for r in peer.requests if r["path"] == path]


@pytest.mark.parametrize("transport", ["fetch", "xhr"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_explicit_resource_route_preserves_css_and_never_creates_api_evidence(lab, transport, method):
    expression = request("/assets/theme.css", transport=transport, method=method)
    expression += ".then(text=>{const s=document.createElement('style');s.textContent=text;document.head.append(s);return text;})"
    peer, _, context, evidence = lab(complete(expression))
    assert [(r["method"], r["body"]) for r in received(peer, "/assets/theme.css")] == [(method, b"")]
    fields = evidence.rendered["page"]["anonymous"][0]["fields"]
    assert fields["result"] == (CSS.decode() if method == "GET" else "")
    if method == "GET":
        assert fields["color"] == "rgb(7, 8, 9)"
    assert evidence.traffic == evidence.diagnostic_recorded == evidence.diagnostic_outgoing == []
    assert evidence.diagnostic_notes == []
    assert not any(entry.get("logical") for entry in context.native.requests.values())


def test_stylesheet_loading_retains_existing_resource_behavior(lab):
    script = """const link=document.createElement('link');link.rel='stylesheet';
      link.href='/assets/theme.css';link.onload=()=>{window.done=true;};document.head.append(link);"""
    peer, _, _, evidence = lab(script, routes=False)
    assert len(received(peer, "/assets/theme.css")) == 1
    assert evidence.rendered["page"]["anonymous"][0]["fields"]["color"] == "rgb(7, 8, 9)"
    assert evidence.traffic == evidence.diagnostic_recorded == []


@pytest.mark.parametrize("path,method,routes", [
    ("/assets/theme.css", "GET", False),
    ("/assets-other/theme.css", "GET", True),
    ("/assets/theme.css", "POST", True),
    ("/assets/theme.css", "OPTIONS", True),
])
def test_resource_route_does_not_grant_unconfigured_paths_or_methods(lab, path, method, routes):
    peer, support, context, _ = lab(complete(request(path, method=method)), routes=routes, open_now=False)
    with pytest.raises(ActionFailure) as error:
        support.perform(context, permit(), url=peer.url + "/")
    assert error.value.reason is Reason.POLICY_DENIED
    assert received(peer, path) == []
    assert context.closed


def test_resource_route_does_not_grant_credential_delivery(lab):
    peer, support, context, _ = lab(complete(request("/assets/theme.css",
        headers={"Authorization": "Bearer credential-sentinel"})), open_now=False)
    with pytest.raises(ActionFailure) as error:
        support.perform(context, permit(), url=peer.url + "/")
    assert error.value.reason is Reason.POLICY_DENIED
    assert received(peer, "/assets/theme.css") == []
    assert "credential-sentinel" not in str(error.value)


def test_resource_route_does_not_grant_another_origin(lab):
    foreign = Peer()
    lab.peers.append(foreign)
    peer, support, context, _ = lab(complete(request(foreign.url + "/assets/theme.css")), open_now=False)
    with pytest.raises(ActionFailure) as error:
        support.perform(context, permit(), url=peer.url + "/")
    assert error.value.reason is Reason.POLICY_DENIED
    assert foreign.requests == []


@pytest.mark.parametrize("transport", ["fetch", "xhr"])
def test_background_array_bytes_reach_server_without_fabricated_record(lab, transport):
    expression = request("/api/records", transport=transport, method="POST", body=ARRAY,
                         headers={"Content-Type": "application/json"})
    peer, _, context, evidence = lab(complete("Promise.all([" + expression + "," + expression + "]).then(r=>r[0])"))
    assert [r["body"] for r in received(peer, "/api/records")] == [ARRAY.encode()] * 2
    assert json.loads(evidence.rendered["page"]["anonymous"][0]["fields"]["result"])["data"]["reply"] == "seen"
    assert evidence.traffic == evidence.diagnostic_recorded == evidence.diagnostic_outgoing == []
    assert evidence.diagnostic_notes == [NOTE]
    assert context.native.background_reads == 0
    assert not any(entry.get("logical") for entry in context.native.requests.values())


def test_existing_background_object_still_has_complete_typed_diagnostic(lab):
    raw = '{ "name": "record" }'
    expression = request("/api/records", method="POST", body=raw,
                         headers={"Content-Type": "application/json"})
    peer, _, _, evidence = lab(complete(expression))
    assert received(peer, "/api/records")[0]["body"] == raw.encode()
    assert evidence.traffic == [] and evidence.diagnostic_notes == []
    assert len(evidence.diagnostic_recorded) == 1
    assert evidence.diagnostic_recorded[0].request.body == {"name": "record"}


@pytest.mark.parametrize("awaited", [False, True])
@pytest.mark.parametrize("transport", ["fetch", "xhr"])
def test_action_owned_array_remains_rejected_even_after_native_await(lab, awaited, transport):
    expression = request("/api/records", transport=transport, method="POST", body=ARRAY,
                         headers={"Content-Type": "application/json"})
    script = "window.done=true;document.querySelector('#go').onclick=" + ("async " if awaited else "")
    script += "()=>{" + ("await Promise.resolve();" if awaited else "") + "return " + complete(expression) + "};"
    peer, support, context, _ = lab(script)
    with pytest.raises(ActionFailure) as error:
        support.perform(context, permit("click"), selector="#go")
    assert error.value.reason is Reason.EVIDENCE_INVALID
    assert received(peer, "/api/records") == []
    assert NOTE not in context.native.notes
    assert context.closed


@pytest.mark.parametrize("transport", ["fetch", "xhr"])
def test_mock_array_neither_reaches_server_nor_consumes_fixture(lab, transport):
    fixture = ports.MockResponse(fixture_id="record", source="synthetic fixture",
        method="POST", path="api/records", response={"success": True, "data": {"reply": "fixture"}})
    expression = request("/api/records", transport=transport, method="POST", body=ARRAY,
                         headers={"Content-Type": "application/json"})
    peer, support, context, _ = lab(complete(expression), mode="mock", mock_plan=[fixture], open_now=False)
    with pytest.raises(ActionFailure) as error:
        support.perform(context, permit(mode="mock"), url=peer.url + "/")
    assert error.value.reason is Reason.EVIDENCE_INVALID
    assert received(peer, "/api/records") == []
    assert context.mock_queue.index == 0 and context.mock_recordings == []
    assert NOTE not in context.native.notes


@pytest.mark.parametrize("path,reason", [("/api/redirect", Reason.POLICY_DENIED),
                                         ("/api/stream", Reason.POLICY_DENIED)])
def test_omitted_array_diagnostic_preserves_response_policy(lab, path, reason):
    expression = request(path, method="POST", body=ARRAY, headers={"Content-Type": "application/json"})
    peer, support, context, _ = lab(complete(expression), open_now=False)
    with pytest.raises(ActionFailure) as error:
        support.perform(context, permit(), url=peer.url + "/")
    assert error.value.reason is reason
    assert [r["body"] for r in received(peer, path)] == [ARRAY.encode()]
    assert received(peer, "/api/after-redirect") == []


def test_background_array_cors_denial_remains_visible(lab):
    foreign = Peer()
    lab.peers.append(foreign)
    # text/plain is a simple CORS request: the real POST reaches the server, but
    # its missing response permission must never become a successful observation.
    expression = request(foreign.url + "/api/cors-denied", method="POST", body=ARRAY,
                         headers={"Content-Type": "text/plain"})
    peer, support, context, _ = lab(complete(expression), api=foreign.url, open_now=False)
    with pytest.raises(ActionFailure) as error:
        support.perform(context, permit(), url=peer.url + "/")
    assert error.value.reason is Reason.POLICY_DENIED
    assert [r["body"] for r in received(foreign, "/api/cors-denied")] == [ARRAY.encode()]
    assert context.traffic == []


class ScenarioDriver(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, peer):
        self.peer = peer
        self.contexts = []
        self.evidence = []
        self.browser = BrowserSupport(peer.url, snapshot, network_policy=BrowserNetworkPolicy(
            api_endpoints=(ApiEndpoint(peer.url, "/api", "api"),)))

    def supports_stepwise_mode(self, mode):
        return mode == "live"

    def open_stepwise(self, session, **options):
        context = self.browser.open(context_options=session, **options)
        self.contexts.append(context)
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
        mapping = {"url": self.peer.url + "/"} if permit.action == "open" else {"selector": "#go"}
        result = self.browser.perform(context, permit, **mapping)
        self.evidence.append(result.evidence)
        return result

    def snapshot(self, context):
        return self.browser.snapshot(context)

    def close_stepwise(self, context):
        self.browser.close(context)


def test_same_endpoint_background_array_cannot_supply_missing_primary_request(tmp_path):
    peer = Peer()
    expression = request("/api/records", method="POST", body=ARRAY,
                         headers={"Content-Type": "application/json"})
    peer.page = page("window.done=true;document.querySelector('#go').onclick=()=>{"
                     "window.done=false;setTimeout(()=>{" + complete(expression) + "},0);};")
    scenario = {"schema_version": 1, "scenario": "records.missing_primary", "users": ["reader"], "steps": [
        {"id": "open", "do": "open", "target": "page"},
        {"id": "read", "do": "click", "target": "go", "expect": {
            "request": {"method": "POST", "path": ["api", "records"]},
            "response": [{"check": "status_equals", "value": 200}]}}]}
    path = tmp_path / "missing-primary.yaml"
    path.write_text(yaml.safe_dump(scenario))
    driver = ScenarioDriver(peer)
    bundle = Adapters(Auth(), None, None, driver, InMemoryRecorder,
        lambda action: ports.RequestSpec(action.method, action.path, action.body), NoResponse())
    try:
        report = run_scenario(path, bundle, projections=("e2e",))
        assert [s.status for s in report.domains[0].steps] == ["COMPLETED", "ERROR"]
        assert report.status == "FAILED" and report.passed is False
        assert report.domains[0].steps[-1].detail == "declared UI request missing or ambiguous among associated traffic"
        assert [r["body"] for r in received(peer, "/api/records")] == [ARRAY.encode()]
        assert driver.evidence[-1].traffic == []
        assert driver.evidence[-1].diagnostic_notes == [NOTE]
        assert report.domains[0].provider_recordings == []
        assert all(context.closed for context in driver.contexts)
    finally:
        for context in driver.contexts:
            driver.browser.close(context)
        peer.close()
