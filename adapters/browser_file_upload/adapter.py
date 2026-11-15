"""Map one action at a time; browser collection and orchestration stay shared."""
import secrets

from adapters.file_upload.adapter import (
    UploadApiDriver, UploadNormalizer, resolve_documents, resolve_records,
)
from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport


MAPPINGS = {
    "documents": {"page": "/documents", "prefix": "/v1", "input": "#document-file",
                  "list": "#document-uploads", "region": "#document-results",
                  "actions": {("fill", "title_input"): "#document-title",
                              ("select_file", "attachment_input"): "#document-file",
                              ("click", "upload_button"): "#document-upload"}},
    "records": {"page": "/records", "prefix": "/vault", "input": "#record-blob",
                "list": "#record-attachments", "region": "#record-results",
                "actions": {("fill", "caption_input"): "#record-caption",
                            ("select_file", "attachment_input"): "#record-blob",
                            ("click", "upload_button"): "#record-attach"}},
}


class Auth(ports.Authenticator):
    def __init__(self, origin):
        self.origin = origin
        self.session_calls = 0

    def identify(self, user):
        if user != "editor":
            raise ValueError("unknown synthetic upload user")
        return "upload-editor"

    def session(self, user):
        principal = self.identify(user)
        self.session_calls += 1
        return ports.UserSession(principal_id=principal, authentication_id=secrets.token_hex(16),
            credentials={"token": "example-editor", "storage_state": {"cookies": [], "origins": [{
                "origin": self.origin,
                "localStorage": [{"name": "upload-session", "value": "example-editor"}]}]}})


class CountingApi(UploadApiDriver):
    def __init__(self, origin):
        super().__init__(origin)
        self.calls = []

    def send(self, request, session):
        self.calls.append((request.method, request.path))
        return super().send(request, session)


def read_rendered(page, product):
    mapping = MAPPINGS[product]
    selected = page.locator(mapping["input"])
    region = page.locator(mapping["region"])
    rows = page.locator(mapping["list"])
    if (selected.count() != 1 or not selected.is_visible()
            or region.count() != 1 or not region.is_visible() or rows.count() != 1):
        raise ValueError("upload display region is unavailable")
    files = selected.evaluate("el => Array.from(el.files, f => ({filename: f.name, size: f.size}))")
    return {
        product + ".selected_files": {"identified": [], "anonymous": [
            {"fields": fields} for fields in files]},
        product + ".uploaded_files": {"identified": [], "anonymous": [
            {"fields": {"filename": row.inner_text()}}
            for row in rows.locator("li").all() if row.is_visible()]},
    }


class UploadUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, origin, product, *, timeout_ms=5000, file_config=None):
        self.origin, self.product = origin, product
        self.mapping = MAPPINGS[product]
        self.browser = BrowserSupport(origin, lambda page: read_rendered(page, product),
            timeout_ms=timeout_ms, file_config=file_config,
            network_policy=BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(origin, self.mapping["prefix"], ""),),
                credential_headers={"x-upload-session": (origin,)}))
        self.evidence = []
        self.opened_contexts = 0
        self.closed_contexts = 0

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def supports_file_selection(self, mode):
        return self.browser.supports_file_selection(mode)

    def supports_file_requests(self, mode):
        return self.browser.supports_file_requests(mode)

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        context = self.browser.open(mode, mock_plan=mock_plan, mock_queue=mock_queue,
            context_options={"storage_state": session["storage_state"]}, user=user,
            session_generation=session_generation, context_id=context_id)
        self.opened_contexts += 1
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
        if permit.action == "open" and permit.target == self.product + ".upload_page":
            result = self.browser.perform(context, permit, url=self.origin + self.mapping["page"])
        else:
            selectors = {(action, self.product + "." + target): selector
                         for (action, target), selector in self.mapping["actions"].items()}
            selector = selectors.get((permit.action, permit.target))
            if selector is None:
                raise ValueError("unsupported upload action mapping")
            result = self.browser.perform(context, permit, selector=selector)
        self.evidence.append(result.evidence)
        return result

    def snapshot(self, context):
        return self.browser.snapshot(context)

    def close_stepwise(self, context):
        try:
            self.browser.close(context)
        finally:
            self.closed_contexts += 1


def build_adapters(origin, product="documents", *, timeout_ms=5000, file_config=None):
    if product not in MAPPINGS:
        raise ValueError("unknown browser upload consumer")
    return Adapters(Auth(origin), CountingApi(origin), None,
        UploadUi(origin, product, timeout_ms=timeout_ms, file_config=file_config), InMemoryRecorder,
        resolve_documents if product == "documents" else resolve_records, UploadNormalizer(product))
