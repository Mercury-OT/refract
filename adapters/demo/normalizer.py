"""ResponseNormalizer for the reference demo application.

The demo app uses a small `{success, error, data}` envelope. This adapter maps
that envelope into the core's product-neutral `NormalizedResponse` and can also
synthesize mock bodies in the same shape.
"""
from refracto import ports


class DemoResponseNormalizer(ports.ResponseNormalizer):
    def normalize(self, resp: ports.RecordedResponse) -> ports.NormalizedResponse:
        body = resp.json if isinstance(resp.json, dict) else {}
        if body:
            succeeded = body.get("success") is True
        else:
            succeeded = 200 <= resp.status < 300
        data = body.get("data")
        if isinstance(data, dict):
            fields = dict(data)
        else:
            fields = {k: v for k, v in body.items() if k not in ("success", "error")}
        return ports.NormalizedResponse(
            succeeded=succeeded,
            fields=fields,
            status=resp.status,
            raw=resp,
        )

    def synthesize(self, fields) -> dict:
        return {
            "success": True,
            "error": None,
            "data": {f: f"<stub:{f}>" for f in fields},
        }
