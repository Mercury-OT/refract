"""Primitive Playwright adapter with bounded event-origin request correlation.

Synchronous fetches created by a targeted event carry that event's action ID.
Fetches after an untracked async continuation remain diagnostic. Waiting for
handler promises is only a completion barrier, never a correlation mechanism.
Mock routes consume explicit caller fixtures; missing fixtures abort, not fall
through to a real backend. No scenario ID or expectation determines actions.
"""
import copy
import dataclasses
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from refracto import ports


_INSTRUMENT = r"""(() => {
  const originalAdd = EventTarget.prototype.addEventListener;
  const originalFetch = window.fetch.bind(window);
  const state = window.__refract = {armed: null, origin: null, pending: 0};
  EventTarget.prototype.addEventListener = function(type, listener, options) {
    if (typeof listener !== 'function') return originalAdd.call(this, type, listener, options);
    return originalAdd.call(this, type, function(event) {
      const previous = state.origin;
      const arm = state.armed;
      state.origin = arm && arm.type === event.type && event.target.closest?.(arm.selector)
        ? arm.action_id : null;
      let result;
      try { result = listener.call(this, event); }
      finally { state.origin = previous; }
      if (result && typeof result.then === 'function') {
        state.pending++;
        Promise.resolve(result).finally(() => state.pending--);
      }
      return result;
    }, options);
  };
  window.fetch = function(input, init = {}) {
    const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
    const hex = n => Array.from(crypto.getRandomValues(new Uint8Array(n)), x => x.toString(16).padStart(2,'0')).join('');
    headers.set('x-refract-request-id', crypto.randomUUID());
    if (state.origin) headers.set('x-refract-action-id', state.origin);
    headers.set('traceparent', '00-' + hex(16) + '-' + hex(8) + '-01');
    return originalFetch(input, {...init, headers});
  };
})();"""


@dataclass
class _Context:
    playwright: object
    browser: object
    browser_context: object
    page: object
    mode: str
    mock_plan: list
    fixture_index: int = 0
    permits: dict = field(default_factory=dict)
    traffic: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    mock_recordings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


