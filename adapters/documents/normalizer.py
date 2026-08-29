"""Normalize the document target's nested receipts and result sets."""

from refracto import ports


def _document_fields(document: object) -> dict:
    if not isinstance(document, dict):
        return {}
    properties = document.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    sources = (
        ("document_id", document, "identifier"),
        ("title", properties, "title"),
        ("category", properties, "category"))
    return {field: source[key] for field, source, key in sources if key in source}


class DocumentResponseNormalizer(ports.ResponseNormalizer):
    def normalize(self, resp: ports.RecordedResponse) -> ports.NormalizedResponse:
        body = resp.json if isinstance(resp.json, dict) else {}
        if not body:
            succeeded = 200 <= resp.status < 300
            fields = {}
        else:
            receipt = body.get("receipt")
            receipt = receipt if isinstance(receipt, dict) else {}
            succeeded = receipt.get("state") == "accepted" and 200 <= resp.status < 300
            resource = body.get("resource")
            result_set = body.get("result_set")
            fault = body.get("fault")
            if isinstance(resource, dict) and isinstance(resource.get("document"), dict):
                fields = _document_fields(resource["document"])
            elif isinstance(resource, dict) and isinstance(resource.get("normalized"), dict):
                fields = dict(resource["normalized"])
            elif isinstance(result_set, dict):
                nodes = result_set.get("nodes")
                nodes = nodes if isinstance(nodes, list) else []
                page_info = result_set.get("page_info")
                page_info = page_info if isinstance(page_info, dict) else {}
                fields = {
                    "returned": len(nodes),
                    "next_cursor": page_info.get("next_cursor"),
                }
                if nodes:
                    fields.update(_document_fields(nodes[0]))
            elif isinstance(fault, dict):
                fields = {
                    "error_code": fault.get("code"),
                    "error_message": fault.get("message"),
                }
            else:
                fields = {}
        return ports.NormalizedResponse(
            succeeded=succeeded,
            fields=fields,
            status=resp.status,
            raw=resp,
        )

    def synthesize(self, fields, values=None) -> dict:
        values = values or {}
        normalized = {field: values.get(field, f"<stub:{field}>") for field in fields}
        return {
            "receipt": {"state": "accepted", "operation": "synthetic"},
            "resource": {"normalized": normalized},
        }
