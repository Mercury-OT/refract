"""HTTP ApiDriver for the reference demo application.

This adapter sends requests directly to the demo app's base URL. The demo keeps
transport behavior intentionally simple so the core can be exercised without
product-specific gateway logic.
"""
import httpx

from refracto import ports
from adapters.demo.config import DemoConfig


def real_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


class DemoApiDriver(ports.ApiDriver):
    def __init__(self, config: DemoConfig):
        self._config = config

    def send(self, spec: ports.RequestSpec, session) -> ports.RecordedResponse:
        headers = {}
        if spec.traceparent:
            headers["traceparent"] = spec.traceparent
        with httpx.Client(base_url=self._config.base_url, timeout=30.0) as client:
            r = client.request(spec.method, real_path(spec.path), json=spec.body, headers=headers)
        try:
            body = r.json()
        except Exception:
            body = None
        return ports.RecordedResponse(
            status=r.status_code,
            headers=dict(r.headers),
            json=body,
            text=r.text,
            trace_id=None,
            request=spec,
        )
