"""Approved records example over actual HTTP using the reference transport."""
from copy import deepcopy
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import yaml

from adapters.demo.api import DemoApiDriver
from adapters.demo.auth import DemoAuthenticator, Session
from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.resolver import DemoResolver
from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario


EXAMPLE = Path(__file__).resolve().parents[2] / "examples/minimal/idempotent_create.yaml"
PROJECTIONS = [("backend", "contract"), ("e2e",)]


@dataclass
class RecordsPeer:
    """Fresh, immediate complete lists and no uniqueness constraint on names."""

    base_url: str = ""
    records: list[dict] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    previous: dict = field(default_factory=dict)
    duplicate_on_retry: bool = False
    extra_response_headers: list[tuple[str, str]] = field(default_factory=list)


@pytest.fixture
def records_peer():
    peer = RecordsPeer()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.handle_request()

        def do_GET(self):
            self.handle_request()

        def handle_request(self):
            route = urlsplit(self.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw) if raw else None
            peer.requests.append({"method": self.command, "path": self.path,
                                  "body": deepcopy(body), "headers": list(self.headers.raw_items())})
            if route.path != "/records":
                status, result = 404, {}
            elif self.command == "POST":
                key = self.headers.get("Idempotency-Key")
                previous = peer.previous.get(key) if key is not None else None
                if previous is not None and previous[0] != body:
                    status, result = 409, {}
                elif previous is not None:
                    if peer.duplicate_on_retry:
                        peer.records.append({"id": f"record-{len(peer.records) + 1}", "name": body["name"]})
                    status, result = 200, deepcopy(previous[1])
                else:
                    result = {"id": f"record-{len(peer.records) + 1}", "name": body["name"]}
                    peer.records.append(deepcopy(result))
                    if key is not None:
                        peer.previous[key] = (deepcopy(body), deepcopy(result))
                    status = 201
            else:
                name = parse_qs(route.query).get("name", [None])[0]
                status, result = 200, {"records": [deepcopy(record) for record in peer.records
                                                  if name is None or record["name"] == name]}
            data = json.dumps({"success": status < 400, "data": result}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("cAcHe-CoNtRoL", "no-store")
            for name, value in peer.extra_response_headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    peer.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield peer
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def adapters_for(peer):
    return Adapters(auth=DemoAuthenticator(), api=DemoApiDriver(DemoConfig(peer.base_url)),
                    state=None, ui=None, recorder_factory=InMemoryRecorder,
                    resolve_request=DemoResolver().resolve_request,
                    normalizer=DemoResponseNormalizer())


def write_example(tmp_path, change):
    declaration = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    change(declaration)
    path = tmp_path / "records.yaml"
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_approved_records_retry_example_uses_real_http_and_independent_target_capture(records_peer, projections):
    report = run_scenario(EXAMPLE, adapters_for(records_peer), projections=projections)

    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert [step.step_id for step in report.domains[0].steps] == ["first_submit", "repeat_submit", "read_back"]
    records = report.domains[0].provider_recordings
    assert [record.status for record in records] == [201, 200, 200]
    assert len(records_peer.requests) == 3  # Contract makes no network calls.
    assert records_peer.requests[0]["body"] == records_peer.requests[1]["body"] == {"name": "idempotency-example-record"}
    assert records_peer.requests[-1]["path"] == "/records?name=idempotency-example-record"
    for recorded, actual in zip(records, records_peer.requests, strict=True):
        # An HTTP intermediary may reorder/case-fold names and change its
        # connection policy. Compare the independently observed business data.
        actual_headers = {name.lower(): value for name, value in actual["headers"]}
        sent_headers = {name.lower(): value for name, value in recorded.request_header_items}
        assert sent_headers.keys() == actual_headers.keys()
        for name in ("idempotency-key", "traceparent", "content-type"):
            assert sent_headers.get(name) == actual_headers.get(name)
        assert any(name.lower() == "host" for name, _ in recorded.request_header_items)
    assert [dict((name.lower(), value) for name, value in record.request_header_items).get("idempotency-key")
            for record in records] == ["record-create-example-001", "record-create-example-001", None]
    assert records[0].request.headers == {"Idempotency-Key": "record-create-example-001"}
    assert len(records_peer.records) == 1
    assert records[0].json["data"]["id"] == records[1].json["data"]["id"]


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_records_read_detects_duplicate_creation_despite_reused_response_id(records_peer, projections):
    records_peer.duplicate_on_retry = True
    report = run_scenario(EXAMPLE, adapters_for(records_peer), projections=projections)

    assert report.status == "FAILED", report.localize()
    assert {domain.status for domain in report.domains} == {"FAILED"}
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED", "FAILED"]
    records = report.domains[0].provider_recordings
    assert records[0].json == records[1].json
    assert len(records_peer.records) == 2
    assert len(records_peer.requests) == 3
    checks = [check for check in report.domains[0].checks if check.step == "read_back"]
    assert [check.ok for check in checks if check.check == "collection_matching_count"] == [False, True]


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_real_http_preserves_case_insensitive_names_exact_strings_and_empty_values(records_peer, tmp_path, projections):
    def change(declaration):
        for step in declaration["steps"][:2]:
            step["do"]["request"]["headers"] = {
                "iDeMpOtEnCy-KeY": {"from_parameter": "idempotency_key"},
                "X-Empty": "", "X-Visible": "Exact internal spaces",
            }

    report = run_scenario(write_example(tmp_path, change), adapters_for(records_peer), projections=projections)
    assert report.status == "PASSED", report.localize()
    for request in records_peer.requests[:2]:
        observed = {name.lower(): value for name, value in request["headers"]}
        assert observed["x-empty"] == ""
        assert observed["x-visible"] == "Exact internal spaces"


@pytest.mark.parametrize("name", ["X-Session-Key", "x-SeSsIoN-kEy"])
def test_reference_driver_custom_credential_collision_precedes_network(records_peer, name):
    api = DemoApiDriver(DemoConfig(records_peer.base_url))
    session = Session("creator", headers={"X-SESSION-KEY": "credential-sentinel"})
    with pytest.raises(ValueError, match="credential") as error:
        api.send(ports.RequestSpec("GET", "records", headers={name: "business-sentinel"}), session)
    assert records_peer.requests == []
    assert "credential-sentinel" not in str(error.value)
    assert "business-sentinel" not in str(error.value)


def test_reference_driver_raw_blocks_keep_credentials_duplicates_and_hide_them_in_repr(records_peer):
    secret = "sensitive-synthetic-sentinel"
    records_peer.extra_response_headers = [("Set-Cookie", "first=" + secret), ("set-cookie", "second=" + secret)]
    api = DemoApiDriver(DemoConfig(records_peer.base_url))
    response = api.send(ports.RequestSpec("GET", "records", headers={"X-Note": secret}),
                        Session("creator", headers={"X-Session-Key": secret}))

    captured = {name.lower(): value for name, value in response.request_header_items}
    actual = {name.lower(): value for name, value in records_peer.requests[0]["headers"]}
    assert captured.keys() == actual.keys()
    assert captured["x-session-key"] == actual["x-session-key"] == secret
    assert captured["x-note"] == actual["x-note"] == secret
    assert [value for name, value in response.header_items if name.lower() == "set-cookie"] == [
        "first=" + secret, "second=" + secret]
    assert dict(response.request_header_items)["X-Session-Key"] == secret
    assert secret not in repr(response)
    assert secret not in repr(response.request)


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_changed_actual_http_header_fails_and_later_read_still_runs(records_peer, monkeypatch, projections):
    original_send = httpx.Client.send

    def change_wire_header(client, request, *args, **kwargs):
        if "idempotency-key" in request.headers:
            request.headers["idempotency-key"] = "actual-different-key"
        return original_send(client, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", change_wire_header)
    report = run_scenario(EXAMPLE, adapters_for(records_peer), projections=projections)
    assert report.domains[0].status == "FAILED", report.localize()
    assert [step.status for step in report.domains[0].steps] == ["FAILED", "FAILED", "PASSED"]
    assert len(records_peer.requests) == 3
    assert len(records_peer.records) == 1
    assert all(dict(record.request_header_items)["idempotency-key"] == "actual-different-key"
               for record in report.domains[0].provider_recordings[:2])


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("headers,expected", [
    ([("Set-Cookie", "one"), ("set-cookie", "two")], "PASSED"),
    ([("Cache-Control", "no-store")], "ERROR"),
    ([("X-Internal-Debug", "")], "FAILED"),
])
def test_real_response_raw_duplicates_and_empty_presence(records_peer, projections, headers, expected):
    records_peer.extra_response_headers = headers
    report = run_scenario(EXAMPLE, adapters_for(records_peer), projections=projections)
    assert report.status == ("PASSED" if expected == "PASSED" else "FAILED"), report.localize()
    assert report.domains[0].steps[0].status == expected
    assert len(records_peer.requests) == (1 if expected == "ERROR" else 3)
    if expected == "ERROR":
        assert [step.status for step in report.domains[0].steps[1:]] == ["BLOCKED", "BLOCKED"]
