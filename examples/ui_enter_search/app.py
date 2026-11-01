"""Ordinary in-place search over two fixed, public sample records.

The two keyboard handlers share this HTTP service and built-in static dataset.
No Scenario, expected value, Refract import, or adapter prepares the application.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit


@dataclass
class Application:
    implementation: str
    records: list = field(default_factory=lambda: [
        {"id": "r1", "name": "Quarterly report"},
        {"id": "r2", "name": "Invoice"},
    ])
    received: list = field(default_factory=list)
    responses: list = field(default_factory=list)
    base_url: str = ""

    def page(self):
        rows = "".join("<li>" + escape(record["name"]) + "</li>" for record in self.records)
        return ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<title>Search records</title><h1>Search records</h1>'
                '<label for="search">Name contains</label><input id="search" type="search">'
                '<p>Press Enter to search.</p><ul id="records" aria-label="Search results">'
                + rows + '</ul><p id="notice" role="status"></p>'
                + f'<script src="/{self.implementation}.js"></script></html>').encode()

    def script(self, name):
        return Path(__file__).with_name(name).read_bytes()

    def response(self, method, path, query, headers):
        if headers.get("Authorization") != "Bearer synthetic-reader-session":
            return 401, {"error": "authentication_required"}
        if path != "/records":
            return 404, {"error": "route_missing"}
        if method != "GET":
            return 405, {"error": "method_not_allowed"}
        if set(query) != {"q"} or len(query["q"]) != 1:
            return 400, {"error": "invalid_search"}
        term = query["q"][0].casefold()
        return 200, {"records": [dict(record) for record in self.records
                                 if term in record["name"].casefold()]}


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def handle_request(self):
            parsed = urlsplit(self.path)
            path = parsed.path
            query = parse_qs(parsed.query, keep_blank_values=True)
            app.received.append({"method": self.command, "path": path, "query": query,
                                 "headers": dict(self.headers)})
            content_type = "application/json"
            if path.startswith("/api/"):
                status, payload = app.response(self.command, path[4:], query, self.headers)
                app.responses.append({"status": status, "payload": payload})
                data = json.dumps(payload).encode()
            elif self.command == "GET" and path == "/":
                status, data, content_type = 200, app.page(), "text/html"
            elif self.command == "GET" and path in {"/listener.js", "/property.js"}:
                status, data, content_type = 200, app.script(path[1:]), "application/javascript"
            elif path == "/favicon.ico":
                status, data = 204, b""
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
def application(implementation="listener", *, app_type=Application):
    if implementation not in {"listener", "property"}:
        raise ValueError("unknown search implementation")
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
