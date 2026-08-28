"""Playwright UiDriver for the reference demo application.

The driver keeps the UI surface intentionally small: one page, one form, and a
single list refresh cycle. It supports two modes:

* mock mode: fulfill declared routes from a synthesized mock backend
* live mode: drive the real app once, inject `traceparent`, and record the
  correlated network responses for e2e evaluation
"""
import json
import os

from playwright.sync_api import sync_playwright

from refracto import ports
from refracto.projection.backend import gen_traceparent

_ITEM_NAME = "demo-item"


def _testid(page_or_dialog, name: str):
    return page_or_dialog.locator(f'[data-testid="{name}"]')


def _real_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _safe_json(request):
    try:
        return request.post_data_json
    except Exception:
        return None


class DemoUiDriver(ports.UiDriver):
    def __init__(self, config):
        self._config = config

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
