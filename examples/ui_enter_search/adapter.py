"""Action-only mappings and read-only DOM fields for the frozen search target."""
import copy
import secrets

from refracto import ports
from refracto.query import wire_query
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport


class Auth(ports.Authenticator):
    def __init__(self, origin):
        self.origin = origin
        self.session_calls = 0

    def identify(self, user):
        if user != "reader":
            raise ValueError("unknown synthetic account")
        return "records-reader"

    def session(self, user):
        principal = self.identify(user)
        self.session_calls += 1
        return ports.UserSession(
            principal_id=principal, authentication_id=secrets.token_hex(16),
            credentials={"storage_state": {"cookies": [], "origins": [{
                "origin": self.origin, "localStorage": [{
                    "name": "records-session", "value": "synthetic-reader-session"}]}]}})


class NoApi(ports.ApiDriver):
    """This e2e-only example cannot create or repair a search through an API port."""
    def __init__(self):
        self.send_calls = 0

    def send(self, spec, session):
        self.send_calls += 1
        raise ValueError("this consumer supports browser e2e only")


def resolve_request(action):
    return ports.RequestSpec(action.method, action.path, copy.deepcopy(action.body),
                             query=wire_query(action.query or {}),
                             headers=copy.deepcopy(action.headers or {}))


class Normalizer(ports.ResponseNormalizer):
    def normalize(self, response):
        if type(response.json) is not dict:
            raise ValueError("search response must be a mapping")
        return ports.NormalizedResponse(200 <= response.status < 300,
                                        copy.deepcopy(response.json), response.status, response)


def read_rendered(page):
    inputs = [{"fields": {"value": item.input_value()}}
              for item in page.locator("#search").all() if item.is_visible()]
    rows = [{"fields": {"name": item.inner_text()}}
            for item in page.locator("#records li").all() if item.is_visible()]
    return {
        "records.search_input": {"identified": [], "anonymous": inputs},
        "records.result_rows": {"identified": [], "anonymous": rows},
    }


class SearchUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, app, *, timeout_ms=5000):
        self.origin = app.base_url
        self.browser = BrowserSupport(app.base_url, read_rendered, timeout_ms=timeout_ms,
            network_policy=BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(app.base_url, "/api", ""),),
                credential_origins=(app.base_url,)))
        self.evidence = []
        self.opened_contexts = 0
        self.closed_contexts = 0

    def supports_stepwise_mode(self, mode):
        return mode == "live"

    def supports_key_press(self, mode, key):
        return mode == "live" and key == "Enter"

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        context = self.browser.open(mode, mock_plan=mock_plan, mock_queue=mock_queue,
            context_options={"storage_state": session["storage_state"]}, user=user,
            session_generation=session_generation, context_id=context_id)
        self.opened_contexts += 1
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
        if permit.action == "open" and permit.target == "records.search_page":
            result = self.browser.perform(context, permit, url=self.origin + "/")
        elif permit.action in {"fill", "press"} and permit.target == "records.search_input":
            result = self.browser.perform(context, permit, selector="#search")
        else:
            raise ValueError("unsupported search action mapping")
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
    return Adapters(Auth(app.base_url), NoApi(), None,
                    SearchUi(app, timeout_ms=timeout_ms), InMemoryRecorder,
                    resolve_request, Normalizer())
