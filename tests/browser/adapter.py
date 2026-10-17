"""A second product adapter, authored solely for the public synthetic page."""
from refracto import ports
from refracto_browser import BrowserSupport


def read_rendered(page):
    fields = page.evaluate("""() => ({
      url: location.href,
      clicks: window.lab?.clicks || 0,
      inputs: window.lab?.inputs || 0,
      propertyIdentity: window.lab?.propertyIdentity || false,
      staticLoaded: window.staticLoaded === true,
      secureContext: window.isSecureContext,
      randomUuidAvailable: typeof crypto.randomUUID === 'function',
      value: document.querySelector('#value')?.value || '',
      result: document.querySelector('#result')?.textContent || ''
    })""")
    return {"laboratory": {"identified": [{"id": "page", "fields": fields}], "anonymous": []}}


def fields(rendered):
    return rendered["laboratory"]["identified"][0]["fields"]


class SyntheticUi(ports.UiDriver, ports.StepwiseUiDriver):
    """Map declared primitives and rendering without reading assertions."""

    def __init__(self, base_url, *, timeout_ms=1500, read=read_rendered, context_options=None):
        self.base_url = base_url
        self.context_options = context_options
        self.support = BrowserSupport(base_url, read, timeout_ms=timeout_ms)
        self.actions = []
        self.results = []
        self.close_calls = 0
        self.context = None

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None, **identity):
        self.context = self.support.open(mode, mock_plan=mock_plan,
                                         context_options=self.context_options, **identity)
        return self.context

    def perform_step(self, scenario, step, context, permit):
        if step.request is not None:
            self.support.validate_request_headers(context, step.request.headers)
        self.actions.append(permit.action)
        if permit.action == "open":
            outcome = self.support.perform(context, permit, url=self.base_url + "/")
        else:
            outcome = self.support.perform(context, permit, selector="#" + permit.target)
        self.results.append(outcome)
        return outcome

    def snapshot(self, context):
        return self.support.snapshot(context)

    def close_stepwise(self, context):
        self.close_calls += 1
        self.support.close(context)
