"""StateProbe for the reference demo application.

The demo app exposes an in-memory trace endpoint at
`GET /debug/traces/{trace_id}`. This adapter converts that payload into the
core's neutral `StateFacts` structure.
"""
import httpx

from refracto import ports
from adapters.demo.config import DemoConfig


class DemoStateProbe(ports.StateProbe):
    def __init__(self, config: DemoConfig):
        self._config = config

    def observe(self, trace_id: str) -> ports.StateFacts:
        r = httpx.get(f"{self._config.base_url}/debug/traces/{trace_id}", timeout=30.0)
        r.raise_for_status()
        payload = r.json()
        spans = [
            ports.Span(name=s["name"], attributes=s["attributes"])
            for s in payload.get("spans") or []
        ]
        return ports.StateFacts(trace_id=trace_id, spans=spans)
