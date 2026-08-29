"""Map logical document requests to target routes and pagination parameters."""

from urllib.parse import urlencode

from refracto import ports


def _inputs(scenario) -> dict:
    return {item.kind: item.value for item in scenario.inputs}


def resolve_request(scenario, step, template) -> ports.RequestSpec:
    method = template.method.upper()
    logical_path = template.path.strip("/")

    if method == "POST" and logical_path == "documents":
        target_path = "/v3/documents"
    elif method == "GET" and logical_path == "documents/search":
        values = _inputs(scenario)
        query = urlencode(
            {
                "category": values.get("filter_category", ""),
                "cursor": values.get("cursor", 0),
                "limit": values.get("page_size", 10),
            }
        )
        target_path = f"/v3/documents?{query}"
    elif method == "DELETE" and logical_path.startswith("documents/"):
        document_id = logical_path.removeprefix("documents/")
        if not document_id or "/" in document_id:
            raise ValueError(f"invalid logical document path {template.path!r}")
        target_path = f"/v3/documents/{document_id}"
    else:
        raise ValueError(
            f"document adapter cannot resolve {template.method} {template.path}"
        )

    return ports.RequestSpec(method=method, path=target_path, body=template.body)
