"""Ordinary server-rendered editors with two full-document navigation styles.

This new synthetic target shares the previous example's JSON records service.
It does not import Refract or receive Scenario expectations. Links and form
routes identify records because the application uses them for navigation/save.
"""
from contextlib import contextmanager
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit

from examples.ui_object_targets.app import Application as RecordsService


class Application(RecordsService):
    def list_page(self):
        rows = []
        for record in self.records.values():
            route = '/records/' + record['id'] + '/edit'
            if self.implementation == 'anchor':
                control = '<a class="edit" href="' + escape(route, quote=True) + '"><span>Edit</span></a>'
            else:
                control = ('<form action="' + escape(route, quote=True) + '">'
                           '<button class="edit" type="button">Edit</button></form>')
            rows.append('<article><h2>' + escape(record['name']) + '</h2>' + control + '</article>')
        script = '' if self.implementation == 'anchor' else '''<script>
document.addEventListener('click', event => {
  const button = event.target.closest('button.edit');
  if (button) location.assign(button.form.action);
});
</script>'''
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Records</title>'
                '<h1>Records</h1><main id="records">' + ''.join(rows) + '</main>' + script + '</html>').encode()

    def editor_page(self, identity):
        record = self.records[identity]
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Edit record</title>'
                '<h1>Edit record</h1><form id="editor" action="/api/records/'
                + escape(record['id'], quote=True) + '"><label for="name">Name</label>'
                '<input id="name" name="name" value="' + escape(record['name'], quote=True) + '">'
                '<button id="save" type="button">Save</button></form>'
                '<p id="notice" role="status"></p><script src="/editor.js"></script></html>').encode()

    def script(self):
        return Path(__file__).with_name('editor.js').read_bytes()


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def handle_request(self):
            path = urlsplit(self.path).path
            raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            body = json.loads(raw) if raw else None
            app.received.append({'method': self.command, 'path': path, 'body': body,
                                 'headers': dict(self.headers)})
            content_type = 'application/json'
            if path.startswith('/api/'):
                status, payload = app.response(self.command, path[4:], body, self.headers)
                data = json.dumps(payload).encode()
            elif path == '/':
                status, data, content_type = 200, app.list_page(), 'text/html'
            elif path == '/editor.js':
                status, data, content_type = 200, app.script(), 'application/javascript'
            elif path.startswith('/records/') and path.endswith('/edit') and path.split('/')[2] in app.records:
                status, data, content_type = 200, app.editor_page(path.split('/')[2]), 'text/html'
            else:
                status, data = 404, b'{}'
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_POST = do_PATCH = handle_request

    return Handler


@contextmanager
def application(implementation='anchor', *, app_type=Application):
    if implementation not in {'anchor', 'location'}:
        raise ValueError('unknown navigation implementation')
    app = app_type(implementation)
    server = ThreadingHTTPServer(('127.0.0.1', 0), _handler(app))
    server.daemon_threads = True
    app.base_url = f'http://127.0.0.1:{server.server_address[1]}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
