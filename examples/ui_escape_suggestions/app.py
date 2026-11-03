"""Standalone search suggestions; independent of declarations and test adapters."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import urlsplit


@dataclass
class Application:
    implementation: str
    received: list = field(default_factory=list)
    page_url: str = ""

    def page(self):
        return ('<!doctype html><html lang="en"><head><title>Record search</title>'
                '<link rel="stylesheet" href="/search.css"></head>'
                f'<body data-handler="{self.implementation}"><main id="search-region">'
                '<h1>Record search</h1><label for="search">Search records</label>'
                '<input id="search" type="text" aria-controls="suggestions" autocomplete="off">'
                '<ul id="suggestions" aria-label="Search suggestions" hidden></ul>'
                '<button id="help" type="button">Help</button></main>'
                '<script src="/search.js"></script></body></html>').encode()

    def script(self):
        return Path(__file__).with_name("search.js").read_bytes()


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            app.received.append(path)
            if path == "/":
                status, data, mime = 200, app.page(), "text/html"
            elif path == "/search.js":
                status, data, mime = 200, app.script(), "application/javascript"
            elif path == "/search.css":
                status, data, mime = 200, Path(__file__).with_name("search.css").read_bytes(), "text/css"
            else:
                status, data, mime = 404, b"not found", "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


@contextmanager
def application(implementation="listener"):
    if implementation not in {"listener", "property"}:
        raise ValueError("unknown search implementation")
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
