"""Only product-owned mappings/authentication; collection stays in BrowserSupport."""
import secrets

from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import BrowserSupport


TARGETS = ("name", "code", "record_id", "category", "page", "list", "filter", "next",
           "create", "read", "update", "delete", "protected_write", "protected_read")


class Auth(ports.Authenticator):
    def __init__(self, page_url):
        self.page_url = page_url

    def identify(self, user):
        if user != "creator":
            raise ValueError("unknown synthetic account")
        return "records-account-creator"

    def session(self, user):
        return ports.UserSession(principal_id=self.identify(user), authentication_id=secrets.token_hex(16),
            credentials={"storage_state": {"cookies": [], "origins": [{"origin": self.page_url,
                "localStorage": [{"name": "record-account", "value": user}]}]}})


def read_rendered(page):
    return {"page": {"identified": [{"id": page.locator('main').get_attribute('data-object-id'),
                                     "fields": {"ready": page.locator('#asset-ready').inner_text()}}],
                     "anonymous": []}}


class RecordsUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, app, *, legacy=False):
        self.page_url = app.page_url
        self.elements = {name: "#" + app.selector_prefix + name for name in TARGETS}
        if legacy:
            self.browser = BrowserSupport(app.page_url, read_rendered, timeout_ms=5000,
                logical_path=lambda path: "records-api" + path.removeprefix(app.api_prefix))
        else:
            from refracto_browser import ApiEndpoint, BrowserNetworkPolicy
            policy = BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(app.api_url, app.api_prefix, "records-api"),),
                resource_origins=(app.static_url,), credential_origins=(app.api_url,))
            self.browser = BrowserSupport(app.page_url, read_rendered, timeout_ms=5000,
                                          network_policy=policy)

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        return self.browser.open(mode, mock_plan=mock_plan, mock_queue=mock_queue,
            context_options=session, user=user, session_generation=session_generation, context_id=context_id)

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
        if permit.action == "open" and permit.target == "records.page":
            return self.browser.perform(context, permit, url=self.page_url + "/")
        return self.browser.perform(context, permit, selector=self.elements[permit.target])

    def snapshot(self, context):
        return self.browser.snapshot(context)

    def close_stepwise(self, context):
        self.browser.close(context)


class Normalizer(ports.ResponseNormalizer):
    def normalize(self, response):
        actual = response.json
        if type(actual) is not dict or type(actual.get("success")) is not bool or type(actual.get("data")) is not dict:
            raise ValueError("invalid records response")
        return ports.NormalizedResponse(actual["success"], actual["data"], response.status, response)


def adapters(app, *, legacy=False):
    return Adapters(Auth(app.page_url), None, None, RecordsUi(app, legacy=legacy),
                    InMemoryRecorder, None, Normalizer())
