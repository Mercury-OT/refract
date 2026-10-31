"""Action-only bindings for two synthetic record editors.

Both readers inspect ordinary product links/forms. Neither receives an expected
ID, a Scenario, or an assertion; BrowserSupport owns exact selection and capture.
"""
import copy
import json
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from refracto import ports
from refracto.query import request_path, wire_query
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport, ObjectTarget


TARGETS = {
    "table": ObjectTarget(
        rows="#records tbody tr", control="button.edit",
        read_id=r"""row => {
          const link = row.querySelector('a');
          const path = link && link.getAttribute('href');
          if (!path || !/^\/records\/[^/]+$/.test(path)) throw new Error('Missing record link');
          return decodeURIComponent(path.slice('/records/'.length));
        }"""),
    "cards": ObjectTarget(
        rows="#records article", control="form button",
        read_id=r"""row => {
          const form = row.querySelector('form');
          const path = form && form.getAttribute('action');
          if (!path || !/^\/records\/[^/]+$/.test(path)) throw new Error('Missing record action');
          return decodeURIComponent(path.slice('/records/'.length));
        }"""),
}


class Auth(ports.Authenticator):
    def __init__(self, origin):
        self.origin = origin

    def identify(self, user):
        if user != "editor":
            raise ValueError("unknown synthetic account")
        return "records-editor"

    def session(self, user):
        return ports.UserSession(
            principal_id=self.identify(user), authentication_id=secrets.token_hex(16),
            credentials={"token": "synthetic-editor-session", "storage_state": {
                "cookies": [], "origins": [{"origin": self.origin, "localStorage": [
                    {"name": "records-session", "value": "synthetic-editor-session"}]}]}})


def resolve_request(action):
    return ports.RequestSpec(action.method, action.path, copy.deepcopy(action.body),
                             query=wire_query(action.query or {}),
                             headers=copy.deepcopy(action.headers or {}))


class Api(ports.ApiDriver):
    def __init__(self, origin):
        self.origin = origin

    def send(self, spec, session):
        headers = dict(spec.headers or {})
        if session is not None:
            headers["Authorization"] = "Bearer " + session["token"]
        if spec.traceparent:
            headers["traceparent"] = spec.traceparent
        data = None
        if spec.body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(spec.body).encode()
        request = Request(self.origin + request_path("/api/" + spec.path, spec.query),
                          data=data, headers=headers, method=spec.method)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as rejected:
            response = rejected
        with response:
            text = response.read().decode()
            return ports.RecordedResponse(
                response.status, dict(response.headers), json.loads(text), text, None, spec,
                request_header_items=list(request.header_items()),
                header_items=list(response.headers.items()))


class Normalizer(ports.ResponseNormalizer):
    def normalize(self, response):
        if type(response.json) is not dict:
            raise ValueError("record response must be a mapping")
        return ports.NormalizedResponse(200 <= response.status < 300,
                                        copy.deepcopy(response.json), response.status, response)


def read_rendered(page):
    editor = page.locator("#editor")
    visible = editor.count() == 1 and editor.is_visible()
    return {"records.editor": {"identified": [],
                               "anonymous": [{"fields": {}}] if visible else []}}


class RecordsUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, app, *, timeout_ms=5000):
        self.origin = app.base_url
        self.mapping = TARGETS[app.implementation]
        self.browser = BrowserSupport(app.base_url, read_rendered, timeout_ms=timeout_ms,
            network_policy=BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(app.base_url, "/api", ""),),
                credential_origins=(app.base_url,)))
        self.evidence = []
        self.closed_contexts = 0

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def supports_object_targeting(self, mode):
        return mode in {"live", "mock"}

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        return self.browser.open(mode, mock_plan=mock_plan, mock_queue=mock_queue,
            context_options={"storage_state": session["storage_state"]}, user=user,
            session_generation=session_generation, context_id=context_id)

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
        if permit.action == "open" and permit.target == "records.page":
            result = self.browser.perform(context, permit, url=self.origin + "/")
        elif permit.action == "click" and permit.target == "records.edit_button":
            result = self.browser.perform(context, permit, object_target=self.mapping)
        else:
            selectors = {"records.name_input": "#name", "records.save_button": "#save"}
            result = self.browser.perform(context, permit, selector=selectors[permit.target])
        self.evidence.append(result.evidence)
        return result

    def snapshot(self, context):
        return self.browser.snapshot(context)

    def close_stepwise(self, context):
        try:
            self.browser.close(context)
        finally:
            self.closed_contexts += 1


def adapters(app, *, timeout_ms=5000):
    return Adapters(Auth(app.base_url), Api(app.base_url), None,
                    RecordsUi(app, timeout_ms=timeout_ms), InMemoryRecorder,
                    resolve_request, Normalizer())
