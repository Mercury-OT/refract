"""Local Documents and Records attachment APIs, independent of adapter code.

Multipart is parsed with the standard-library MIME parser. Saved bytes are read
again for every metadata/content request. No client digest is accepted as fact.
This small loopback demonstration is not a production HTTP service.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ReceivedUpload:
    product: str
    field_name: str
    filename: str = field(repr=False)
    data: bytes = field(repr=False)
    text_fields: dict = field(repr=False)
    request_headers: tuple = field(repr=False)


class UploadStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.entries = {}
        self.received = []
        self.request_count = 0

    def save_upload(self, product, title, filename, data):
        identifier = str(len(self.entries) + 1)
        path = self.directory / (identifier + ".bin")
        path.write_bytes(data)
        self.entries[(product, identifier)] = {"path": path, "title": title, "filename": filename}
        return identifier

    def read_upload(self, product, identifier):
        entry = self.entries[(product, identifier)]
        return entry, entry["path"].read_bytes()


def parse_upload(content_type, data):
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + data)
    if message.get_content_type() != "multipart/form-data" or not message.is_multipart() or message.defects:
        raise ValueError("invalid multipart request")
    text, files = {}, {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if (part.defects or part.is_multipart() or part.get_content_disposition() != "form-data"
                or not name or name in text or name in files or part.get("Content-Transfer-Encoding")):
            raise ValueError("invalid multipart field")
        payload = part.get_payload(decode=True)
        filename = part.get_filename()
        if filename is None:
            text[name] = payload.decode("utf-8")
        else:
            files[name] = (filename, payload)
    return text, files


class UploadHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _respond(self, status, payload, content_type="application/json"):
        data = payload if type(payload) is bytes else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        self.server.store.request_count += 1
        if self.headers.get("x-upload-session") != "example-editor":
            self._respond(401, {"error": "unauthenticated"})
            return False
        return True

    def do_POST(self):
        if not self._authorized():
            return
        route = urlsplit(self.path).path
        if route == "/v1/documents":
            product, file_field, title_field = "documents", "attachment", "title"
        elif route == "/vault/records/archive/attachments":
            product, file_field, title_field = "records", "blob", "caption"
        else:
            self._respond(404, {"error": "route_missing"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= 12 * 1024 * 1024:
                raise ValueError("invalid request size")
            text, files = parse_upload(self.headers.get("Content-Type", ""), self.rfile.read(length))
            if set(text) != {title_field} or set(files) != {file_field}:
                raise ValueError("required multipart fields missing")
            filename, data = files[file_field]
        except (ValueError, UnicodeError):
            self._respond(422, {"error": "invalid_upload"})
            return
        self.server.store.received.append(ReceivedUpload(
            product, file_field, filename, data, text, tuple(self.headers.raw_items())))
        identifier = self.server.store.save_upload(product, text[title_field], filename, data)
        self._respond(201, {"id": identifier} if product == "documents"
                      else {"attachment": {"key": identifier}})

    def do_GET(self):
        if not self._authorized():
            return
        route = urlsplit(self.path).path
        document = re.fullmatch(r"/v1/documents/([^/]+)(/content)?", route)
        record = re.fullmatch(r"/vault/records/archive/attachments/([^/]+)(/payload)?", route)
        match = document or record
        if match is None:
            self._respond(404, {"error": "route_missing"})
            return
        product = "documents" if document else "records"
        try:
            entry, data = self.server.store.read_upload(product, match[1])
        except (KeyError, FileNotFoundError):
            self._respond(404, {"error": "attachment_missing"})
            return
        if match[2]:
            self._respond(200, data, "application/octet-stream")
            return
        metadata = {"id": match[1], "filename": entry["filename"], "title": entry["title"],
                    "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        try:
            metadata["content"] = data.decode("utf-8")
        except UnicodeError:
            pass
        if product == "records":
            names = {"id": "key", "filename": "original_name", "title": "caption", "size": "byte_count",
                     "sha256": "digest", "content": "text"}
            metadata = {"attachment": {names[key]: value for key, value in metadata.items()}}
        self._respond(200, metadata)


@contextmanager
def serve_uploads(*, store_factory=UploadStore):
    """Start a loopback HTTP service with run-local, temporary on-disk storage."""
    with TemporaryDirectory(prefix="refract-upload-") as directory:
        store = store_factory(directory)
        server = ThreadingHTTPServer(("127.0.0.1", 0), UploadHandler)
        server.store = store
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", store
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
