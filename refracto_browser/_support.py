"""Bounded browser primitives with request-start association, outside the core."""

import copy
import json
import math
import os
import threading
import time
import weakref
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from refracto import ports
from refracto.errors import ActionFailure, ActionFailureReason as Reason, safe_action_failure
from refracto.headers import header_map, match_headers, require_header_items, validate_name
from refracto.query import parse_query

from ._instrument import SCRIPT, NATIVE_SCRIPT
from ._policy import BrowserNetworkPolicy
from ._native import NativeCollector
from ._navigation import NavigationCollector
from ._request_body import is_form_content_type, parse_form_body
from ._object_target import ObjectTarget, PinnedObjectTarget, require_browser_id
from ._key_press import KeyPressBoundary, PinnedKeyPress
from ._hover import PinnedHover


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
    mock_queue: object = None
    user: str | None = None
    session_generation: int = 0
    context_id: str = ""
    playwright: object = None
    browser: object = None
    browser_context: object = None
    page: object = None
    closed: bool = False
    execution_id: str | None = None
    deadline: float | None = None
    permits: dict = field(default_factory=dict)
    traffic: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    mock_recordings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    credential_header_names: frozenset = field(default_factory=frozenset)
    pending_mock_responses: dict = field(default_factory=dict)
    mock_response_events: dict = field(default_factory=dict)
    traffic_cursor: int = 0
    diagnostic_cursor: int = 0
    mock_cursor: int = 0
    native: object = None
    navigation: object = None
    key_boundary: object = None
    block_unassociated_mock: bool = False
    diagnostic_notes: list = field(default_factory=list)

    def __repr__(self):
        return "<BrowserSupport context>"


