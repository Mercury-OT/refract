"""The minimum Refract adapter surface for the clean-room REST target."""

import json
from uuid import uuid4

from refracto import ports, runner
from refracto.recorder import InMemoryRecorder

from examples.minimal.app import MinimalRestApp


class MinimalAuthenticator(ports.Authenticator):
    def identify(self, user: str) -> str:
        return f"minimal-account:{user}"

    def session(self, user: str) -> ports.UserSession:
        return ports.UserSession(
            principal_id=self.identify(user), authentication_id=str(uuid4()),
            credentials={"user": user},
        )


class MinimalApiDriver(ports.ApiDriver):
    def __init__(self, app: MinimalRestApp):
        self.app = app
        self.sent: list[ports.RequestSpec] = []

    def send(self, spec: ports.RequestSpec, session: object) -> ports.RecordedResponse:
        self.sent.append(spec)
        response = self.app.handle(spec.method, spec.path, spec.body)
        return ports.RecordedResponse(
            status=response.status,
            headers=dict(response.headers),
            json=response.body,
            text="" if response.body is None else json.dumps(response.body),
            trace_id=None,
            request=spec,
        )


class MinimalResponseNormalizer(ports.ResponseNormalizer):
    def normalize(self, resp: ports.RecordedResponse) -> ports.NormalizedResponse:
        fields = dict(resp.json) if isinstance(resp.json, dict) else {}
        return ports.NormalizedResponse(
            succeeded=200 <= resp.status < 300,
            fields=fields,
            status=resp.status,
            raw=resp,
        )

def resolve_request(action: ports.RequestAction) -> ports.RequestSpec:
    logical_path = action.path.strip("/")
    if logical_path == "records":
        target_path = "/items"
    elif logical_path.startswith("records/"):
        target_path = f"/items/{logical_path.removeprefix('records/')}"
    else:
        raise ValueError(f"minimal adapter cannot resolve {action.method} {action.path}")
    return ports.RequestSpec(
        method=action.method,
        path=target_path,
        body=action.body,
    )


def build_adapters(app: MinimalRestApp | None = None) -> runner.Adapters:
    app = app or MinimalRestApp()
    return runner.Adapters(
        auth=MinimalAuthenticator(),
        api=MinimalApiDriver(app),
        state=None,
        ui=None,
        recorder_factory=InMemoryRecorder,
        resolve_request=resolve_request,
        normalizer=MinimalResponseNormalizer(),
    )
