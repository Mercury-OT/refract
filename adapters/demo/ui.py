"""Playwright UiDriver for the reference demo application.

The driver keeps the UI surface intentionally small: one page, one form, and a
single list refresh cycle. It supports two modes:

* mock mode: fulfill declared routes from a synthesized mock backend
* live mode: drive the real app once, inject `traceparent`, and record the
  correlated network responses for e2e evaluation
"""
import copy
import dataclasses
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from refracto import ports
from refracto.projection.backend import gen_traceparent

_ITEM_NAME = "demo-item"


@dataclass
class _StepwiseContext:
    playwright: object
    browser: object
    browser_context: object
    page: object
    loaded: bool = False
    active_permit: object = None
    active_object_id: str = ""
    primary_request: object = None
    primary_response: object = None
    diagnostic_outgoing: list = field(default_factory=list)
    diagnostic_recorded: list = field(default_factory=list)
    items: list = field(default_factory=list)


def _testid(page_or_dialog, name: str):
    return page_or_dialog.locator(f'[data-testid="{name}"]')


def _real_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _safe_json(request):
    try:
        return request.post_data_json
    except Exception:
        return None


class DemoUiDriver(ports.UiDriver, ports.StepwiseUiDriver):
    _STEPWISE_ACTIONS = {
        ("demo.item_frontend_stepwise", "create_first"): ("input", "first_name"),
        ("demo.item_frontend_stepwise", "create_bound"): ("bind", "itemId"),
        ("demo.item_e2e_stepwise", "create_first"): ("input", "first_name"),
        ("demo.item_e2e_stepwise", "create_bound"): ("bind", "itemKey"),
    }

    def __init__(self, config):
        self._config = config

    def supports_stepwise_mode(self, mode: str) -> bool:
        return mode in ("mock", "live")

    def run_intent(self, scenario, session, mock) -> ports.UiResult:
        step = scenario.steps[0]
        object_id = next(
            (item.value for item in scenario.inputs if item.kind == "item_id"),
            _ITEM_NAME,
        )
        object_id = str(object_id)
        declared = [(step.request.method, step.request.path)] if step.request is not None else []
        outgoing, recorded, injected = [], [], {}
        pending_responses = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=os.environ.get("SAT_HEADED") != "1")
            context = None
            try:
                context = browser.new_context()
                page = context.new_page()
                self._install_routes(
                    page, declared, mock, outgoing, injected, object_id
                )
                if mock is None:
                    page.on(
                        "response",
                        lambda r: pending_responses.append(r) if id(r.request) in injected else None,
                    )
                self._run_flow(page, object_id)
                rendered = self._read_rendered(page)
                for resp in pending_responses:
                    recorded.append(self._to_recorded(resp, injected))
            finally:
                if context is not None:
                    context.close()
                browser.close()
        return ports.UiResult(rendered=rendered, outgoing=outgoing, recorded=recorded)

    def open_stepwise(self, scenario, session, *, mode):
        if not self.supports_stepwise_mode(mode):
            raise ValueError(f"DemoUiDriver stepwise mode {mode!r} is not supported")
        playwright = sync_playwright().start()
        browser = None
        browser_context = None
        try:
            browser = playwright.chromium.launch(headless=os.environ.get("SAT_HEADED") != "1")
            browser_context = browser.new_context()
            page = browser_context.new_page()
            context = _StepwiseContext(
                playwright=playwright,
                browser=browser,
                browser_context=browser_context,
                page=page,
            )
            page.route(
                f"{self._config.base_url}/items*",
                lambda route: self._handle_stepwise_route(context, route),
            )
            return context
        except Exception:
            if browser_context is not None:
                browser_context.close()
            if browser is not None:
                browser.close()
            playwright.stop()
            raise

    def perform_step(self, scenario, step, context, permit):
        action = self._STEPWISE_ACTIONS.get((scenario.id, step.id))
        if action is None:
            raise ValueError(
                f"no demo UI action registered for scenario={scenario.id!r}, step={step.id!r}")
        source, name = action
        if source == "input":
            object_id = next(
                item.value for item in scenario.inputs if item.kind == name
            )
        else:
            object_id = permit.resolved_bindings[name]

        context.active_permit = permit
        context.active_object_id = str(object_id)
        context.primary_request = None
        context.primary_response = None
        context.diagnostic_outgoing = []
        context.diagnostic_recorded = []
        try:
            if not context.loaded:
                context.page.goto(
                    f"{self._config.base_url}/",
                    wait_until="networkidle",
                    timeout=30000,
                )
                context.loaded = True
            _testid(context.page, "item-name").fill(context.active_object_id)
            _testid(context.page, "create-btn").click()
            context.page.wait_for_function(
                """objectId => Array.from(
                    document.querySelectorAll('[data-testid="item-row"]')
                ).some(row => row.getAttribute('data-object-id') === objectId)""",
                arg=context.active_object_id,
                timeout=30000,
            )
            if context.primary_request is None or context.primary_response is None:
                raise RuntimeError("registered demo action produced no primary request/response")
            evidence = ports.UiActionEvidence(
                execution_id=permit.execution_id,
                action_id=permit.action_id,
                request_id=permit.request_id,
                step_id=permit.step_id,
                attempt_index=permit.attempt_index,
                mode=permit.mode,
                method=permit.method,
                template_path=permit.template_path,
                bound_logical_path=permit.bound_logical_path,
                permit_token=permit.token,
                actual_path=context.primary_response.actual_path,
                is_final=True,
                primary_request=context.primary_request,
                primary_response=context.primary_response,
                rendered=self._read_rendered(context.page),
                diagnostic_outgoing=list(context.diagnostic_outgoing),
                diagnostic_recorded=list(context.diagnostic_recorded),
            )
            return ports.UiActionResult(evidence=evidence)
        finally:
            context.active_permit = None
            context.active_object_id = ""

    def close_stepwise(self, context):
        try:
            context.browser_context.close()
        finally:
            try:
                context.browser.close()
            finally:
                context.playwright.stop()

    def _handle_stepwise_route(self, context, route):
        permit = context.active_permit
        if permit is None:
            raise RuntimeError("demo UI traffic occurred without a core action permit")
        request = route.request
        actual_path = urlparse(request.url).path
        path = actual_path.lstrip("/")
        is_primary = (
            context.primary_request is None
            and request.method == permit.method
            and path == permit.bound_logical_path
        )
        if is_primary:
            spec = ports.RequestSpec(
                method=request.method,
                path=path,
                body=_safe_json(request),
                traceparent=permit.traceparent,
            )
            if permit.mode == "mock":
                body = copy.deepcopy(permit.mock_response)
                status = 200
                headers = {}
                text = json.dumps(body)
                if request.method == "POST":
                    context.items.append({
                        "id": len(context.items) + 1,
                        "name": context.active_object_id,
                        "count": 3,
                    })
                route.fulfill(json=body)
            else:
                live_response = route.fetch(headers={
                    **request.headers,
                    "traceparent": permit.traceparent,
                })
                status = live_response.status
                headers = dict(live_response.headers)
                try:
                    body = live_response.json()
                except Exception:
                    body = None
                try:
                    text = live_response.text()
                except Exception:
                    text = ""
                route.fulfill(response=live_response)
            context.primary_request = spec
            context.primary_response = ports.RecordedResponse(
                status=status,
                headers=headers,
                json=copy.deepcopy(body),
                text=text,
                trace_id=permit.trace_id,
                request=dataclasses.replace(spec),
                step_id=permit.step_id,
                attempt_index=permit.attempt_index,
                is_final=True,
                template_path=permit.template_path,
                bound_logical_path=permit.bound_logical_path,
                actual_path=actual_path,
            )
            return

        spec = ports.RequestSpec(
            method=request.method,
            path=path,
            body=_safe_json(request),
            traceparent=request.headers.get("traceparent"),
        )
        if permit.mode == "mock":
            body = {
                "success": True,
                "error": None,
                "data": {"items": list(context.items)},
            }
            status = 200
            headers = {}
            text = json.dumps(body)
            route.fulfill(json=body)
        else:
            live_response = route.fetch()
            status = live_response.status
            headers = dict(live_response.headers)
            try:
                body = live_response.json()
            except Exception:
                body = None
            try:
                text = live_response.text()
            except Exception:
                text = ""
            route.fulfill(response=live_response)
        diagnostic_response = ports.RecordedResponse(
            status=status,
            headers=headers,
            json=copy.deepcopy(body),
            text=text,
            trace_id=None,
            request=dataclasses.replace(spec),
            actual_path=actual_path,
        )
        context.diagnostic_outgoing.append(spec)
        context.diagnostic_recorded.append(diagnostic_response)

    def _run_flow(self, page, object_id):
        page.goto(f"{self._config.base_url}/", wait_until="networkidle", timeout=30000)
        _testid(page, "item-name").fill(object_id)
        _testid(page, "create-btn").click()
        page.wait_for_function(
            """objectId => Array.from(
                document.querySelectorAll('[data-testid="item-row"]')
            ).some(row => row.getAttribute('data-object-id') === objectId)""",
            arg=object_id,
            timeout=30000,
        )

    def _read_rendered(self, page):
        loc = _testid(page, "item-row")
        try:
            loc.first.wait_for(state="visible", timeout=30000)
        except Exception:
            pass
        identified, anonymous = [], []
        for index in range(loc.count()):
            row = loc.nth(index)
            raw_fields = row.get_attribute("data-object-fields")
            try:
                fields = json.loads(raw_fields) if raw_fields is not None else {}
            except (TypeError, json.JSONDecodeError):
                fields = {}
            if not isinstance(fields, dict):
                fields = {}
            object_id = row.get_attribute("data-object-id")
            rendered_object = {"fields": fields}
            if isinstance(object_id, str) and object_id:
                identified.append({"id": object_id, **rendered_object})
            else:
                anonymous.append(rendered_object)
        return {
            "item_row": {
                "identified": identified,
                "anonymous": anonymous,
            },
        }

    def _install_routes(self, page, declared, mock, outgoing, injected, object_id):
        base = self._config.base_url
        if mock is not None:
            def handle(route):
                req = route.request
                method = req.method
                path = "items"
                key = (method, path)
                if key in mock:
                    outgoing.append(ports.RequestSpec(method=method, path=path, body=_safe_json(req)))
                    route.fulfill(json=mock[key])
                    return
                overlay = self._mock_overlay(method, path, object_id)
                if overlay is not None:
                    route.fulfill(json=overlay)
                    return
                route.fulfill(json={"success": True, "error": None, "data": None})

            page.route(f"{base}/items", handle)
        else:
            def handle(route):
                req = route.request
                method = req.method
                path = "items"
                tp = gen_traceparent()
                injected[id(req)] = tp
                outgoing.append(
                    ports.RequestSpec(method=method, path=path, body=_safe_json(req), traceparent=tp)
                )
                route.continue_(headers={**req.headers, "traceparent": tp})

            for method, path in set(declared):
                page.route(f"{base}{_real_path(path)}", handle)

    def _to_recorded(self, response, injected):
        req = response.request
        tp = injected[id(req)]
        method = req.method
        path = "items"
        try:
            body = response.json()
        except Exception:
            body = None
        try:
            text = response.text()
        except Exception:
            text = ""
        trace_id = tp.split("-")[1]
        spec = ports.RequestSpec(method=method, path=path, body=None, traceparent=tp)
        return ports.RecordedResponse(
            status=response.status,
            headers=dict(response.headers),
            json=body,
            text=text,
            trace_id=trace_id,
            request=spec,
        )

    def _mock_overlay(self, method, path, object_id):
        if method == "GET" and path == "items":
            return {
                "success": True,
                "error": None,
                "data": {"items": [{"id": 1, "name": object_id, "count": 3}]},
            }
        return None
