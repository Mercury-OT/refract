"""Map logical document requests to target routes without inventing values."""

from copy import deepcopy

from refracto import ports
from refracto.query import wire_query


def resolve_request(scenario, step, template) -> ports.RequestSpec:
    method = template.method.upper()
    logical_path = template.path.strip("/")

    if method == "POST" and logical_path == "documents":
        target_path = "/v3/documents"
    elif method == "GET" and logical_path == "documents/search":
        target_path = "/v3/documents"
    elif method in {"GET", "DELETE"} and logical_path.startswith("documents/"):
        document_id = logical_path.removeprefix("documents/")
        if not document_id or "/" in document_id:
            raise ValueError(f"invalid logical document path {template.path!r}")
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
            f"document adapter cannot resolve {template.method} {template.path}"
        )

    return ports.RequestSpec(method=method, path=target_path, body=template.body,
                             query=wire_query(template.query or {}),
                             headers=deepcopy(template.headers or {}))