class BrowserSupport:
    """Execute one authorized primitive using an owned, optional Playwright browser.

    URL/selector mappings and read-only rendered-field interpretation belong to
    the caller. Raw port evidence remains sensitive; this helper's repr/errors
    deliberately omit browser handles, URLs, bodies, options, and input values.
    After the first hover or Escape authorization in a context, unassociated mock API
    requests are blocked with an explicit framework error for that context, including
    deferred arrivals in later steps or Flow nodes. They never consume ordered
    fixtures or reach a live service. Live diagnostics and other mock
    contexts retain their existing behavior.
    """

    def __init__(self, base_url, read_rendered, logical_path=None, timeout_ms=5000, *, network_policy=None):
        self._origin = _origin(base_url)
        if network_policy is not None and (type(network_policy) is not BrowserNetworkPolicy or logical_path is not None):
            raise ValueError("native browser policy cannot use a logical-path callback")
        self._network_policy = network_policy
        self._page_origin = network_policy.bind(base_url) if network_policy is not None else None
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

    def open(self, mode, mock_plan=None, context_options=None, *, mock_queue=None,
             user=None, session_generation=0, context_id=""):
        """Create an instrumented context at about:blank; never navigate or log in."""
        if mode not in {"live", "mock"}:
            raise ValueError("unsupported browser mode")
        if mode == "live" and mock_plan is not None:
            raise ValueError("live browser mode does not accept a mock plan")
        if mode == "live" and mock_queue is not None:
            raise ValueError("live browser mode does not accept a mock queue")
        if mock_queue is not None and (type(mock_queue) is not ports.MockResponseQueue
                or type(mock_queue.index) is not int or mock_queue.index < 0
                or type(mock_queue.plan) is not list
                or not all(type(item) is ports.MockResponse for item in mock_queue.plan)):
            raise ValueError("browser mock queue must be an explicit run-local cursor")
        if (user is not None and (type(user) is not str or not user.strip())) or (
                type(session_generation) is not int or session_generation < 0) or type(context_id) is not str:
            raise ValueError("browser context binding is invalid")
        if context_id and ((user is None and session_generation != 0)
                           or (user is not None and session_generation < 1)):
            raise ValueError("browser context user/session binding is invalid")
        if mock_plan is not None and (not isinstance(mock_plan, (list, tuple)) or
                not all(isinstance(item, ports.MockResponse) for item in mock_plan)):
            raise ValueError("browser mock plan must contain explicit MockResponse fixtures")
        if context_options is not None and not isinstance(context_options, dict):
            raise ValueError("browser context options must be a mapping")
        options = dict(context_options or {})
        if context_id and user is None and (any(key in options for key in
                ("storage_state", "http_credentials", "client_certificates"))
                or any(str(key).lower() in {"authorization", "cookie", "proxy-authorization"}
                       for key in options.get("extra_http_headers", {}))):
            raise ValueError("anonymous browser context cannot inherit authentication")
        if options.get("service_workers", "block") != "block":
            raise ValueError("browser service workers are unsupported")
        options["service_workers"] = "block"
        if self._network_policy is not None:
            self._network_policy.validate_context_options(self._page_origin, options)
        plan = copy.deepcopy(list(mock_plan or []))
        queue = mock_queue or ports.MockResponseQueue(plan)
        context = _Context(self, mode, queue.plan, mock_queue=queue, user=user,
                           session_generation=session_generation, context_id=context_id,
                           credential_header_names=frozenset(
                               name.lower() for name in options.get("extra_http_headers", {}))
                           | frozenset(self._network_policy.credential_headers if self._network_policy is not None else ()))
        try:
            # Import lazily: even importing this package needs no browser extra.
            context.playwright = _acquire_playwright()
            context.browser = context.playwright.chromium.launch(
                headless=os.environ.get("SAT_HEADED") != "1", timeout=self._timeout_ms)
            context.browser_context = context.browser.new_context(**options)
            context.browser_context.set_default_timeout(self._timeout_ms)
            context.browser_context.set_default_navigation_timeout(self._timeout_ms)
            context.browser_context.add_init_script(NATIVE_SCRIPT if self._network_policy is not None else SCRIPT)
            if self._network_policy is None:
                context.browser_context.route("**/*", lambda route: self._route(context, route))
            context.page = context.browser_context.new_page()
            if self._network_policy is not None:
                context.native = NativeCollector(self, context, self._network_policy, self._page_origin)
            context.page.on("response", lambda response: self._capture_mock_headers(context, response))
            # This is deliberately a whole-page policy, not proof that an
            # uncaught exception belongs to the current action's handler.
            context.page.on("pageerror", lambda _: context.errors.append(Reason.PAGE_ERROR))
            context.page.on("worker", lambda _: context.errors.append(Reason.POLICY_DENIED))
            context.page.on("websocket", lambda _: context.errors.append(Reason.POLICY_DENIED))
            return context
        except Exception as error:
            self._fail(context, self._reason(context, error))

    def _context(self, context):
        if not isinstance(context, _Context) or context.owner is not self:
            raise ValueError("browser context belongs to another helper")
        if context.closed:
            raise ValueError("browser context is closed")
        return context

    def validate_request_header_names(self, context, names):
        """Reject credential-name collisions without receiving expected values."""
        context = self._context(context)
        if type(names) is not tuple:
            raise ValueError("business header names must be a normalized tuple")
        normalized = tuple(validate_name(name, business=True) for name in names)
        if normalized != names or tuple(sorted(set(normalized))) != normalized:
            raise ValueError("business header names must be unique, lowercase and sorted")
        if context.credential_header_names.intersection(normalized):
            raise ValueError("business request headers collide with browser credentials")

    def _capture_mock_headers(self, context, response):
        # Event callbacks do not yield while reading headers or remove the
        # pending association. The action collector owns that finite work.
        if response.request in context.pending_mock_responses:
            context.mock_response_events[response.request] = response

    def _collect_mock_headers(self, context, recordings):
        requests = {id(recording): request for request, recording
                    in context.pending_mock_responses.items()}
        for recording in recordings:
            if recording.header_items is not None:
                continue
            request = requests[id(recording)]
            while request not in context.mock_response_events:
                self._check(context)
                context.page.wait_for_timeout(min(10, self._remaining(context)))
            response = context.mock_response_events[request]
            # Observe the fulfilled browser response, including headers added by
            # Playwright (for example Content-Length), before claiming completeness.
            items = [(item["name"], item["value"]) for item in response.headers_array()]
            require_header_items(items)
            recording.header_items = items
            recording.headers = {name.lower(): value for name, value in items}
            context.pending_mock_responses.pop(request)
            context.mock_response_events.pop(request)
            self._remaining(context)

    def _remaining(self, context):
        remaining = self._timeout_ms if context.deadline is None else (context.deadline - time.monotonic()) * 1000
        if remaining <= 0:
            raise ActionFailure(Reason.COLLECTION_TIMEOUT)
        return remaining

    def _check(self, context):
        if context.errors:
            reason = context.errors[0]
            raise ActionFailure(reason if type(reason) is Reason else Reason.EVIDENCE_INVALID)
        errors = context.page.evaluate("() => window.__refractBrowser?.errors || []")
        if errors:
            # Browser strings are not trusted error text.
            raise ActionFailure(Reason.EVIDENCE_INVALID)

    @staticmethod
    def _reason(context, error, fallback=Reason.COLLECTION_FAILED):
        # Prefer the first known host failure: a policy abort can make an
        # unrelated Playwright call fail before _check observes the ledger.
        if context.errors:
            reason = context.errors[0]
            return reason if type(reason) is Reason else Reason.EVIDENCE_INVALID
        if safe_action_failure(error) is not None:
            return error.reason
        # Import only while executing the optional browser path. Never inspect
        # arbitrary exception text or use a custom class name as a category.
        if fallback is Reason.TARGET_UNAVAILABLE:
            return fallback
        if isinstance(error, TimeoutError):
            return Reason.COLLECTION_TIMEOUT
        try:
            from playwright.sync_api import TimeoutError as BrowserTimeout
        except ImportError:
            return fallback
        if isinstance(error, BrowserTimeout):
            return Reason.COLLECTION_TIMEOUT
        return fallback

    def _authorize(self, context, permit, url, selector, object_target=None):
        if not isinstance(permit, ports.UiActionPermit):
            raise ValueError("browser action requires an action permit")
        if permit.mode != context.mode or permit.action not in {"open", "click", "fill", "press", "hover"}:
            raise ValueError("browser action permit is incompatible with context")
        for name in ("user", "session_generation", "context_id"):
            actual, expected = getattr(permit, name), getattr(context, name)
            if type(actual) is not type(expected) or actual != expected:
                raise ValueError("browser action permit belongs to another user/session/context")
        if not all(type(value) is str and value for value in
                   (permit.execution_id, permit.action_id, permit.step_id, permit.token)):
            raise ValueError("browser action permit has invalid identity")
        if object_target is not None:
            if (type(object_target) is not ObjectTarget or permit.action != "click"
                    or url is not None or selector is not None or permit.object_id is None):
                raise ValueError("browser object selection requires one scoped click mapping")
            require_browser_id(permit.object_id)
        elif permit.object_id is not None:
            raise ValueError("browser scoped click requires an object target mapping")
        elif permit.action == "open":
            if selector is not None or not isinstance(url, str) or _origin(url) != self._origin:
                raise ValueError("browser open requires one same-origin URL")
        elif url is not None or not isinstance(selector, str) or not selector.strip():
            raise ValueError("browser interaction requires one CSS selector")
        if permit.action == "fill" and type(permit.value) is not str:
            raise ValueError("browser fill requires a string value")
        if permit.action != "fill" and permit.value is not None:
            raise ValueError("browser action does not accept a bound value")
        if (permit.action == "press" and (type(permit.key) is not str or permit.key not in {"Enter", "Escape"})
                or permit.action != "press" and permit.key is not None):
            raise ValueError("browser action key is invalid")
        if context.execution_id not in {None, permit.execution_id}:
            raise ValueError("browser permit belongs to another execution")
        execution_key = (permit.execution_id, permit.context_id)
        if self._executions.get(execution_key, context) is not context:
            raise ValueError("browser execution is already bound to another context")
        identity = (permit.execution_id, permit.action_id)
        if identity in self._used_actions or permit.token in self._used_tokens or permit.token in _authorizations:
            raise ValueError("browser action authorization was already used")
        context.execution_id = permit.execution_id
        self._executions[execution_key] = context
        self._used_actions.add(identity)
        self._used_tokens.add(permit.token)
        # Keep replay protection while the authorizing helper exists, without
        # making the authorization registry retain a closed context.
        _authorizations[permit.token] = self
        context.permits[permit.action_id] = permit
        if permit.action == "hover" or permit.action == "press" and permit.key == "Escape":
            # These page-only actions have no ordered request fixture. Keep the
            # protection for deferred callbacks on the reused context as well.
            # Contexts without these actions retain their legacy policy.
            context.block_unassociated_mock = True

    def perform(self, context, permit, *, url=None, selector=None, object_target=None):
        """Perform one authorized primitive, then collect bounded evidence."""
        context = self._context(context)
        self._authorize(context, permit, url, selector, object_target)
        if context.navigation is not None:
            context.navigation.opening = object_target is None
        context.deadline = time.monotonic() + self._timeout_ms / 1000
        start, diagnostic_start, mock_start = context.traffic_cursor, context.diagnostic_cursor, context.mock_cursor
        pressed = None
        hovered = None
        failure_phase = Reason.COLLECTION_FAILED
        try:
            self._check(context)
            if context.key_boundary is not None:
                context.key_boundary.check()
            if context.key_boundary is not None and permit.action not in {"press", "hover"}:
                # Only after checking the protected idle gap may the next
                # explicitly authorized action resume its existing semantics.
                context.key_boundary.protected = False
            selection = None
            key_press = None
            hover = None
            if permit.action == "open":
                if context.navigation is not None:
                    context.navigation.opening = True
                context.page.goto(url, wait_until="domcontentloaded", timeout=self._remaining(context))
            else:
                failure_phase = Reason.TARGET_UNAVAILABLE
                pinned = None
                if permit.action == "press":
                    if context.key_boundary is None:
                        context.key_boundary = KeyPressBoundary(context)
                    context.key_boundary.begin()
                    pressed = PinnedKeyPress(context.page, selector, permit.action_id, key=permit.key)
                elif permit.action == "hover":
                    if context.key_boundary is None:
                        context.key_boundary = KeyPressBoundary(context)
                    context.key_boundary.begin(kind="hover")
                    hovered = PinnedHover(context.page, selector, permit.action_id,
                                          lambda: self._remaining(context))
                elif object_target is not None:
                    if context.navigation is None:
                        context.navigation = NavigationCollector(self, context)
                    context.navigation.begin(permit)
                    pinned = PinnedObjectTarget(context.page, object_target, permit.object_id,
                                                permit.action_id, lambda: self._remaining(context))
                    locator = pinned.control
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
                        raise ActionFailure(Reason.TARGET_UNAVAILABLE)
                    context.page.evaluate("""arm => {
                    window.__refractBrowser.armed = arm;
                    window.__refractBrowser.event = null;
                    }""", {"action_id": permit.action_id, "selector": selector,
                        "type": "click" if permit.action == "click" else "input"})
                try:
                    failure_phase = Reason.COLLECTION_FAILED
                    if permit.action == "press":
                        # page.keyboard has no locator focus or click behavior.
                        # The capture guard revalidates each actual trusted event.
                        context.page.keyboard.down(permit.key)
                        context.page.keyboard.up(permit.key)
                    elif permit.action == "hover":
                        context.page.mouse.move(**hovered.position)
                    elif permit.action == "click":
                        locator.click(timeout=self._remaining(context))
                    else:
                        locator.fill(permit.value, timeout=self._remaining(context))
                    if pinned is not None:
                        context.navigation.check(wait=True)
                    self._settle(context, permit.action_id)
                    if pinned is not None:
                        selection = context.navigation.selection()
                finally:
                    try:
                        # A rejected secondary target can leave the opener's
                        # renderer unresponsive. Owning-resource cleanup below
                        # must not wait for another evaluation in that renderer.
                        if pressed is None and hovered is None and not context.errors:
                            context.page.evaluate("""() => {
                            window.__refractBrowser.armed = null;
                            window.__refractBrowser.event = null;
                            window.__refractBrowser.origin = null;
                            }""")
                    finally:
                        if pinned is not None:
                            pinned.close()
            if permit.action == "open":
                self._settle(context, permit.action_id)
            if context.native is not None:
                context.native.collect(permit.action_id)
            self._check(context)
            rendered = self.snapshot(context)
            # Snapshot and header reads pump browser events. Freeze a finite
            # receipt boundary after the snapshot, then complete only its mock
            # blocks; later arrivals remain queued for the next action.
            traffic_end = len(context.traffic)
            diagnostic_end = len(context.diagnostics)
            mock_end = len(context.mock_recordings)
            mock_recordings = list(context.mock_recordings[mock_start:mock_end])
            if context.native is None:
                self._collect_mock_headers(context, mock_recordings)
            self._check(context)
            self._remaining(context)
            if pressed is not None:
                failure_phase = Reason.EVIDENCE_INVALID
                # Snapshot/header reads can dispatch focus and navigation work.
                # Keep the guard armed until this final observed receipt boundary.
                key_press = pressed.receipt()
                pressed.close()
                pressed = None
                context.key_boundary.check()
                self._remaining(context)
            if hovered is not None:
                failure_phase = Reason.EVIDENCE_INVALID
                hover = hovered.receipt()
                hovered.close()
                hovered = None
                context.key_boundary.check()
                self._remaining(context)
            current, diagnostics = [], list(context.diagnostics[diagnostic_start:diagnostic_end])
            for traffic in context.traffic[start:traffic_end]:
                if traffic.action_id == permit.action_id:
                    current.append(traffic)
                else:
                    diagnostics.append(traffic.response)
            if (permit.action == "hover" or permit.action == "press" and permit.key == "Escape") and current:
                raise ActionFailure(Reason.EVIDENCE_INVALID)
            result = ports.UiActionResult(evidence=ports.UiActionEvidence(
                execution_id=permit.execution_id, action_id=permit.action_id,
                step_id=permit.step_id, mode=permit.mode, permit_token=permit.token,
                user=permit.user, session_generation=permit.session_generation, context_id=permit.context_id,
                traffic=current, rendered=rendered,
                diagnostic_outgoing=[recording.request for recording in diagnostics],
                diagnostic_recorded=diagnostics,
                mock_recordings=mock_recordings,
                diagnostic_notes=list(context.native.notes) if context.native is not None else list(context.diagnostic_notes),
                object_selection=selection,
                key_press=key_press, hover=hover,
            ))
            if context.navigation is not None:
                context.navigation.end()
            context.traffic_cursor = traffic_end
            context.diagnostic_cursor = diagnostic_end
            context.mock_cursor = mock_end
            return result
        except Exception as error:
            self._fail(context, self._reason(context, error, failure_phase),
                       cleanup_failed=(safe_action_failure(error) or (None, False))[1])
        finally:
            if hovered is not None:
                try:
                    hovered.close()
                except Exception:
                    pass
            if pressed is not None:
                try:
                    pressed.close()
                except Exception:
                    pass
            if context.navigation is not None:
                context.navigation.opening = False
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
                raise ActionFailure(Reason.POLICY_DENIED)
            if context.page is not None and request.frame != context.page.main_frame:
                raise ActionFailure(Reason.POLICY_DENIED)
            api = request.resource_type in {"fetch", "xhr"}
            if not api and (request.resource_type not in {
                    "document", "stylesheet", "script", "image", "font", "media", "texttrack", "manifest",
            } or request.method not in {"GET", "HEAD"}):
                raise ActionFailure(Reason.POLICY_DENIED)
            request_items = [(item["name"], item["value"]) for item in request.headers_array()]
            require_header_items(request_items)
            headers = dict(request.all_headers())
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
            # The effective transport removes private markers and replaces any
            # application trace. Preserve the complete browser-observed block,
            # including credentials. route.fetch can add transport-owned headers;
            # this observation is not a packet capture of that forwarding hop.
            request_items = [(name, value) for name, value in request_items
                             if not name.lower().startswith("x-refract-")
                             and name.lower() != "traceparent"]
            if traceparent is not None:
                request_items.append(("traceparent", traceparent))
            trace_id = traceparent.split("-")[1] if traceparent and len(traceparent.split("-")) == 4 else None
            actual_url = urlsplit(request.url)
            actual_path = actual_url.path
            fixture_id = None
            if api:
                # Parse before forwarding or choosing a fixture. Duplicate or
                # invalid API query values cannot be represented as evidence.
                actual_query = parse_query(actual_url.query)
                logical_path = self._logical_path(actual_path)
                if type(logical_path) is not str or not logical_path:
                    raise ValueError("browser logical path mapping failed")
                body = None
                if is_form_content_type(request_items):
                    body = parse_form_body(request.post_data_buffer)
                elif request.post_data is not None:
                    body = json.loads(request.post_data)
                    if body is not None and type(body) is not dict:
                        raise ValueError("browser request body must be a JSON object")
                spec = ports.RequestSpec(request.method, logical_path, body, traceparent,
                                         query=actual_query)
            if api and context.mode == "mock":
                if permit is None and context.block_unassociated_mock:
                    context.errors.append(Reason.MOCK_BACKGROUND_BLOCKED)
                    route.abort()
                    return
                if context.mock_queue.index >= len(context.mock_queue.plan):
                    raise ValueError("browser mock plan is exhausted")
                fixture = context.mock_queue.plan[context.mock_queue.index]
                if (fixture.method, fixture.path) != (spec.method, spec.path):
                    raise ValueError("browser traffic does not match the next mock fixture")
                if fixture.query is not None and fixture.query != spec.query:
                    raise ValueError("browser traffic does not match the next mock fixture query")
                if fixture.request_headers is not None and not match_headers(fixture.request_headers, request_items):
                    raise ValueError("browser traffic does not match the next mock fixture headers")
                response_body, status = copy.deepcopy(fixture.response), fixture.status
                text = json.dumps(response_body)
                response_headers = {"content-type": "application/json"}
                response_headers.update(header_map(
                    {} if fixture.response_headers is None else fixture.response_headers))
                context.mock_queue.index += 1
                fixture_id = fixture.fixture_id
                response_items = None
            else:
                response = route.fetch(
                    headers={name: value for name, value in headers.items() if not name.startswith("x-refract-")},
                    max_redirects=0, timeout=self._remaining(context),
                )
                try:
                    status, response_headers = response.status, dict(response.headers)
                    response_items = [(item["name"], item["value"]) for item in response.headers_array]
                    require_header_items(response_items)
                    if 300 <= status < 400 and "location" in response_headers:
                        raise ActionFailure(Reason.POLICY_DENIED)
                    if "text/event-stream" in response_headers.get("content-type", "").lower():
                        raise ActionFailure(Reason.POLICY_DENIED)
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
                    status, response_headers, response_body, text, trace_id, copy.deepcopy(spec),
                    step_id=permit.step_id if permit else None, actual_path=actual_path,
                    request_id=request_id, mock_fixture_id=fixture_id,
                    user=context.user, session_generation=context.session_generation,
                    request_header_items=request_items, header_items=response_items,
                )
                if context.mode == "mock":
                    context.mock_recordings.append(recorded)
                    context.pending_mock_responses[request] = recorded
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
                        user=permit.user, session_generation=permit.session_generation, context_id=permit.context_id,
                    ))
                if context.mode == "mock":
                    route.fulfill(status=status, body=text, headers=response_headers)
        except Exception as error:
            context.errors.append(self._reason(context, error, Reason.EVIDENCE_INVALID))
            try:
                route.abort()
            except Exception:
                context.errors.append(Reason.CLEANUP_FAILED)

    def snapshot(self, context):
        """Read product-owned rendering without executing another primitive."""
        context = self._context(context)
        try:
            self._check(context)
            rendered = self._read_rendered(context.page)
            if type(rendered) is not dict:
                raise ActionFailure(Reason.EVIDENCE_INVALID)
            self._check(context)
            return rendered
        except Exception as error:
            self._fail(context, self._reason(context, error))

    def close(self, context):
        """Release every owned resource, including after a partial open; repeat-safe."""
        if not isinstance(context, _Context) or context.owner is not self:
            raise ValueError("browser context belongs to another helper")
        if context.closed:
            return
        context.closed = True
        execution_key = (context.execution_id, context.context_id)
        if self._executions.get(execution_key) is context:
            # Reserve the execution without retaining the closed browser and
            # its raw evidence through the helper's lifetime.
            self._executions[execution_key] = _CLOSED_EXECUTION
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
            raise ActionFailure(Reason.CLEANUP_FAILED) from None

    def _fail(self, context, reason, *, cleanup_failed=False):
        cleanup_failed = cleanup_failed or any(
            type(item) is Reason and item is Reason.CLEANUP_FAILED
            for item in getattr(context, "errors", ()))
        try:
            self.close(context)
        except Exception:
            cleanup_failed = True
        raise ActionFailure(reason, cleanup_failed=cleanup_failed) from None
