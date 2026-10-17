"""HTTP ApiDriver for the reference demo application.

This adapter sends requests directly to the demo app's base URL. The demo keeps
transport behavior intentionally simple so the core can be exercised without
product-specific gateway logic.
"""
import httpx

from refracto import ports
from refracto.headers import business_headers
from refracto.query import request_path
from adapters.demo.config import DemoConfig


def real_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


class DemoApiDriver(ports.ApiDriver):
    def __init__(self, config: DemoConfig):
        self._config = config

    def send(self, spec: ports.RequestSpec, session) -> ports.RecordedResponse:
        # Credentials belong only to this lease. Do not retain a client or its
        # authentication defaults across named/anonymous sends. The core owns
        # trace attribution, including over mixed-case credential header names.
        headers = {name: value for name, value in dict(getattr(session, "headers", {})).items()
                   if name.lower() != "traceparent"} if session is not None else {}
        declared = business_headers(spec.headers)
        if set(declared) & {name.lower() for name in headers}:
            raise ValueError("business header collides with session credential header")
        headers.update(declared)
        if spec.traceparent:
            headers["traceparent"] = spec.traceparent
        with httpx.Client(base_url=self._config.base_url, timeout=30.0) as client:
            r = client.request(spec.method, request_path(real_path(spec.path), spec.query),
                               json=spec.body, headers=headers)
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
            request_header_items=[(name.decode("ascii"), value.decode("latin-1"))
                                  for name, value in r.request.headers.raw],
            header_items=[(name.decode("ascii"), value.decode("latin-1"))
                          for name, value in r.headers.raw],
        )
