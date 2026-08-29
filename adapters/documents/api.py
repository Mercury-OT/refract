"""In-process transport port for the clean-room document target."""

import json

from refracto import ports

from examples.documents.app import DocumentRestApp


class DocumentApiDriver(ports.ApiDriver):
    def __init__(self, app: DocumentRestApp):
        self.app = app
        self.sent: list[ports.RequestSpec] = []

    def send(self, spec: ports.RequestSpec, session: object) -> ports.RecordedResponse:
        self.sent.append(spec)
        session_key = session.get("session_key", "") if isinstance(session, dict) else ""
        response = self.app.handle(
            spec.method,
            spec.path,
            spec.body,
            headers={"x-session-key": session_key},
        )
        return ports.RecordedResponse(
            status=response.status,
            headers=dict(response.headers),
            json=response.body,
            text="" if response.body is None else json.dumps(response.body),
            trace_id=None,
            request=spec,
        )