class DemoUiDriver(ports.UiDriver, ports.StepwiseUiDriver):
    _TARGETS = {
        "items.new_button": '[data-testid="new-btn"]',
        "items.name_input": '[data-testid="item-name"]',
        "items.submit_button": '[data-testid="create-btn"]',
        "records.new_button": '[data-testid="new-btn"]',
        "records.name_input": '[data-testid="item-name"]',
        "records.submit_button": '[data-testid="create-btn"]',
    }

    def __init__(self, config):
        self._config = config

    def supports_stepwise_mode(self, mode):
        return mode in {"mock", "live"}

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None):
        pw = sync_playwright().start()
        browser = browser_context = None
        try:
            browser = pw.chromium.launch(headless=os.environ.get("SAT_HEADED") != "1")
            browser_context = browser.new_context()
            browser_context.add_init_script(_INSTRUMENT)
            page = browser_context.new_page()
            context = _Context(pw, browser, browser_context, page, mode, mock_plan or [])
            page.route("**/*", lambda route: self._route(context, route))
            return context
        except Exception:
            if browser_context is not None:
                browser_context.close()
            if browser is not None:
                browser.close()
            pw.stop()
            raise

    def perform_step(self, scenario, step, context, permit):
        context.permits[permit.action_id] = permit
        start = len(context.traffic)
        diagnostic_start = len(context.diagnostics)
        mock_start = len(context.mock_recordings)
        page = context.page
        if permit.action == "open":
            if permit.target not in {"items.page", "records.page"}:
                raise ValueError("unknown page target")
            page.goto(self._config.base_url + "/", wait_until="networkidle")
        else:
            selector = self._TARGETS.get(permit.target)
            if selector is None:
                raise ValueError("unknown element target")
            locator = page.locator(selector)
            if locator.count() != 1:
                raise ValueError("UI target is missing or ambiguous")
            page.evaluate("arm => window.__refract.armed = arm", {
                "action_id": permit.action_id, "selector": selector,
                "type": "click" if permit.action == "click" else "input",
            })
            try:
                if permit.action == "click":
                    locator.click()
                elif permit.action == "fill":
                    if type(permit.value) is not str:
                        raise TypeError("demo text input requires a string value")
                    locator.fill(permit.value)
                else:
                    raise ValueError("unsupported primitive")
                page.wait_for_function("window.__refract.pending === 0")
                page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            finally:
                page.evaluate("window.__refract.armed = null")
        if context.errors:
            raise ValueError(context.errors[0])
        # A delayed earlier action's response is retained but cannot be assigned
        # to the current step just because it arrived during its completion.
        current, diagnostics = [], list(context.diagnostics[diagnostic_start:])
        for traffic in context.traffic[start:]:
            if traffic.action_id == permit.action_id:
                current.append(traffic)
            else:
                diagnostics.append(traffic.response)
        return ports.UiActionResult(evidence=ports.UiActionEvidence(
            execution_id=permit.execution_id, action_id=permit.action_id,
            step_id=permit.step_id, mode=permit.mode, permit_token=permit.token,
            traffic=current, rendered=self.snapshot(context),
            diagnostic_outgoing=[r.request for r in diagnostics],
            diagnostic_recorded=diagnostics,
            mock_recordings=list(context.mock_recordings[mock_start:]),
        ))

    def _route(self, context, route):
        request = route.request
        url = urlparse(request.url)
        base = urlparse(self._config.base_url)
        # The local app document/static assets are not mock API responses.
        if request.resource_type not in {"fetch", "xhr"}:
            if (url.scheme, url.netloc) != (base.scheme, base.netloc):
                context.errors.append("cross-origin resource not allowed")
                route.abort()
            else:
                route.continue_()
            return
        try:
            if (url.scheme, url.netloc) != (base.scheme, base.netloc):
                raise ValueError("cross-origin API traffic not allowed")
            request_id = request.headers.get("x-refract-request-id")
            action_id = request.headers.get("x-refract-action-id")
            permit = context.permits.get(action_id)
            traceparent = request.headers.get("traceparent")
            trace_id = traceparent.split("-")[1] if traceparent else None
            try:
                body = request.post_data_json
            except Exception:
                body = None
            spec = ports.RequestSpec(request.method, url.path.lstrip("/"), body, traceparent)
            fixture_id = None
            if context.mode == "mock":
                if context.fixture_index >= len(context.mock_plan):
                    raise ValueError("unmatched mock traffic: plan exhausted")
                fixture = context.mock_plan[context.fixture_index]
                if (fixture.method, fixture.path) != (spec.method, spec.path):
                    raise ValueError("unmatched mock traffic: ordered fixture differs")
                fixture_id = fixture.fixture_id
                context.fixture_index += 1
                response_body, status = copy.deepcopy(fixture.response), fixture.status
                text, headers = json.dumps(response_body), {"content-type": "application/json"}
                route.fulfill(status=status, json=response_body)
            else:
                response = route.fetch(headers={k: v for k, v in request.headers.items()
                                                if not k.startswith("x-refract-")})
                status, headers, text = response.status, dict(response.headers), response.text()
                try:
                    response_body = response.json()
                except Exception:
                    response_body = None
                route.fulfill(response=response)
            recorded = ports.RecordedResponse(
                status, headers, response_body, text, trace_id, dataclasses.replace(spec),
                step_id=permit.step_id if permit else None, actual_path=url.path,
                request_id=request_id, mock_fixture_id=fixture_id,
            )
            if context.mode == "mock":
                context.mock_recordings.append(recorded)
            if permit is None:
                context.diagnostics.append(recorded)
            else:
                context.traffic.append(ports.UiTraffic(
                    execution_id=permit.execution_id, action_id=permit.action_id,
                    step_id=permit.step_id, mode=permit.mode, request_id=request_id,
                    permit_token=permit.token, request=spec, response=recorded,
                    mock_fixture_id=fixture_id,
                ))
        except Exception as exc:
            context.errors.append(str(exc))
            route.abort()

    def snapshot(self, context):
        identified, anonymous = [], []
        rows = context.page.locator('[data-testid="item-row"]')
        for index in range(rows.count()):
            row = rows.nth(index)
            try:
                fields = json.loads(row.get_attribute("data-object-fields") or "{}")
            except (TypeError, json.JSONDecodeError):
                fields = {}
            fields = fields if type(fields) is dict else {}
            object_id = row.get_attribute("data-object-id")
            if object_id:
                identified.append({"id": object_id, "fields": fields})
            else:
                anonymous.append({"fields": fields})
        rendered = {"identified": identified, "anonymous": anonymous}
        return {"items.rows": rendered, "records.rows": rendered, "item_row": rendered}

    def close_stepwise(self, context):
        try:
            context.browser_context.close()
        finally:
            try:
                context.browser.close()
            finally:
                context.playwright.stop()
