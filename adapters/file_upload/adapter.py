"""Two explicit API mappings sharing an ordinary multipart HTTP sender.

The sender only sees owned RequestSpec data. It never opens a source filename
or receives declaration expectations. The local demonstration server is not
imported here; the boundary is actual HTTP.
"""

from copy import deepcopy
from http.client import HTTPConnection
import json
import re
from urllib.parse import urlsplit
from uuid import uuid4

from refracto import ports
from refracto.headers import business_headers
from refracto.query import request_path, wire_query
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters


def _quoted(value):
    if type(value) is not str or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("multipart parameter contains unsupported control characters")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def encode_multipart(body, files):
    """Keep file bytes untouched; UTF-8 encodes only declared text and headers."""
    if body is not None and (type(body) is not dict
                            or any(type(value) is not str for value in body.values())):
        raise ValueError("multipart text fields must be strings")
    boundary = "refract-" + uuid4().hex
    pieces = []
    for name, value in (body or {}).items():
        pieces.append((f'--{boundary}\r\nContent-Disposition: form-data; '
                       f'name="{_quoted(name)}"\r\n\r\n').encode("utf-8"))
        pieces.extend((value.encode("utf-8"), b"\r\n"))
    for name, asset in files.items():
        pieces.append((f'--{boundary}\r\nContent-Disposition: form-data; '
                       f'name="{_quoted(name)}"; filename="{_quoted(asset.filename)}"\r\n'
                       'Content-Type: application/octet-stream\r\n\r\n').encode("utf-8"))
        pieces.extend((asset.data, b"\r\n"))
    pieces.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(pieces), f"multipart/form-data; boundary={boundary}"


class UploadApiDriver(ports.ApiDriver):
    def __init__(self, base_url):
        address = urlsplit(base_url)
        if (address.scheme != "http" or not address.hostname or address.path not in ("", "/")
                or address.query or address.fragment or address.username or address.password):
            raise ValueError("upload example requires an HTTP origin")
        self.host, self.port = address.hostname, address.port
        self.authority = address.netloc

    def supports_file_upload(self):
        return True

    def _encode_upload(self, request):
        return encode_multipart(request.body, request.files)

    def send(self, request, session):
        headers = business_headers(request.headers)
        if "x-upload-session" in headers:
            raise ValueError("business header collides with session credential header")
        headers["x-upload-session"] = session["token"]
        if request.traceparent:
            headers["traceparent"] = request.traceparent
        payload = None
        if request.files:
            payload, headers["content-type"] = self._encode_upload(request)
        elif request.body is not None:
            payload = json.dumps(request.body).encode("utf-8")
            headers["content-type"] = "application/json"
        # Supply the headers http.client otherwise inserts so this recording
        # captures every transmitted request field, including transport fields.
        headers["host"] = self.authority
        headers["accept-encoding"] = "identity"
        if payload is not None or request.method in {"POST", "PUT", "PATCH"}:
            headers["content-length"] = str(len(payload) if payload is not None else 0)
        connection = HTTPConnection(self.host, self.port, timeout=5)
        try:
            connection.request(request.method, request_path(request.path, request.query),
                               body=payload, headers=headers)
            response = connection.getresponse()
            data, status = response.read(), response.status
            response_headers = response.getheaders()
        finally:
            connection.close()
        text = data.decode("utf-8")
        observed = json.loads(text) if text else None
        trace_id = request.traceparent.split("-")[1] if request.traceparent else None
        return ports.RecordedResponse(status, dict(response_headers), observed, text, trace_id, request,
            request_header_items=list(headers.items()), header_items=response_headers)


class ExampleAuthenticator(ports.Authenticator):
    def identify(self, user):
        if user != "editor":
            raise ValueError("unknown example user")
        return "upload-editor"

    def session(self, user):
        return ports.UserSession(principal_id=self.identify(user),
            authentication_id="local-upload-session", credentials={"token": "example-editor"})


def _spec(action, path):
    return ports.RequestSpec(action.method, path, deepcopy(action.body),
        query=wire_query(action.query or {}), headers=deepcopy(action.headers or {}),
        files=deepcopy(action.files))


def resolve_documents(action):
    path = action.path.strip("/")
    if ((action.method == "POST" and path == "documents")
            or (action.method == "GET" and re.fullmatch(r"documents/[^/]+", path))):
        return _spec(action, "/v1/" + path)
    raise ValueError("unsupported document upload request")


def resolve_records(action):
    path = action.path.strip("/")
    if ((action.method == "POST" and path == "records/archive/attachments")
            or (action.method == "GET"
                and re.fullmatch(r"records/archive/attachments/[^/]+", path))):
        return _spec(action, "/vault/" + path)
    raise ValueError("unsupported record attachment request")


class UploadNormalizer(ports.ResponseNormalizer):
    def __init__(self, product):
        self.product = product

    def normalize(self, response):
        payload = response.json if type(response.json) is dict else {}
        if self.product == "records" and "attachment" in payload:
            attachment = payload["attachment"]
            fields = {"id": attachment["key"]}
            for source, target in (("original_name", "filename"), ("byte_count", "size"),
                                   ("digest", "sha256"), ("text", "content"), ("caption", "title")):
                if source in attachment:
                    fields[target] = attachment[source]
        else:
            fields = deepcopy(payload)
        return ports.NormalizedResponse(200 <= response.status < 300, fields, response.status, response)


def build_adapters(base_url, product="documents", *, driver=None):
    if product not in {"documents", "records"}:
        raise ValueError("unknown upload consumer")
    return Adapters(auth=ExampleAuthenticator(), api=driver or UploadApiDriver(base_url),
        state=None, ui=None, recorder_factory=InMemoryRecorder,
        resolve_request=resolve_documents if product == "documents" else resolve_records,
        normalizer=UploadNormalizer(product))
