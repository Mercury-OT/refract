"""Product-owned Demo mappings and rendering over reusable browser support."""

import json

from refracto import ports
from refracto_browser import BrowserSupport


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
        self._browser = BrowserSupport(config.base_url, self._read_rendered)

    def supports_stepwise_mode(self, mode):
        return mode in {"mock", "live"}

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None,
                      mock_queue=None, user=None, session_generation=0, context_id=""):
        return self._browser.open(mode, mock_plan=mock_plan, mock_queue=mock_queue,
                                  user=user, session_generation=session_generation,
                                  context_id=context_id,
                                  context_options=getattr(session, "context", None))

    def perform_step(self, scenario, step, context, permit):
        if permit.action == "open":
            if permit.target not in {"items.page", "records.page"}:
                raise ValueError("unknown page target")
            return self._browser.perform(context, permit, url=self._config.base_url + "/")
        selector = self._TARGETS.get(permit.target)
        if selector is None:
            raise ValueError("unknown element target")
        return self._browser.perform(context, permit, selector=selector)

    @staticmethod
    def _read_rendered(page):
        identified, anonymous = [], []
        rows = page.locator('[data-testid="item-row"]')
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

    def snapshot(self, context):
        return self._browser.snapshot(context)

    def close_stepwise(self, context):
        self._browser.close(context)
