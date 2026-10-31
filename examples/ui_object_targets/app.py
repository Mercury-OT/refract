"""Two ordinary record editors sharing one small HTTP service.

The targets do not import Refract, inspect Scenarios, or receive expected values.
Their detail links and form actions identify the records they actually operate on.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit


@dataclass
class Application:
    implementation: str
    records: dict = field(default_factory=lambda: {
        "r1": {"id": "r1", "code": "first", "name": "First record"},
        "r2": {"id": "r2", "code": "second", "name": "Second record"},
    })
    received: list = field(default_factory=list)
    next_id: int = 3
    base_url: str = ""

    def page(self):
        if self.implementation == "table":
            listing = ('<table id="records"><thead><tr><th>Name</th><th>Code</th>'
                       '<th>Action</th></tr></thead><tbody></tbody></table>')
        else:
            listing = '<section id="records" aria-label="Records"></section>'
        return ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
                "<title>Records</title><h1>Records</h1>" + listing
                + '<form id="editor" hidden><label for="name">Name</label>'
                  '<input id="name" name="name"><button id="save" type="button">Save</button></form>'
                + '<p id="notice" role="status"></p>'
                + f'<script src="/{self.implementation}.js"></script></html>').encode()

    def script(self, name):
        return Path(__file__).with_name(name).read_bytes()

    def response(self, method, path, body, headers):
        if headers.get("Authorization") != "Bearer synthetic-editor-session":
            return 401, {"error": "authentication_required"}
        if path == "/records" and method == "GET":
            return 200, {"records": list(self.records.values())}
        if path == "/records" and method == "POST":
            if (type(body) is not dict or set(body) != {"code", "name"}
                    or any(type(value) is not str or not value for value in body.values())):
                return 400, {"error": "invalid_record"}
            if any(record["code"] == body["code"] for record in self.records.values()):
                return 409, {"error": "duplicate_code"}
            identity = f"r{self.next_id}"
            self.next_id += 1
            record = {"id": identity, **body}
            self.records[identity] = record
            return 201, dict(record)
        identity = path.removeprefix("/records/")
        if not path.startswith("/records/") or identity not in self.records:
            return 404, {"error": "record_missing"}
        if method == "PATCH":
            if type(body) is not dict or set(body) != {"name"} or type(body["name"]) is not str:
                return 400, {"error": "invalid_update"}
            self.records[identity] = {**self.records[identity], "name": body["name"]}
        elif method != "GET":
            return 405, {"error": "method_not_allowed"}
        return 200, dict(self.records[identity])


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def handle_request(self):
            path = urlsplit(self.path).path
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw) if raw else None
            app.received.append({"method": self.command, "path": path, "body": body,
                                 "headers": dict(self.headers)})
            content_type = "application/json"
            if path.startswith("/api/"):
                status, payload = app.response(self.command, path[4:], body, self.headers)
                data = json.dumps(payload).encode()
            elif path in {"/table.js", "/cards.js"}:
                status, data, content_type = 200, app.script(path[1:]), "application/javascript"
            elif path == "/":
                status, data, content_type = 200, app.page(), "text/html"
            elif path.startswith("/records/") and path[9:] in app.records:
                record = app.records[path[9:]]
                data = ('<!doctype html><title>Record</title><h1>' + escape(record["name"])
                        + '</h1><a href="/">Back to records</a>').encode()
                status, content_type = 200, "text/html"
            else:
                status, data = 404, b"{}"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_POST = do_PATCH = handle_request

    return Handler


@contextmanager
def application(implementation="table", *, app_type=Application):
    if implementation not in {"table", "cards"}:
        raise ValueError("unknown editor implementation")
    app = app_type(implementation)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(app))
    server.daemon_threads = True
    app.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
