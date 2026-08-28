"""A tiny in-process REST target with no telemetry or adapter hooks."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AppResponse:
    status: int
    body: dict | None
    headers: dict[str, str] = field(default_factory=dict)


class MinimalRestApp:
    """An ordinary JSON REST target used only by the onboarding example."""

    def __init__(self):
        self._items: dict[str, dict] = {}
        self._next_id = 1
        self.requests: list[tuple[str, str, dict | None]] = []

    @property
    def request_count(self) -> int:
        return len(self.requests)

    def handle(self, method: str, path: str, body: dict | None = None) -> AppResponse:
        method = method.upper()
        path = path if path.startswith("/") else f"/{path}"
        self.requests.append((method, path, body))

        if method == "POST" and path == "/items":
            name = body.get("name") if isinstance(body, dict) else None
            if not isinstance(name, str) or not name:
                return AppResponse(400, {"error": "name is required"})
            item_id = f"item-{self._next_id}"
            self._next_id += 1
            item = {"id": item_id, "name": name}
            self._items[item_id] = item
            return AppResponse(201, dict(item), {"content-type": "application/json"})

        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "items":
            item_id = parts[1]
            if method == "GET":
                item = self._items.get(item_id)
                if item is None:
                    return AppResponse(404, {"error": "item not found"})
                return AppResponse(200, dict(item), {"content-type": "application/json"})
            if method == "DELETE":
                if item_id not in self._items:
                    return AppResponse(404, {"error": "item not found"})
                del self._items[item_id]
                return AppResponse(204, None)

        return AppResponse(404, {"error": "route not found"})
