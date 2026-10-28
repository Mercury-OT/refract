"""Explicit business mappings; no expected values are supplied to the probe."""

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

from refracto import ports
from refracto.headers import business_headers
from refracto.query import request_path, wire_query
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters


class RecordsAuthenticator(ports.Authenticator):
    def __init__(self, app):
        self.app = app

    def identify(self, user):
        return self.app.account_identity(user)

    def session(self, user):
        principal, token = self.app.authenticate(user)
        return ports.UserSession(principal_id=principal, authentication_id=token,
                                 credentials={"session_key": token})


def resolve_request(action):
    path = action.path.strip("/")
    if not ((action.method == "POST" and path == "records")
            or (action.method == "GET" and len(path.split("/")) == 2 and path.startswith("records/"))):
        raise ValueError("unsupported logical record request")
    return ports.RequestSpec(action.method, "/" + path, deepcopy(action.body),
                             query=wire_query(action.query or {}),
                             headers=deepcopy(action.headers or {}))


class RecordsApiDriver(ports.ApiDriver):
    def __init__(self, app):
        self.app = app

    def send(self, request, session):
        headers = business_headers(request.headers)
        if "x-session-key" in headers:
            raise ValueError("business header collides with session credentials")
        token = session.get("session_key", "") if isinstance(session, dict) else ""
        headers = {"x-session-key": token, **headers}
        response = self.app.handle(request.method, request_path(request.path, request.query),
                                   request.body, headers)
        return ports.RecordedResponse(response.status, dict(response.headers),
            deepcopy(response.body), json.dumps(response.body), None, request,
            request_header_items=list(headers.items()), header_items=list(response.headers.items()))


class RecordsNormalizer(ports.ResponseNormalizer):
    def normalize(self, response):
        return ports.NormalizedResponse(200 <= response.status < 300,
            deepcopy(response.json) if type(response.json) is dict else {}, response.status, response)


class SQLiteRecordProbe(ports.ObjectStateProbe):
    """Read one committed object through a separate, read-only connection."""

    def __init__(self, database):
        self._database = Path(database)
        self.queries = []

    def _connect(self):
        connection = sqlite3.connect(self._database.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        connection.execute("PRAGMA query_only = ON")
        return connection

    def observe_object(self, query):
        if (query.object != "record" or type(query.id) is not int
                or not set(query.fields).issubset({"id", "code", "name"})):
            raise ValueError("unsupported record observation")
        self.queries.append(query)
        with closing(self._connect()) as connection:
            # All columns come from the same SELECT snapshot. Neither the
            # object's type nor field names are interpolated into SQL.
            rows = connection.execute(
                "SELECT record_id, business_code, label FROM entries WHERE record_id = ?",
                (query.id,),
            ).fetchall()
        objects = []
        for row in rows:
            fields = dict(zip(("id", "code", "name"), row, strict=True))
            objects.append(ports.ObservedObject(id=fields["id"],
                fields={name: fields[name] for name in query.fields}))
        return ports.ObjectStateFacts(query=query, source="sqlite-records", complete=True, objects=objects)


def build_adapters(app, *, probe=None):
    return Adapters(auth=RecordsAuthenticator(app), api=RecordsApiDriver(app),
        state=None, ui=None, recorder_factory=InMemoryRecorder,
        resolve_request=resolve_request, normalizer=RecordsNormalizer(),
        object_state=probe if probe is not None else SQLiteRecordProbe(app.database))
