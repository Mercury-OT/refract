"""Bounded browser primitives with request-start association, outside the core."""

import copy
import dataclasses
import json
import math
import os
import threading
import time
import weakref
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from refracto import ports

from ._instrument import SCRIPT


_runtime = threading.local()
_authorizations = weakref.WeakValueDictionary()
_CLOSED_EXECUTION = object()


def _acquire_playwright():
    # Sync Playwright owns one event loop per thread. Multiple helpers may own
    # different browsers on that loop; only the final owner stops the runtime.
    if getattr(_runtime, "playwright", None) is None:
        from playwright.sync_api import sync_playwright

        _runtime.playwright = sync_playwright().start()
        _runtime.users = 0
    _runtime.users += 1
    return _runtime.playwright


def _release_playwright():
    _runtime.users -= 1
    if _runtime.users == 0:
        playwright, _runtime.playwright = _runtime.playwright, None
        playwright.stop()


def _origin(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)
    except Exception:
        raise ValueError("browser URL must be an absolute HTTP URL without credentials") from None


@dataclass(eq=False, repr=False)
class _Context:
    owner: object
    mode: str
    mock_plan: list
    playwright: object = None
    browser: object = None
    browser_context: object = None
    page: object = None
    closed: bool = False
    execution_id: str | None = None
    deadline: float | None = None
    fixture_index: int = 0
    permits: dict = field(default_factory=dict)
    traffic: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    mock_recordings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    traffic_cursor: int = 0
    diagnostic_cursor: int = 0
    mock_cursor: int = 0

    def __repr__(self):
        return "<BrowserSupport context>"


