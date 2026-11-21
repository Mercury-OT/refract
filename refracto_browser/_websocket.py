"""Admission of background-only sockets. No message or HTTP evidence collection."""
import json
import re

from refracto.errors import ActionFailure, ActionFailureReason as Reason


class SocketBoundary:
    def __init__(self, context, base, endpoints):
        self.context = context
        self.base = base
        self.origin = 'ws' + base[4:]
        self.paths = {e.path: e.query_keys for e in endpoints}
        self.attempts = 0
        self.pending = self.active = None

    def permits(self, url):
        if type(url) is not str or len(url) > 2048:
            return False
        address, sep, query = url.partition('?')
        path = address.removeprefix(self.origin)
        if address != self.origin + path or path not in self.paths:
            return False
        if not sep:
            return True
        keys = set()
        for pair in query.split('&'):
            key, eq, value = pair.partition('=')
            if (not eq or key in keys or key not in self.paths[path]
                    or not re.fullmatch(r'[A-Za-z0-9_-]{0,64}', value)):
                return False
            keys.add(key)
        return True

    def denied(self, *_):
        if Reason.POLICY_DENIED not in self.context.errors:
            self.context.errors.append(Reason.POLICY_DENIED)

    async def reject(self, route):
        import asyncio
        from greenlet import greenlet

        self.denied()
        # Unlike HTTP routes, Playwright dispatches socket routes directly on
        # its event-loop fiber. Calling the synchronous close there deadlocks;
        # returning before it finishes can synthesize an open. Give the public
        # close operation its own fiber and await its receipt in this callback.
        closed = asyncio.get_running_loop().create_future()

        def close():
            try:
                route.close(code=1008, reason='policy denied')
            except Exception:
                closed.set_result(False)
            else:
                closed.set_result(True)

        greenlet(close).switch()
        if not await closed:
            if Reason.CLEANUP_FAILED not in self.context.errors:
                self.context.errors.append(Reason.CLEANUP_FAILED)
            raise ActionFailure(Reason.POLICY_DENIED, cleanup_failed=True)

    def install(self):
        ctx = self.context.browser_context
        ctx.expose_binding('__refractSocketDenied', self.denied)
        ctx.route_web_socket('**/*', self.reject)

    def script(self, instrument):
        config = {'origin': self.origin, 'page': self.base, 'paths': self.paths,
                  'live': self.context.mode == 'live'}
        return instrument.replace('const socketPolicy = null;', 'const socketPolicy = ' + json.dumps(config) + ';')

    def watch(self, native):
        page = self.context.page
        if self.context.mode == 'live':
            page.route_web_socket('**/*', self.route)
        session = native.session
        session.on('Network.webSocketCreated', self.created)
        session.on('Network.webSocketClosed', self.closed)

    async def route(self, route):
        ctx = self.context
        # The page route takes precedence over the context-wide deny. The route
        # API doesn't identify a frame, so do not guess when subframes exist.
        if (ctx.closed or ctx.errors or self.attempts >= 4 or self.pending is not None
                or self.active is not None or len(ctx.page.frames) != 1
                or not self.permits(route.url) or getattr(route, 'protocols', None) != []):
            await self.reject(route)
            return
        self.attempts += 1
        self.pending = route.url
        try:
            route.connect_to_server()
        except Exception:
            await self.reject(route)

    def created(self, event):
        if self.pending is None or self.pending != event['url'] or self.active is not None:
            self.denied()
            return
        self.pending = None
        self.active = event['requestId']

    def closed(self, event):
        if event['requestId'] == self.active:
            self.active = None
