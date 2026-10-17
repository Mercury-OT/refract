"""An offline REST target with server ids, envelopes, filtering, and rejection."""

from dataclasses import dataclass, field
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4


@dataclass(frozen=True)
class RestResponse:
    status: int
    body: dict | None
    headers: dict[str, str] = field(default_factory=dict)


class DocumentRestApp:
    """A neutral document service with no telemetry or adapter-specific hooks."""

    def __init__(self, *, permission_policy: str = "live"):
        if permission_policy not in {"live", "session"}:
            raise ValueError("unknown permission policy")
        self.permission_policy = permission_policy
        self._documents: dict[str, dict] = {}
        self._owners: dict[str, str] = {}
        self._next_id = 1
        self._idempotency: dict[tuple[str, str], tuple[dict, RestResponse]] = {}
        self.requests: list[tuple[str, str, dict | None, dict[str, str]]] = []
        self._accounts = {
            name: {"user_id": f"account-{name}",
                   "role": "administrator" if name == "administrator" else "member",
                   "read_documents": True}
            for name in ("editor", "reader", "user", "operator", "creator", "peer", "member", "administrator")
        }
        self._sessions: dict[str, dict] = {}
        self.authentications: list[tuple[str, str]] = []

    def account_identity(self, user: str) -> str:
        if user not in self._accounts:
            raise ValueError("logical user has no configured account")
        return self._accounts[user]["user_id"]

    def authenticate(self, user: str) -> tuple[str, str]:
        """Issue a new session for a fixed account without changing its grants."""
        principal = self.account_identity(user)
        token = str(uuid4())
        self._sessions[token] = {"user": user, "read_documents": self._accounts[user]["read_documents"]}
        self.authentications.append((principal, token))
        return principal, token

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

        header_values = {name.lower(): value for name, value in headers.items()}
        session = self._sessions.get(header_values.get("x-session-key", ""))
        if session is None:
            return self._rejection(401, "session_required", "a session is required")
        account = self._accounts[session["user"]]
        principal = account["user_id"]

        parsed = urlsplit(path)
        route = parsed.path
        if method == "GET" and route == "/v3/account/profile":
            return self._accepted("account", {name: account[name] for name in ("user_id", "role")})
        if method == "POST" and route == "/v3/documents":
            key = header_values.get("idempotency-key")
            identity = (principal, key) if key is not None else None
            previous = self._idempotency.get(identity) if identity is not None else None
            if previous is not None:
                previous_body, previous_response = previous
                if body != previous_body:
                    return self._rejection(409, "idempotency_conflict", "the key was already used for another request")
                return RestResponse(200, deepcopy(previous_response.body), dict(previous_response.headers))
            response = self._create(body, principal)
            if identity is not None and response.status == 201:
                self._idempotency[identity] = (deepcopy(body), deepcopy(response))
            return response
        if method == "GET" and route == "/v3/documents":
            return self._list(parse_qs(parsed.query), principal)

        parts = route.strip("/").split("/")
        if method == "PATCH" and len(parts) == 4 and parts[:2] == ["v3", "accounts"] and parts[3] == "permissions":
            if account["role"] != "administrator":
                return self._rejection(403, "administrator_required", "this operation requires an administrator")
            target = next((item for item in self._accounts.values() if item["user_id"] == parts[2]), None)
            if target is None:
                return self._rejection(404, "account_missing", "account was not found")
            if not isinstance(body, dict) or set(body) != {"read_documents"} or type(body["read_documents"]) is not bool:
                return self._rejection(400, "permissions_invalid", "read_documents must be a boolean")
            target["read_documents"] = body["read_documents"]
            return self._accepted("permissions", {"user_id": target["user_id"], "read_documents": target["read_documents"]})
        if method in {"GET", "DELETE"} and len(parts) == 3 and parts[:2] == ["v3", "documents"]:
            document_id = parts[2]
            if document_id not in self._documents:
                return self._rejection(404, "document_missing", "document was not found")
            if self._owners[document_id] != principal:
                return self._rejection(403, "owner_required", "document belongs to another account")
            if method == "GET":
                can_read = account["read_documents"] if self.permission_policy == "live" else session["read_documents"]
                if not can_read:
                    return self._rejection(403, "read_permission_required", "document reading is not permitted")
                return self._accepted("document", self._documents[document_id])
            del self._documents[document_id]
            del self._owners[document_id]
            return RestResponse(204, None)

        return self._rejection(404, "route_missing", "route was not found")

    def _create(self, body: dict | None, principal: str) -> RestResponse:
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
        self._owners[document_id] = principal
        return RestResponse(
            201,
            {
                "receipt": {"state": "accepted", "operation": "create"},
                "resource": {"document": document},
            },
            {"content-type": "application/json", "cache-control": "no-store"},
        )

    def _list(self, query: dict[str, list[str]], principal: str) -> RestResponse:
        category = query.get("category", [""])[0]
        title = query.get("title", [""])[0]
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
            if self._owners[document["identifier"]] == principal
            and (not category or document["properties"]["category"] == category)
            and (not title or document["properties"]["title"] == title)
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
    def _accepted(kind: str, value: dict) -> RestResponse:
        return RestResponse(200, {"receipt": {"state": "accepted"}, "resource": {kind: value}},
                            {"content-type": "application/json"})

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
