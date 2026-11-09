"""A neutral target accepting deletion before a separate worker commits it."""

from contextlib import closing
import sqlite3
from threading import Event, Thread

from examples.sqlite_records.app import RecordsApp, Response


class AsyncRecordsApp(RecordsApp):
    """The worker knows storage operations, never probes or assertions."""

    def __init__(self, database):
        super().__init__(database)
        self._cancel = Event()
        self._workers = []
        self.worker_errors = []

    def _before_delete(self):
        # A short target-side queue delay, independent of the reader interval.
        return not self._cancel.wait(0.05)

    def _commit_delete(self, connection, record_id):
        connection.execute("DELETE FROM entries WHERE record_id = ?", (record_id,))
        connection.commit()

    def _delete_record(self, record_id):
        def worker():
            try:
                if self._before_delete():
                    with closing(sqlite3.connect(self.database, timeout=1)) as connection:
                        self._commit_delete(connection, record_id)
            except Exception as exc:
                self.worker_errors.append(type(exc).__name__)

        thread = Thread(target=worker, name="record-delete", daemon=True)
        self._workers.append(thread)
        thread.start()

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        return Response(202, None) if method == "DELETE" and response.status == 204 else response

    def close(self):
        self._cancel.set()
        try:
            for thread in self._workers:
                thread.join(timeout=3)
            if any(thread.is_alive() for thread in self._workers):
                raise RuntimeError("record deletion worker did not stop")
            if self.worker_errors:
                raise RuntimeError("record deletion worker failed")
        finally:
            super().close()
