"""A small in-process API target; no Scenario or expectation access."""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Response:
    status: int
    body: dict
    headers: dict = field(default_factory=lambda: {"content-type": "application/json"})


class RecordsApp:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.connection = sqlite3.connect(self.database)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS entries ("
            "record_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "business_code TEXT NOT NULL UNIQUE, label TEXT NOT NULL)"
        )
        self.connection.commit()
        self.requests = []
        self._sessions = set()

    def account_identity(self, user):
        if user != "creator":
            raise ValueError("unknown logical user")
        return "record-creator"

    def authenticate(self, user):
        principal = self.account_identity(user)
        token = secrets.token_hex(16)
        self._sessions.add(token)
        return principal, token

    def _commit_write(self):
        self.connection.commit()

    def handle(self, method, path, body=None, headers=None):
        headers = dict(headers or {})
        self.requests.append((method, path, deepcopy(body), deepcopy(headers)))
        credentials = {key.lower(): value for key, value in headers.items()}
        if credentials.get("x-session-key") not in self._sessions:
            return Response(401, {"error": "session_required"})
        parsed = urlsplit(path)
        if parsed.query:
            return Response(400, {"error": "query_not_supported"})
        if method == "POST" and parsed.path == "/records":
            if (type(body) is not dict or set(body) != {"code", "name"}
                    or any(type(body[key]) is not str or not body[key] for key in body)):
                return Response(400, {"error": "record_invalid"})
            try:
                inserted = self.connection.execute(
                    "INSERT INTO entries (business_code, label) VALUES (?, ?)",
                    (body["code"], body["name"]),
                )
                self._commit_write()
            except sqlite3.IntegrityError:
                self.connection.rollback()
                return Response(409, {"error": "code_exists"})
            return Response(201, {"id": inserted.lastrowid, **deepcopy(body)})
        parts = parsed.path.strip("/").split("/")
        if method == "GET" and len(parts) == 2 and parts[0] == "records" and parts[1].isdigit():
            row = self.connection.execute(
                "SELECT record_id, business_code, label FROM entries WHERE record_id = ?",
                (int(parts[1]),),
            ).fetchone()
            if row is not None:
                return Response(200, dict(zip(("id", "code", "name"), row, strict=True)))
        return Response(404, {"error": "record_missing"})

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
