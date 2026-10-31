"""Action-only mappings for the frozen full-document targets.

Selectors and readers interpret existing routes. They do not receive expectations,
insert identifiers, infer identity from row order, or substitute navigation.
"""
from urllib.parse import urlsplit

from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport, ObjectTarget
from examples.ui_object_targets.adapter import Auth as BaseAuth, Api, Normalizer, RecordsUi, resolve_request


TARGETS = {
    'anchor': ObjectTarget('#records article', 'a.edit', r'''row => {
        const path = row.querySelector('a.edit')?.getAttribute('href');
        const match = path?.match(/^\/records\/([^/]+)\/edit$/);
        if (!match) throw new Error('Missing record route');
        return decodeURIComponent(match[1]);
    }'''),
    'location': ObjectTarget('#records article', 'button.edit', r'''row => {
        const path = row.querySelector('form')?.getAttribute('action');
        const match = path?.match(/^\/records\/([^/]+)\/edit$/);
        if (!match) throw new Error('Missing record route');
        return decodeURIComponent(match[1]);
    }'''),
}


class Auth(BaseAuth):
    def __init__(self, origin):
        super().__init__(origin)
        self.session_calls = 0

    def session(self, user):
        self.session_calls += 1
        return super().session(user)


def read_rendered(page):
    editor = page.locator('#editor')
    if editor.count() != 1 or not editor.is_visible():
        return {'records.editor': {'identified': [], 'anonymous': []}}
    action = editor.get_attribute('action')
    path = urlsplit(action or '').path
    prefix = '/api/records/'
    identity = path[len(prefix):] if path.startswith(prefix) else ''
    fields = {'name': editor.locator('input[name="name"]').input_value()}
    if not identity or '/' in identity:
        return {'records.editor': {'identified': [], 'anonymous': [{'fields': fields}]}}
    return {'records.editor': {'identified': [{'id': identity, 'fields': fields}], 'anonymous': []}}


class NavigationUi(RecordsUi):
    def __init__(self, app, *, timeout_ms=5000):
        self.origin = app.base_url
        self.mapping = TARGETS[app.implementation]
        self.browser = BrowserSupport(app.base_url, read_rendered, timeout_ms=timeout_ms,
            network_policy=BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(app.base_url, '/api', ''),),
                credential_origins=(app.base_url,)))
        self.evidence = []
        self.closed_contexts = 0


def adapters(app, *, timeout_ms=5000):
    return Adapters(Auth(app.base_url), Api(app.base_url), None,
                    NavigationUi(app, timeout_ms=timeout_ms), InMemoryRecorder,
                    resolve_request, Normalizer())
