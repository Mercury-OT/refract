"""A records application served by three independent local HTTP listeners.

The application owns request values, authentication headers and CORS policy.
It never reads Scenario files or receives expected assertions.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit


@dataclass
class Application:
    implementation: str
    maintenance: bool = False
    records: dict = field(default_factory=lambda: {
        "r1": {"id": "r1", "code": "first", "name": "First", "category": "guide"},
        "r2": {"id": "r2", "code": "second", "name": "Second", "category": "note"},
        "r3": {"id": "r3", "code": "third", "name": "Third", "category": "guide"},
    })
    received: list = field(default_factory=list)
    page_url: str = ""
    api_url: str = ""
    static_url: str = ""
    next_id: int = 4

    @property
    def api_prefix(self):
        return "/service" if self.maintenance else "/api"

    @property
    def selector_prefix(self):
        return "v2-" if self.maintenance else ""

    def page(self):
        prefix = self.selector_prefix
        inputs = "".join(f'<input id="{prefix}{name}" value="{value}">'
                         for name, value in (("name", "Example record"), ("code", "new"),
                                             ("record_id", "r1"), ("category", "guide"),
                                             ("page", "1")))
        buttons = "".join(f'<button id="{prefix}{name}">{name}</button>' for name in (
            "list", "filter", "next", "create", "read", "update", "delete",
            "protected_write", "protected_read"))
        configuration = json.dumps({"api": self.api_url + self.api_prefix,
                                    "selectorPrefix": prefix})
        return ("<!doctype html><html lang=\"en\"><title>Records</title>"
                '<main data-object-id="page"><output id="asset-ready">loading</output>'
                + inputs + buttons + '<pre id="result"></pre></main>'
                + f"<script>window.recordConfig={configuration};</script>"
                + f'<script src="{self.static_url}/{self.implementation}.js"></script></html>').encode()

    def response(self, method, path, query, body, headers):
        if path.startswith("/protected"):
            if headers.get("Authorization") != "Bearer creator":
                return 401, {"success": False, "data": {"reason": "authentication_required"}}
            if method == "GET":
                return 200, {"success": True, "data": {"access": "creator"}}
            return 201, {"success": True, "data": {"accepted": True}}
        if path == "/records" and method == "GET":
            items = list(self.records.values())
            if "category" in query:
                items = [item for item in items if item["category"] == query["category"][0]]
            if "page" in query:
                page, limit = int(query["page"][0]), int(query.get("limit", ["1"])[0])
                items = items[(page - 1) * limit:page * limit]
            return 200, {"success": True, "data": {"records": items}}
        if path == "/records" and method == "POST":
            if any(item["code"] == body["code"] for item in self.records.values()):
                return 409, {"success": False, "data": {"reason": "duplicate_code"}}
            identity = f"r{self.next_id}"
            self.next_id += 1
            item = {"id": identity, "code": body["code"], "name": body["name"], "category": "guide"}
            self.records[identity] = item
            return 201, {"success": True, "data": item}
        identity = path.removeprefix("/records/")
        if path.startswith("/records/") and identity in self.records:
            if method == "PATCH":
                self.records[identity] = {**self.records[identity], "name": body["name"]}
            if method == "DELETE":
                del self.records[identity]
                return 200, {"success": True, "data": {"deleted": identity}}
            return 200, {"success": True, "data": self.records[identity]}
        return 404, {"success": False, "data": {"reason": "not_found"}}


def _handler(app, channel):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def handle_request(self):
            url = urlsplit(self.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw) if raw else None
            app.received.append({"channel": channel, "method": self.command,
                                 "path": url.path, "query": url.query,
                                 "headers": dict(self.headers), "body": body})
            content_type = "application/json"
            if channel == "api":
                if self.command == "OPTIONS":
                    status, value = 204, None
                elif not url.path.startswith(app.api_prefix + "/"):
                    status, value = 404, {"success": False, "data": {"reason": "wrong_prefix"}}
                else:
                    status, value = app.response(self.command, url.path[len(app.api_prefix):],
                                                 parse_qs(url.query), body, self.headers)
                data = json.dumps(value).encode() if value is not None else b""
            elif channel == "static":
                name = url.path.removeprefix("/")
                if name not in {"promise.js", "async.js"}:
                    status, data = 404, b"not found"
                else:
                    status, data = 200, Path(__file__).with_name(name).read_bytes()
                content_type = "application/javascript"
            elif url.path == "/favicon.ico":
                status, data = 204, b""
            else:
                status, data, content_type = 200, app.page(), "text/html"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if channel == "api" and self.headers.get("Origin") == app.page_url:
                self.send_header("Access-Control-Allow-Origin", app.page_url)
                self.send_header("Vary", "Origin")
                if self.command == "OPTIONS":
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_POST = do_PATCH = do_DELETE = do_OPTIONS = handle_request

    return Handler


@contextmanager
def application(implementation="promise", maintenance=False):
    if implementation not in {"promise", "async"}:
        raise ValueError("unknown public frontend implementation")
    app = Application(implementation, maintenance)
    servers, threads = [], []
    try:
        for channel in ("page", "api", "static"):
            server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(app, channel))
            server.daemon_threads = True
            setattr(app, channel + "_url", f"http://127.0.0.1:{server.server_address[1]}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            servers.append(server)
            threads.append(thread)
            thread.start()
        yield app
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
