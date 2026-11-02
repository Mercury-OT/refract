"""Map approved operations and actual DOM fields, without reading expectations."""
import copy
import secrets

from refracto import ports
from refracto.query import wire_query
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport


class Auth(ports.Authenticator):
    def __init__(self):
        self.session_calls = 0

    def identify(self, user):
        if user != "reader":
            raise ValueError("unknown synthetic account")
        return "records-reader"

    def session(self, user):
        self.session_calls += 1
        return ports.UserSession(principal_id=self.identify(user),
                                 authentication_id=secrets.token_hex(16), credentials={})


def resolve_request(action):
    return ports.RequestSpec(action.method, action.path, copy.deepcopy(action.body),
                             query=wire_query(action.query or {}),
                             headers=copy.deepcopy(action.headers or {}))


class Normalizer(ports.ResponseNormalizer):
    def normalize(self, response):
        payload = response.json
        if (type(payload) is not dict or type(payload.get("success")) is not bool
                or type(payload.get("data")) is not dict):
            raise ValueError("unsupported records response")
        return ports.NormalizedResponse(payload["success"], copy.deepcopy(payload["data"]),
                                        response.status, response)


def _region(page, selector):
    region = page.locator(selector)
    if region.count() != 1 or not region.is_visible():
        raise ValueError("required display region is unavailable")
    return region


def read_rendered(page):
    # The region must exist and be observable before its empty contents are evidence.
    menu = _region(page, "#menu")
    results = _region(page, "#results")
    items = menu.locator("#menu-items")
    if items.count() != 1:
        raise ValueError("menu contents are unavailable")
    return {
        "records.menu_items": {"identified": [], "anonymous": [
            {"fields": {"text": item.inner_text()}}
            for item in items.locator("button").all() if item.is_visible()]},
        "records.result_rows": {"identified": [], "anonymous": [
            {"fields": {"name": item.inner_text()}}
            for item in results.locator("li").all() if item.is_visible()]},
    }


class MenuUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, app):
        self.page_url = app.page_url
        self.browser = BrowserSupport(app.page_url, read_rendered, timeout_ms=5000,
            network_policy=BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(app.page_url, "/api", ""),)))
        self.opened_contexts = 0
        self.closed_contexts = 0
        self.evidence = []

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def supports_hover(self, mode):
        return mode in {"live", "mock"}

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        context = self.browser.open(mode, mock_plan=mock_plan, mock_queue=mock_queue,
            context_options=session, user=user, session_generation=session_generation,
            context_id=context_id)
        self.opened_contexts += 1
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
        if permit.action == "open" and permit.target == "records.page":
            result = self.browser.perform(context, permit, url=self.page_url + "/")
        elif permit.action == "hover" and permit.target == "records.menu_trigger":
            result = self.browser.perform(context, permit, selector="#menu-trigger")
        elif permit.action == "click" and permit.target == "records.archived_menu_item":
            result = self.browser.perform(context, permit, selector="#archived")
        else:
            raise ValueError("unsupported menu action mapping")
        self.evidence.append(result.evidence)
        return result

    def snapshot(self, context):
        return self.browser.snapshot(context)

    def close_stepwise(self, context):
        try:
            self.browser.close(context)
        finally:
            self.closed_contexts += 1


def adapters(app):
    return Adapters(Auth(), None, None, MenuUi(app), InMemoryRecorder,
                    resolve_request, Normalizer())
