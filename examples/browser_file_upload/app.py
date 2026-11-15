"""Ordinary local pages and multipart API; no Refract imports or declarations.

The API reuses the public fixed-file server's independent MIME parser and
on-disk store. Every read opens the saved file again. Test subclasses can change
served scripts or storage behavior without editing these baseline sources.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit

from examples.file_upload.server import ReceivedUpload, UploadHandler, UploadStore, parse_upload


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Submission:
    path: str
    text: dict = field(repr=False)
    files: dict = field(repr=False)
    raw: bytes = field(repr=False)


@dataclass
class Application:
    store: UploadStore
    base_url: str = ""
    submissions: list = field(default_factory=list, repr=False)
    requests: list = field(default_factory=list)
    closed: bool = False

    def page(self, product):
        return (ROOT / (product + ".html")).read_bytes()

    def script(self, product):
        return (ROOT / (product + ".js")).read_bytes()


def _handler(app):
    class Handler(UploadHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            app.requests.append(("GET", path))
            if path in {"/documents", "/records"}:
                self._respond(200, app.page(path[1:]), "text/html; charset=utf-8")
            elif path in {"/documents.js", "/records.js"}:
                self._respond(200, app.script(path[1:-3]), "application/javascript")
            elif path == "/favicon.ico":
                self._respond(204, b"", "image/x-icon")
            else:
                super().do_GET()

        def do_POST(self):
            path = urlsplit(self.path).path
            app.requests.append(("POST", path))
            if not self._authorized():
                return
            routes = {
                "/v1/documents": ("documents", "attachment", "title"),
                "/vault/records/archive/attachments": ("records", "blob", "caption"),
            }
            if path not in routes:
                self._respond(404, {"error": "route_missing"})
                return
            product, file_field, title_field = routes[path]
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= length <= 12 * 1024 * 1024:
                    raise ValueError("invalid upload size")
                raw = self.rfile.read(length)
                text, files = parse_upload(self.headers.get("Content-Type", ""), raw)
                app.submissions.append(Submission(path, text, files, raw))
                if set(text) != {title_field} or set(files) != {file_field}:
                    raise ValueError("required multipart fields missing")
                filename, data = files[file_field]
            except (ValueError, UnicodeError):
                self._respond(422, {"error": "invalid_upload"})
                return
            app.store.received.append(ReceivedUpload(
                product, file_field, filename, data, text, tuple(self.headers.raw_items())))
            identifier = app.store.save_upload(product, text[title_field], filename, data)
            self._respond(201, {"id": identifier} if product == "documents"
                          else {"attachment": {"key": identifier}})

    return Handler


@contextmanager
def application(*, app_type=Application, store_factory=UploadStore):
    with TemporaryDirectory(prefix="refract-browser-upload-") as directory:
        app = app_type(store_factory(directory))
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(app))
        server.daemon_threads = True
        server.store = app.store
        app.base_url = f"http://127.0.0.1:{server.server_port}"
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        try:
            yield app
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            app.closed = not worker.is_alive()
            if not app.closed:
                raise RuntimeError("upload service failed to close")
