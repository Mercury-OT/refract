"""In-process transport port for the clean-room document target."""

import json

from refracto import ports
from refracto.headers import business_headers
from refracto.query import request_path

from examples.documents.app import DocumentRestApp


class DocumentApiDriver(ports.ApiDriver):
    def __init__(self, app: DocumentRestApp):
        self.app = app
        self.sent: list[ports.RequestSpec] = []

    def send(self, spec: ports.RequestSpec, session: object) -> ports.RecordedResponse:
        declared = business_headers(spec.headers)
        if "x-session-key" in declared:
            raise ValueError("business header collides with session credential header")
        session_key = session.get("session_key", "") if isinstance(session, dict) else ""
        headers = {"x-session-key": session_key, **declared}
        # Record the exact invocation block before the target can mutate it.
        request_header_items = list(headers.items())
        self.sent.append(spec)
        response = self.app.handle(
            spec.method,
            request_path(spec.path, spec.query),
            spec.body,
            headers=headers,
        )
        return ports.RecordedResponse(
            status=response.status,
            headers=dict(response.headers),
            json=response.body,
            text="" if response.body is None else json.dumps(response.body),
            trace_id=None,
            request=spec,
            request_header_items=request_header_items,
            header_items=list(response.headers.items()),
        )
