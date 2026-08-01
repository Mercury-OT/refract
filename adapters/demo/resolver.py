"""Request and precondition resolver for the reference demo application.

The resolver turns declaration-level templates into concrete requests for the
example app. It may add product-specific details needed to execute the demo,
while preserving the declared transport identity of each step.
"""
import httpx

from refracto import ports


class DemoResolver:
    def __init__(self, config=None):
        self._config = config
        self._item_id = None

    def resolve_precondition(self, ref, session):
        """Materialize the `item_exists` precondition in the demo application."""
        if getattr(ref, "ref", None) == "item_exists":
            r = httpx.post(
                f"{self._config.base_url}/items",
                json={"name": "demo-item", "rows": [1, 2, 3]},
                timeout=30.0,
            )
            r.raise_for_status()
            self._item_id = r.json()["data"]["itemId"]
        return None

    def resolve_request(self, scenario, step, template) -> ports.RequestSpec:
        method, path = template.method, step.request.path
        if (method, path) == ("POST", "items"):
            row_count = next((i.value for i in scenario.inputs if i.kind == "rows"), 0)
            return ports.RequestSpec(
                method="POST",
                path="items",
                body={"name": "demo-item", "rows": list(range(row_count))},
            )
        if (method, path) == ("PUT", "items"):
            if self._item_id is None:
                raise ValueError(
                    "PUT items requires an 'item_exists' precondition to establish an item id"
                )
            new_name = next((i.value for i in scenario.inputs if i.kind == "new_name"), "renamed")
            return ports.RequestSpec(
                method="PUT",
                path=f"items/{self._item_id}",
                body={"name": new_name},
            )
        if (method, path) == ("DELETE", "items"):
            if self._item_id is None:
                raise ValueError(
                    "DELETE items requires an 'item_exists' precondition to establish an item id"
                )
            return ports.RequestSpec(method="DELETE", path=f"items/{self._item_id}", body=None)
        if (method, path) == ("POST", "jobs"):
            row_count = next((i.value for i in scenario.inputs if i.kind == "rows"), 0)
            return ports.RequestSpec(
                method="POST",
                path=template.path,
                body={"rows": list(range(row_count))},
            )
        if method == "GET" and path.startswith("jobs/"):
            return ports.RequestSpec(method=template.method, path=template.path, body=None)
        if (method, path) == ("POST", "archives"):
            return ports.RequestSpec(method="POST", path=template.path, body=template.body)
        raise ValueError(f"demo resolver cannot build {template.method} {step.request.path}")
