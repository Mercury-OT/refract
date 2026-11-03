"""Action-only mappings and read-only observations of the frozen search page."""
import secrets

from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import BrowserSupport


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


class NoResponse(ports.ResponseNormalizer):
    """The runner requires this port; a page-only consumer must never call it."""
    def normalize(self, response):
        raise ValueError("this consumer has no response observations")


def no_request(action):
    raise ValueError("this consumer has no API operations")


def read_rendered(page):
    # The input and its actual association must exist even when the panel is hidden.
    region = page.locator("#search-region")
    inputs = region.locator("#search")
    panels = region.locator("#suggestions")
    if (region.count() != 1 or not region.is_visible() or inputs.count() != 1
            or page.locator("#search").count() != 1 or not inputs.is_visible()
            or panels.count() != 1 or page.locator("#suggestions").count() != 1
            or inputs.get_attribute("aria-controls") != "suggestions"):
        raise ValueError("search input or associated panel is unavailable")
    return {"records.search_input": {"identified": [], "anonymous": [
        {"fields": {"value": inputs.input_value(), "suggestions_visible": panels.is_visible()}}]}}


class SearchUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, app):
        self.page_url = app.page_url
        self.browser = BrowserSupport(app.page_url, read_rendered, timeout_ms=5000)
        self.opened_contexts = 0
        self.closed_contexts = 0
        self.evidence = []

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def supports_key_press(self, mode, key):
        return mode in {"live", "mock"} and key == "Escape"

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        context = self.browser.open(mode, mock_plan=mock_plan, mock_queue=mock_queue,
            context_options=session, user=user, session_generation=session_generation,
            context_id=context_id)
        self.opened_contexts += 1
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
        if permit.action == "open" and permit.target == "records.search_page":
            result = self.browser.perform(context, permit, url=self.page_url + "/")
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


def adapters(app):
    return Adapters(Auth(), None, None, SearchUi(app), InMemoryRecorder,
                    no_request, NoResponse())
