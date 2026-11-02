"""Independent records page; it neither imports Refract nor reads declarations."""
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
    records: list = field(default_factory=lambda: [
        {"id": "r1", "name": "Archived record", "status": "archived"},
        {"id": "r2", "name": "Active record", "status": "active"},
    ])
    received: list = field(default_factory=list)
    page_url: str = ""

    def page(self):
        return ("<!doctype html><html lang=\"en\"><head><title>Record browser</title>"
                '<link rel="stylesheet" href="/menu.css"></head>'
                f'<body data-menu-mode="{self.implementation}"><main>'
                '<h1>Record browser</h1><nav id="menu" aria-label="Record views">'
                '<button id="menu-trigger" type="button">Record views</button>'
                '<div id="menu-items"><button id="archived" type="button">Archived records</button></div>'
                '</nav><ul id="results" aria-label="Query results"></ul>'
                '<output id="request-state">Idle</output></main>'
                '<script src="/menu.js"></script></body></html>').encode()

    def response(self, query):
        items = self.records
        if "status" in query:
            items = [record for record in items if record["status"] == query["status"][0]]
        return 200, {"success": True, "data": {"records": items}}


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            app.received.append({"method": "GET", "path": url.path, "query": url.query})
            if url.path == "/":
                status, data, content_type = 200, app.page(), "text/html"
            elif url.path in {"/menu.js", "/menu.css"}:
                status, data = 200, Path(__file__).with_name(url.path[1:]).read_bytes()
                content_type = "application/javascript" if url.path.endswith(".js") else "text/css"
            elif url.path == "/api/records":
                status, payload = app.response(parse_qs(url.query))
                data, content_type = json.dumps(payload).encode(), "application/json"
            else:
                status, data, content_type = 404, b"not found", "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


@contextmanager
def application(implementation="css"):
    if implementation not in {"css", "javascript"}:
        raise ValueError("unknown menu implementation")
    app = Application(implementation)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(app))
    server.daemon_threads = True
    app.page_url = f"http://127.0.0.1:{server.server_address[1]}"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield app
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
