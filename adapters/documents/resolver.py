"""Map logical document requests to target routes without inventing values."""

from copy import deepcopy

from refracto import ports
from refracto.query import wire_query


def resolve_request(action: ports.RequestAction) -> ports.RequestSpec:
    method = action.method.upper()
    logical_path = action.path.strip("/")

    if method == "POST" and logical_path == "documents":
        target_path = "/v3/documents"
    elif method == "GET" and logical_path == "documents/search":
        target_path = "/v3/documents"
    elif method in {"GET", "PATCH", "DELETE"} and logical_path.startswith("documents/"):
        document_id = logical_path.removeprefix("documents/")
        if not document_id or "/" in document_id:
            raise ValueError(f"invalid logical document path {action.path!r}")
        target_path = f"/v3/documents/{document_id}"
    elif method == "GET" and logical_path == "account/profile":
        target_path = "/v3/account/profile"
    elif method == "PATCH" and logical_path.startswith("accounts/"):
        parts = logical_path.split("/")
        if len(parts) != 3 or not parts[1] or parts[2] != "permissions":
            raise ValueError("invalid logical account permissions path")
        target_path = f"/v3/{logical_path}"
    else:
        raise ValueError(
            f"document adapter cannot resolve {action.method} {action.path}"
        )

    return ports.RequestSpec(method=method, path=target_path, body=action.body,
                             query=wire_query(action.query or {}),
                             headers=deepcopy(action.headers or {}))
