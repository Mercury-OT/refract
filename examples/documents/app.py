"""An offline REST target with server ids, envelopes, filtering, and rejection."""

from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit


@dataclass(frozen=True)
class RestResponse:
    status: int
    body: dict | None
    headers: dict[str, str] = field(default_factory=dict)


class DocumentRestApp:
    """A neutral document service with no telemetry or adapter-specific hooks."""

    def __init__(self):
        self._documents: dict[str, dict] = {}
        self._next_id = 1
        self.requests: list[tuple[str, str, dict | None, dict[str, str]]] = []

    @property
    def request_count(self) -> int:
        return len(self.requests)

    def handle(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> RestResponse:
        method = method.upper()
        path = path if path.startswith("/") else f"/{path}"
        headers = dict(headers or {})
        self.requests.append((method, path, body, headers))

        if not headers.get("x-session-key", "").startswith("role:"):
            return self._rejection(401, "session_required", "a session is required")

        parsed = urlsplit(path)
        route = parsed.path
        if method == "POST" and route == "/v3/documents":
            return self._create(body)
        if method == "GET" and route == "/v3/documents":
            return self._list(parse_qs(parsed.query))

        parts = route.strip("/").split("/")
        if method == "DELETE" and len(parts) == 3 and parts[:2] == ["v3", "documents"]:
            document_id = parts[2]
            if document_id not in self._documents:
                return self._rejection(404, "document_missing", "document was not found")
            del self._documents[document_id]
            return RestResponse(204, None)

        return self._rejection(404, "route_missing", "route was not found")

    def _create(self, body: dict | None) -> RestResponse:
        title = body.get("title") if isinstance(body, dict) else None
        category = body.get("category") if isinstance(body, dict) else None
        if not isinstance(title, str) or not title:
            return self._rejection(400, "title_required", "title is required")
        if not isinstance(category, str) or not category:
            return self._rejection(400, "category_required", "category is required")
        if category == "restricted":
            return self._rejection(
                422,
                "category_not_allowed",
                "the requested category is not accepted",
            )

        document_id = f"document-{self._next_id}"
        self._next_id += 1
        document = {
            "identifier": document_id,
            "properties": {"title": title, "category": category},
        }
        self._documents[document_id] = document
        return RestResponse(
            201,
            {
                "receipt": {"state": "accepted", "operation": "create"},
                "resource": {"document": document},
            },
            {"content-type": "application/json"},
        )

    def _list(self, query: dict[str, list[str]]) -> RestResponse:
        category = query.get("category", [""])[0]
        try:
            cursor = int(query.get("cursor", ["0"])[0])
            limit = int(query.get("limit", ["10"])[0])
        except ValueError:
            return self._rejection(400, "page_invalid", "pagination must be numeric")
        if cursor < 0 or limit < 1:
            return self._rejection(400, "page_invalid", "pagination is outside its range")

        matching = [
            document
            for document in self._documents.values()
            if not category or document["properties"]["category"] == category
        ]
        page = matching[cursor:cursor + limit]
        next_cursor = cursor + limit if cursor + limit < len(matching) else None
        return RestResponse(
            200,
            {
                "receipt": {"state": "accepted", "operation": "list"},
                "result_set": {
                    "nodes": page,
                    "page_info": {
                        "cursor": cursor,
                        "limit": limit,
                        "next_cursor": next_cursor,
                    },
                },
            },
            {"content-type": "application/json"},
        )

    @staticmethod
    def _rejection(status: int, code: str, message: str) -> RestResponse:
        return RestResponse(
            status,
            {
                "receipt": {"state": "rejected"},
                "fault": {"code": code, "message": message},
            },
            {"content-type": "application/json"},
        )
