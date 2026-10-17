"""Real HTTP credential isolation; the echo peer makes no permission claim."""
from dataclasses import fields

import pytest
import yaml

from adapters.demo.api import DemoApiDriver
from adapters.demo.auth import Session
from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.resolver import DemoResolver
from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from tests.browser.conftest import http_peer


SECRET = "synthetic-http-account-credential-478"
OLD_TRACE = "00-11111111111111111111111111111111-2222222222222222-01"


class HttpAccounts(ports.Authenticator):
    def __init__(self):
        self.identified, self.acquired = [], []
        self.credentials = Session("owner", headers={"Authorization": "Bearer " + SECRET,
            "Cookie": "account=" + SECRET, "TrAcEpArEnT": OLD_TRACE})

    def identify(self, user):
        assert user == "owner"
        self.identified.append(user)
        return "synthetic-owner-principal"

    def session(self, user):
        assert user == "owner"
        self.acquired.append(user)
        return ports.UserSession(principal_id="synthetic-owner-principal",
            authentication_id="synthetic-owner-login", credentials=self.credentials)


@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
def test_reference_http_named_anonymous_named_has_no_credential_carryover(http_peer, tmp_path, projections):
    raw = {"schema_version": 1, "scenario": "demo.mixed_http", "users": ["owner", "anonymous"],
           "steps": [{"id": sid, "user": user,
                      "do": {"request": {"method": "GET", "path": ["api", "echo"]}},
                      "expect": {"response": [{"check": "status_equals", "value": 200}, {"check": "success"}]}}
                     for sid, user in [("named", "owner"), ("anonymous", "anonymous"), ("named_return", "owner")]]}
    path = tmp_path / "mixed.yaml"
    path.write_text(yaml.safe_dump(raw))
    auth = HttpAccounts()
    original_headers = dict(auth.credentials.headers)
    adapters = Adapters(auth, DemoApiDriver(DemoConfig(http_peer.base_url)), None, None,
        InMemoryRecorder, DemoResolver().resolve_request, DemoResponseNormalizer())
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", [(d.projection, [(s.status, s.detail) for s in d.steps]) for d in report.domains]
    assert auth.identified == auth.acquired == ["owner"]
    assert len(http_peer.api_requests) == 3  # Contract reads only existing records.
    for index, sent in enumerate(http_peer.api_requests):
        headers = {name.lower(): value for name, value in sent["headers"].items()}
        assert len(sent["traceparents"]) == 1 and sent["traceparents"][0] != OLD_TRACE
        if index == 1:
            assert "authorization" not in headers and "cookie" not in headers
        else:
            assert headers["authorization"] == "Bearer " + SECRET
            assert headers["cookie"] == "account=" + SECRET
    assert auth.credentials.headers == original_headers
    assert [(s.user, s.session_generation) for s in report.domains[0].steps] == [("owner", 1), (None, 0), ("owner", 1)]
    assert SECRET not in repr(report) and SECRET not in repr(auth.credentials)


def test_optional_http_credentials_have_independent_hidden_storage():
    first, second = Session("first"), Session("second")
    first.headers["Authorization"] = SECRET
    assert second.headers == {}
    field = next(item for item in fields(Session) if item.name == "headers")
    assert field.kw_only and not field.repr and field.metadata["sensitive"] is True
    assert SECRET not in repr(first)


def test_reference_http_session_cannot_introduce_trace_without_core_authority(http_peer):
    credentials = Session("owner", headers={"traceparent": OLD_TRACE, "Authorization": SECRET})
    DemoApiDriver(DemoConfig(http_peer.base_url)).send(ports.RequestSpec("GET", "api/echo"), credentials)
    assert http_peer.api_requests[0]["traceparents"] == []
    assert http_peer.api_requests[0]["headers"]["Authorization"] == SECRET
    assert credentials.headers["traceparent"] == OLD_TRACE
