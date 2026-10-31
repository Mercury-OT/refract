"""Bounded old-document receipts and Chromium document-transition identity.

This is cooperative evidence collection, not a sandbox against page/host code.
"""
import copy
import json

from refracto import ports
from ._object_target import require_browser_id
from ._policy import canonical_origin

_BINDING = '__refractNavigationReceipt'


class NavigationCollector:
    def __init__(self, owner, context):
        self.owner, self.context = owner, context
        self.session = context.browser_context.new_cdp_session(context.page)
        self.contexts, self.current, self.active = {}, None, None
        self.protected, self.opening = False, False
        self.frame = self.session.send('Page.getFrameTree')['frameTree']['frame']
        for name, callback in (
            ('Runtime.executionContextCreated', self._created),
            ('Runtime.executionContextDestroyed', self._destroyed),
            ('Runtime.executionContextsCleared', self._cleared),
            ('Runtime.bindingCalled', self._binding),
            ('Page.frameNavigated', self._committed),
            ('Page.frameRequestedNavigation', self._requested),
            ('Page.frameStartedNavigating', self._started),
            ('Network.requestWillBeSent', self._request),
            ('Network.responseReceived', self._response),
            ('Network.loadingFinished', self._finished),
            ('Network.loadingFailed', self._failed),
        ):
            self.session.on(name, callback)
        self.session.on('Page.frameAttached', lambda _: self._error() if self.active else None)
        context.browser_context.on('page', lambda page: self._error() if self.active and page is not context.page else None)
        self.session.send('Runtime.enable')
        self.session.send('Runtime.addBinding', {'name': _BINDING})
        self.session.send('Page.enable')
        self.session.send('Network.enable')

    def __repr__(self):
        return '<Browser navigation collector>'

    def _error(self):
        self.context.errors.append('browser navigation evidence failed')

    def _created(self, event):
        info = event['context']
        aux = info.get('auxData', {})
        entry = {'id': info['id'], 'unique': info.get('uniqueId'),
                 'frame': aux.get('frameId'), 'default': aux.get('isDefault') is True,
                 'alive': True}
        self.contexts[info['id']] = entry
        if entry['default'] and entry['frame'] == self.frame['id']:
            self.current = copy.deepcopy(entry)

    def _destroyed(self, event):
        entry = self.contexts.get(event['executionContextId'])
        if entry:
            if self.active and entry['unique'] == self.active['source']['unique']:
                self.active['retired'] = True
            entry['alive'] = False
            if self.current and self.current['unique'] == entry['unique']:
                self.current = None

    def _cleared(self, _):
        if self.active:
            self.active["retired"] = True
        self.contexts.clear()
        self.current = None

    def begin(self, permit):
        if self.active is not None or not self.current or not self.current['unique']:
            raise RuntimeError('browser source document is unavailable')
        self.active = {'permit': copy.deepcopy(permit), 'source': copy.deepcopy(self.current),
                       'loader': self.frame['loaderId'], 'origin': canonical_origin(self.context.page.url), 'selection': None, 'navigation': None,
                       'hidden': False, 'retired': False, 'pending': 0, 'requested': [], 'started': [], 'requests': [],
                       'commits': [], 'response': None, 'finished': False}

    def _binding(self, event):
        if event.get('name') != _BINDING:
            return
        try:
            if not self.active or type(event['payload']) is not str:
                raise ValueError()
            state = self.active
            source = self.contexts.get(event['executionContextId'])
            if (not source or not source['alive'] or not source['default']
                    or source['unique'] != state['source']['unique']
                    or source['frame'] != state['source']['frame']):
                raise ValueError()
            payload = json.loads(event['payload'])
            if payload['action'] != state['permit'].action_id:
                raise ValueError()
            kind = payload['kind']
            if kind == 'selection':
                if state['selection'] is not None or state['navigation'] is not None:
                    raise ValueError()
                selection = payload['selection']
                if set(selection) != {'object_id', 'object_matches', 'control_matches'}:
                    raise ValueError()
                require_browser_id(selection['object_id'])
                if any(type(selection[k]) is not int or selection[k] != 1
                       for k in ('object_matches', 'control_matches')):
                    raise ValueError()
                if (type(selection['object_id']) is not type(state['permit'].object_id)
                        or selection['object_id'] != state['permit'].object_id):
                    raise ValueError()
                state['selection'] = copy.deepcopy(selection)
            elif kind == 'state':
                if (state['selection'] is None or payload['errors'] is not False
                        or type(payload['pending']) is not int or payload['pending'] < 0
                        or state['navigation'] is not None and payload['pending'] != 0):
                    raise ValueError()
                state['pending'] = payload['pending']
            elif kind in {'navigate', 'pagehide'}:
                if (state['selection'] is None or payload['errors'] is not False
                        or type(payload['pending']) is not int or payload['pending'] != 0):
                    raise ValueError()
                if kind == 'pagehide':
                    if state['hidden'] or state['navigation'] is None:
                        raise ValueError()
                    state['hidden'] = True
                else:
                    if state['navigation'] is not None or payload['form'] not in {'anchor', 'script'}:
                        raise ValueError()
                    if canonical_origin(payload['url']) != state['origin']:
                        raise ValueError()
                    state['navigation'] = copy.deepcopy(payload)
            else:
                raise ValueError()
        except Exception:
            self._error()

    def _requested(self, event):
        if self.active:
            self.active['requested'].append(copy.deepcopy(event))
            if len(self.active['requested']) > 1:
                self._error()

    def _started(self, event):
        if self.active:
            self.active['started'].append(copy.deepcopy(event))
            if len(self.active['started']) > 1:
                self._error()

    def _request(self, event):
        if event.get('type') == 'Document' and not self.active and self.protected and not self.opening:
            self._error()
        if self.active and event.get('type') == 'Document':
            self.active['requests'].append(copy.deepcopy(event))
            if len(self.active['requests']) > 1 or 'redirectResponse' in event:
                self._error()

    def _committed(self, event):
        frame = event['frame']
        if frame['id'] == self.frame['id']:
            if not self.active and self.protected and not self.opening:
                self._error()
            self.frame = copy.deepcopy(frame)
        if self.active:
            self.active['commits'].append(copy.deepcopy(frame))
            if len(self.active['commits']) > 1:
                self._error()

    def _response(self, event):
        if self.active and event.get('type') == 'Document':
            if self.active['response'] is not None:
                self._error()
            self.active['response'] = copy.deepcopy(event)

    def _finished(self, event):
        if self.active and any(e['requestId'] == event['requestId'] for e in self.active['requests']):
            self.active['finished'] = True

    def _failed(self, event):
        if self.active and any(e['requestId'] == event['requestId'] for e in self.active['requests']):
            self._error()

    def check(self, *, wait=False):
        # Browser reads can dispatch late CDP failures after _check() inspected
        # the host errors. Finalization must recheck the host ledger itself.
        if self.context.errors:
            raise RuntimeError('browser navigation failed')
        state = self.active
        if not state:
            return
        navigation = state['navigation']
        changed = any(state[k] for k in ('requested', 'started', 'requests', 'commits'))
        if not navigation and not changed:
            return
        if not navigation:
            raise RuntimeError('browser navigation origin is unavailable')
        while wait and not (state['finished'] and state['commits'] and state['retired']):
            if self.context.errors:
                raise RuntimeError('browser navigation failed')
            self.context.page.wait_for_timeout(min(10, self.owner._remaining(self.context)))
        if self.context.errors:
            raise RuntimeError('browser navigation failed')
        if any(len(state[k]) != 1 for k in ('requested', 'started', 'requests', 'commits')):
            raise RuntimeError('browser navigation transition is ambiguous')
        requested, started, request, committed = (state[k][0] for k in
                                                  ('requested', 'started', 'requests', 'commits'))
        response = state['response']
        frame, loader, url = state['source']['frame'], request['loaderId'], navigation['url']
        reason = 'anchorClick' if navigation['form'] == 'anchor' else 'scriptInitiated'
        if (requested['frameId'] != frame or requested['disposition'] != 'currentTab'
                or requested['reason'] != reason or requested['url'] != url
                or started['frameId'] != frame or started['loaderId'] != loader
                or started['navigationType'] != 'differentDocument' or started['url'] != url
                or request.get('frameId') != frame or request['request']['method'] != 'GET'
                or request['request']['url'] != url or loader == state['loader']
                or committed['id'] != frame or committed['loaderId'] != loader
                or committed['url'] != url or committed.get('unreachableUrl')
                or not response or response['requestId'] != request['requestId']
                or response['loaderId'] != loader or response['response']['url'] != url
                or not 200 <= response['response']['status'] < 300
                or response['response']['mimeType'].lower() != 'text/html'
                or not state['finished'] or not state['retired'] or state['pending'] != 0
                or not self.current or self.current['unique'] == state['source']['unique']):
            raise RuntimeError('browser navigation transition is incomplete')

    def selection(self):
        self.check(wait=True)
        if not self.active or self.active['selection'] is None:
            raise RuntimeError('browser object click receipt is unavailable')
        return ports.UiObjectSelection(**copy.deepcopy(self.active['selection']))

    def end(self):
        self.check()
        if self.active is not None:
            self.protected = True
        self.active = None
