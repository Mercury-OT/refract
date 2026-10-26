"""Actual HTTP peers for browser tests, using only the Python standard library."""
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
from urllib.parse import parse_qsl, urlsplit

import pytest


@dataclass
class HttpPeer:
    requests: list = field(default_factory=list)
    tunnels: list = field(default_factory=list)
    completed: list = field(default_factory=list)
    release: threading.Event = field(default_factory=threading.Event)
    redirect_to: str | None = None
    base_url: str = ""
    response_header_items: dict = field(default_factory=dict)

    @property
    def api_requests(self):
        return [item for item in self.requests if item["path"].startswith("/api/")]


def start_peer():
    peer = HttpPeer()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def do_CONNECT(self):
            # Playwright's HTTP client may tunnel even an ordinary HTTP origin.
            # Serve the synthetic peer on this socket; never connect outward.
            if self.path != "example.com:80":
                self.send_error(502)
                return
            peer.tunnels.append(self.path)
            self.send_response(200, "Connection established")
            self.end_headers()
            self.close_connection = False

        def handle_request(self):
            path = urlsplit(self.path).path
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                body = json.loads(raw) if raw else None
            except (ValueError, UnicodeDecodeError):
                body = raw.decode("utf-8", errors="replace")
            if (path == "/api/form" and self.headers.get_content_type()
                    == "application/x-www-form-urlencoded"):
                body = dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
            peer.requests.append(dict(path=path, url=self.path, method=self.command,
                                      headers=dict(self.headers), body=body, raw_body=raw,
                                      header_items=list(self.headers.raw_items()),
                                      traceparents=self.headers.get_all("traceparent", [])))
            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/static/ready.js":
                data = b"window.staticLoaded = true;"
                content_type = "application/javascript"
            elif not path.startswith("/api/"):
                data = Path(__file__).with_name("app.html").read_bytes()
                content_type = "text/html"
            elif path == "/api/abort":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            elif path == "/api/redirect":
                self.send_response(307)
                self.send_header("Location", peer.redirect_to)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            else:
                data = json.dumps({"success": True, "data": {
                    "path": path, "body": body,
                    "reply": body.get("value", "ok") if isinstance(body, dict) else "ok"
                }}).encode()
                content_type = "application/json"
            self.send_response(201 if path == "/api/xhr" else 200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Synthetic-Reply", "actual-http-peer")
            for name, value in peer.response_header_items.get(path, []):
                self.send_header(name, value)
            self.end_headers()
            try:
                if path in {"/api/delayed", "/api/stale", "/api/hang"}:
                    self.wfile.write(data[:1])
                    self.wfile.flush()
                    peer.release.wait(10 if path == "/api/hang" else 0.25)
                    self.wfile.write(data[1:])
                else:
                    self.wfile.write(data)
                self.wfile.flush()
                peer.completed.append(path)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    peer.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return peer, server, worker


@pytest.fixture
def http_peer():
    peer, server, worker = start_peer()
    yield peer
    peer.release.set()
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


@pytest.fixture
def foreign_peer():
    peer, server, worker = start_peer()
    yield peer
    peer.release.set()
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)