class BrowserSupport:
    """Execute one authorized primitive using an owned, optional Playwright browser.

    URL/selector mappings and read-only rendered-field interpretation belong to
    the caller. Raw port evidence remains sensitive; this helper's repr/errors
    deliberately omit browser handles, URLs, bodies, options, and input values.
    """

    def __init__(self, base_url, read_rendered, logical_path=None, timeout_ms=5000):
        self._origin = _origin(base_url)
        if not callable(read_rendered) or (logical_path is not None and not callable(logical_path)):
            raise ValueError("browser rendering and path mappings must be callable")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, (int, float)) or not math.isfinite(timeout_ms) or timeout_ms <= 0:
            raise ValueError("browser timeout must be positive and finite")
        self._read_rendered = read_rendered
        self._logical_path = logical_path or (lambda path: path.removeprefix("/"))
        self._timeout_ms = timeout_ms
        self._executions = {}
        self._used_actions = set()
        self._used_tokens = set()

    def __repr__(self):
        return "<BrowserSupport>"

    def open(self, mode, mock_plan=None, context_options=None):
        """Create an instrumented context at about:blank; never navigate or log in."""
        if mode not in {"live", "mock"}:
            raise ValueError("unsupported browser mode")
        if mode == "live" and mock_plan is not None:
            raise ValueError("live browser mode does not accept a mock plan")
        if mock_plan is not None and (not isinstance(mock_plan, (list, tuple)) or
                not all(isinstance(item, ports.MockResponse) for item in mock_plan)):
            raise ValueError("browser mock plan must contain explicit MockResponse fixtures")
        if context_options is not None and not isinstance(context_options, dict):
            raise ValueError("browser context options must be a mapping")
        options = dict(context_options or {})
        if options.get("service_workers", "block") != "block":
            raise ValueError("browser service workers are unsupported")
        options["service_workers"] = "block"
        context = _Context(self, mode, copy.deepcopy(list(mock_plan or [])))
        try:
            # Import lazily: even importing this package needs no browser extra.
            context.playwright = _acquire_playwright()
            context.browser = context.playwright.chromium.launch(
                headless=os.environ.get("SAT_HEADED") != "1", timeout=self._timeout_ms)
            context.browser_context = context.browser.new_context(**options)
            context.browser_context.set_default_timeout(self._timeout_ms)
            context.browser_context.set_default_navigation_timeout(self._timeout_ms)
            context.browser_context.add_init_script(SCRIPT)
            context.browser_context.route("**/*", lambda route: self._route(context, route))
            context.page = context.browser_context.new_page()
            context.page.on("pageerror", lambda _: context.errors.append("browser event handler failed"))
            context.page.on("worker", lambda _: context.errors.append("browser workers are unsupported"))
            context.page.on("websocket", lambda _: context.errors.append("browser streaming transport is unsupported"))
            return context
        except Exception:
            self._fail(context, "browser context creation failed")

    def _context(self, context):
        if not isinstance(context, _Context) or context.owner is not self:
            raise ValueError("browser context belongs to another helper")
        if context.closed:
            raise ValueError("browser context is closed")
        return context

    def _remaining(self, context):
        remaining = self._timeout_ms if context.deadline is None else (context.deadline - time.monotonic()) * 1000
        if remaining <= 0:
            raise RuntimeError("browser action collection timed out")
        return remaining

    def _check(self, context):
        if context.errors:
            raise RuntimeError(context.errors[0])
        errors = context.page.evaluate("() => window.__refractBrowser?.errors || []")
        if errors:
            # Browser strings are not trusted error text.
            raise RuntimeError("browser origin instrumentation failed")

    def _authorize(self, context, permit, url, selector):
        if not isinstance(permit, ports.UiActionPermit):
            raise ValueError("browser action requires an action permit")
        if permit.mode != context.mode or permit.action not in {"open", "click", "fill"}:
            raise ValueError("browser action permit is incompatible with context")
        if not all(type(value) is str and value for value in
                   (permit.execution_id, permit.action_id, permit.step_id, permit.token)):
            raise ValueError("browser action permit has invalid identity")
        if permit.action == "open":
            if selector is not None or not isinstance(url, str) or _origin(url) != self._origin:
                raise ValueError("browser open requires one same-origin URL")
        elif url is not None or not isinstance(selector, str) or not selector.strip():
            raise ValueError("browser interaction requires one CSS selector")
        if permit.action == "fill" and type(permit.value) is not str:
            raise ValueError("browser fill requires a string value")
        if permit.action != "fill" and permit.value is not None:
            raise ValueError("browser action does not accept a bound value")
        if context.execution_id not in {None, permit.execution_id}:
            raise ValueError("browser permit belongs to another execution")
        if self._executions.get(permit.execution_id, context) is not context:
            raise ValueError("browser execution is already bound to another context")
        identity = (permit.execution_id, permit.action_id)
        if identity in self._used_actions or permit.token in self._used_tokens or permit.token in _authorizations:
            raise ValueError("browser action authorization was already used")
        context.execution_id = permit.execution_id
        self._executions[permit.execution_id] = context
        self._used_actions.add(identity)
        self._used_tokens.add(permit.token)
        # Keep replay protection while the authorizing helper exists, without
        # making the authorization registry retain a closed context.
        _authorizations[permit.token] = self
        context.permits[permit.action_id] = permit

    def perform(self, context, permit, *, url=None, selector=None):
        """Perform exactly one open, click, or fill, then collect bounded evidence."""
        context = self._context(context)
        self._authorize(context, permit, url, selector)
        context.deadline = time.monotonic() + self._timeout_ms / 1000
        start, diagnostic_start, mock_start = context.traffic_cursor, context.diagnostic_cursor, context.mock_cursor
        try:
            self._check(context)
            if permit.action == "open":
                context.page.goto(url, wait_until="domcontentloaded", timeout=self._remaining(context))
            else:
                # Native CSS parsing excludes Playwright's additional selector engines.
                context.page.wait_for_function("""selector => {
                    const visible = [...document.querySelectorAll(selector)].filter(element => {
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.visibility !== 'hidden' && style.visibility !== 'collapse' && rect.width > 0 && rect.height > 0;
                    });
                    return visible.length > 0;
                }""", arg=selector, timeout=self._remaining(context))
                locator = context.page.locator("css=:is(" + selector + "):visible")
                if locator.count() != 1:
                    raise RuntimeError("browser target is ambiguous")
                context.page.evaluate("""arm => {
                    window.__refractBrowser.armed = arm;
                    window.__refractBrowser.event = null;
                }""", {"action_id": permit.action_id, "selector": selector,
                        "type": "click" if permit.action == "click" else "input"})
                try:
                    if permit.action == "click":
                        locator.click(timeout=self._remaining(context))
                    else:
                        locator.fill(permit.value, timeout=self._remaining(context))
                    self._settle(context, permit.action_id)
                finally:
                    context.page.evaluate("""() => {
                        window.__refractBrowser.armed = null;
                        window.__refractBrowser.event = null;
                        window.__refractBrowser.origin = null;
                    }""")
            if permit.action == "open":
                self._settle(context, permit.action_id)
            self._check(context)
            rendered = self.snapshot(context)
            self._remaining(context)
            current, diagnostics = [], list(context.diagnostics[diagnostic_start:])
            for traffic in context.traffic[start:]:
                if traffic.action_id == permit.action_id:
                    current.append(traffic)
                else:
                    diagnostics.append(traffic.response)
            result = ports.UiActionResult(evidence=ports.UiActionEvidence(
                execution_id=permit.execution_id, action_id=permit.action_id,
                step_id=permit.step_id, mode=permit.mode, permit_token=permit.token,
                traffic=current, rendered=rendered,
                diagnostic_outgoing=[recording.request for recording in diagnostics],
                diagnostic_recorded=diagnostics,
                mock_recordings=list(context.mock_recordings[mock_start:]),
            ))
            context.traffic_cursor = len(context.traffic)
            context.diagnostic_cursor = len(context.diagnostics)
            context.mock_cursor = len(context.mock_recordings)
            return result
        except Exception:
            self._fail(context, "browser action or evidence collection failed")
        finally:
            context.deadline = None

    def _settle(self, context, action_id):
        # Two rendering opportunities plus another pending check cover DOM work
        # following settled transport, without waiting for unrelated network idle.
        for _ in range(2):
            context.page.wait_for_function("""id => {
                const state = window.__refractBrowser;
                return state && !(state.pending[id] > 0);
            }""", arg=action_id, timeout=self._remaining(context))
            context.page.evaluate("""timeout => new Promise((resolve, reject) => {
                const timer = setTimeout(() => reject(new Error('render timeout')), timeout);
                requestAnimationFrame(() => { clearTimeout(timer); resolve(); });
            })""", self._remaining(context))
            self._check(context)

    def _route(self, context, route):
        try:
            request = route.request
            if _origin(request.url) != self._origin:
                raise ValueError("cross-origin browser traffic is unsupported")
            if context.page is not None and request.frame != context.page.main_frame:
                raise ValueError("browser frame traffic is unsupported")
            api = request.resource_type in {"fetch", "xhr"}
            if not api and (request.resource_type not in {
                    "document", "stylesheet", "script", "image", "font", "media", "texttrack", "manifest",
            } or request.method not in {"GET", "HEAD"}):
                raise ValueError("browser request transport is unsupported")
            headers = dict(request.headers)
            action_id = headers.get("x-refract-action-id") if api else None
            request_id = headers.get("x-refract-request-id") if api else None
            permit = context.permits.get(action_id)
            # Routing must never infer origin from the active action or expected request.
            if action_id and permit is None:
                raise ValueError("browser request has an unknown action origin")
            # XHR appends setRequestHeader values. Carry our generated trace in
            # a private marker, then set exactly one effective outgoing header
            # for both transports before recording or sending the request.
            if api and "x-refract-traceparent" in headers:
                headers["traceparent"] = headers["x-refract-traceparent"]
            traceparent = headers.get("traceparent")
            trace_id = traceparent.split("-")[1] if traceparent and len(traceparent.split("-")) == 4 else None
            actual_path = urlsplit(request.url).path
            fixture_id = None
            if api:
                logical_path = self._logical_path(actual_path)
                if type(logical_path) is not str or not logical_path:
                    raise ValueError("browser logical path mapping failed")
                body = None
                if request.post_data is not None:
                    body = json.loads(request.post_data)
                    if body is not None and type(body) is not dict:
                        raise ValueError("browser request body must be a JSON object")
                spec = ports.RequestSpec(request.method, logical_path, body, traceparent)
            if api and context.mode == "mock":
                if context.fixture_index >= len(context.mock_plan):
                    raise ValueError("browser mock plan is exhausted")
                fixture = context.mock_plan[context.fixture_index]
                if (fixture.method, fixture.path) != (spec.method, spec.path):
                    raise ValueError("browser traffic does not match the next mock fixture")
                context.fixture_index += 1
                fixture_id = fixture.fixture_id
                response_body, status = copy.deepcopy(fixture.response), fixture.status
                text = json.dumps(response_body)
                response_headers = {"content-type": "application/json"}
                route.fulfill(status=status, body=text, headers=response_headers)
            else:
                response = route.fetch(
                    headers={name: value for name, value in headers.items() if not name.startswith("x-refract-")},
                    max_redirects=0, timeout=self._remaining(context),
                )
                try:
                    status, response_headers = response.status, dict(response.headers)
                    if 300 <= status < 400 and "location" in response_headers:
                        raise ValueError("browser redirects are unsupported")
                    if "text/event-stream" in response_headers.get("content-type", "").lower():
                        raise ValueError("browser streaming responses are unsupported")
                    if api:
                        text = response.text()
                        try:
                            response_body = json.loads(text)
                        except (ValueError, TypeError):
                            response_body = None
                    route.fulfill(response=response)
                finally:
                    response.dispose()
            if api:
                recorded = ports.RecordedResponse(
                    status, response_headers, response_body, text, trace_id, dataclasses.replace(spec),
                    step_id=permit.step_id if permit else None, actual_path=actual_path,
                    request_id=request_id, mock_fixture_id=fixture_id,
                )
                if context.mode == "mock":
                    context.mock_recordings.append(recorded)
                if permit is None:
                    context.diagnostics.append(recorded)
                else:
                    if not request_id:
                        raise ValueError("browser request identifier is missing")
                    context.traffic.append(ports.UiTraffic(
                        execution_id=permit.execution_id, action_id=permit.action_id,
                        step_id=permit.step_id, mode=permit.mode, request_id=request_id,
                        permit_token=permit.token, request=spec, response=recorded,
                        mock_fixture_id=fixture_id,
                    ))
        except Exception:
            context.errors.append("browser request transport or recording failed")
            try:
                route.abort()
            except Exception:
                context.errors.append("browser request cleanup failed")

    def snapshot(self, context):
        """Read product-owned rendering without executing another primitive."""
        context = self._context(context)
        try:
            self._check(context)
            rendered = self._read_rendered(context.page)
            if type(rendered) is not dict:
                raise ValueError("browser rendered snapshot must be a mapping")
            self._check(context)
            return rendered
        except Exception:
            self._fail(context, "browser rendered snapshot failed")

    def close(self, context):
        """Release every owned resource, including after a partial open; repeat-safe."""
        if not isinstance(context, _Context) or context.owner is not self:
            raise ValueError("browser context belongs to another helper")
        if context.closed:
            return
        context.closed = True
        if self._executions.get(context.execution_id) is context:
            # Reserve the execution without retaining the closed browser and
            # its raw evidence through the helper's lifetime.
            self._executions[context.execution_id] = _CLOSED_EXECUTION
        failed = False
        for resource, method in ((context.browser_context, "close"), (context.browser, "close")):
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception:
                    failed = True
        if context.playwright is not None:
            try:
                _release_playwright()
            except Exception:
                failed = True
        if failed:
            raise RuntimeError("browser resource cleanup failed") from None

    def _fail(self, context, message):
        try:
            self.close(context)
        except Exception:
            raise RuntimeError("browser operation and resource cleanup failed") from None
        raise RuntimeError(message) from None
