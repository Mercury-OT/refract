"""Native Chromium HTTP observation with out-of-band request identity.

No second HTTP client, wire marker, expectation or URL-based association is used.
"""
import base64
import copy
from dataclasses import asdict
import json
import re
from uuid import uuid4
from urllib.parse import unquote, urlsplit

from refracto import ports
from refracto.headers import header_map, match_headers, require_header_items
from refracto.query import parse_query
from ._request_body import is_form_content_type, parse_form_body
from ._async_origin import ASYNC_DEPTH, invocation_origin

_MARKER = re.compile(r'^__refract_native_([0-9a-f]{32})__(.*)$')
_NOTICE = 'background diagnostics truncated'


class NativeCollector:
    def __init__(self, owner, context, policy, base):
        self.owner, self.context, self.policy, self.base = owner, context, policy, base
        self.session = context.browser_context.new_cdp_session(context.page)
        # Capture native await registration ancestry without pausing product code.
        self.session.send('Debugger.enable')
        self.session.send('Debugger.setBreakpointsActive', {'active': False})
        self.session.send('Debugger.setSkipAllPauses', {'skip': True})
        self.session.send('Debugger.setAsyncCallStackDepth', {'maxDepth': ASYNC_DEPTH})
        self.target_id = self.session.send('Target.getTargetInfo')['targetInfo']['targetId']
        self.target_guard = context.browser.new_browser_cdp_session()
        self.target_guard.on('Target.attachedToTarget', self._target)
        self.target_guard.send('Target.setAutoAttach', {
            'autoAttach': True, 'waitForDebuggerOnStart': True, 'flatten': True,
            'filter': [{'type': 'page', 'exclude': False}, {'exclude': True}],
        })
        self.request_namespace = uuid4().hex
        self.frame = self.session.send('Page.getFrameTree')['frameTree']['frame']['id']
        self.requests, self.waiting = {}, {}
        self.markers = set()
        self.extra_requests, self.extra_responses = {}, {}
        self.background_count = 0
        self.background_bytes = 0
        self.notes = []
        self.mock_pending = []
        self.session.on('Network.requestWillBeSent', self._request)
        self.session.on('Network.responseReceived', self._response)
        self.session.on('Network.requestWillBeSentExtraInfo', self._request_extra)
        self.session.on('Network.responseReceivedExtraInfo', self._response_extra)
        self.session.on('Network.loadingFinished', self._finished)
        self.session.on('Network.dataReceived', self._data)
        self.session.on('Network.loadingFailed', self._failed)
        self.target_guard.on('Fetch.requestPaused', self._paused)
        self.session.send('Network.enable')
        self.target_guard.send('Fetch.enable', {'patterns': [
            {'urlPattern': '*', 'requestStage': 'Request'},
            {'urlPattern': '*', 'requestStage': 'Response'},
        ]})

    def _target(self, event):
        info = event['targetInfo']
        if info['targetId'] != self.target_id:
            self.context.errors.append('browser secondary targets are unsupported')
            self.target_guard.send('Target.closeTarget', {'targetId': info['targetId']})

    def _error(self, request_id=None):
        self.context.errors.append('native browser request policy or evidence failed')
        if request_id is not None:
            try:
                self.target_guard.send('Fetch.failRequest', {'requestId': request_id, 'errorReason': 'BlockedByClient'})
            except Exception:
                pass

    def _request(self, event):
        try:
            identity = event['requestId']
            if identity in self.requests or 'redirectResponse' in event:
                raise ValueError()
            frames = event.get('initiator', {}).get('stack', {}).get('callFrames', [])
            # A direct marker remains authoritative. A marker with no direct
            # origin can use only bounded invocation ancestry, never a matching
            # endpoint, current action or arbitrary asynchronous ancestor.
            marker = (_MARKER.fullmatch(frames[0].get('functionName', ''))
                      if frames and event.get('type') in {'Fetch', 'XHR'} else None)
            action = None
            if marker:
                if marker.group(1) in self.markers:
                    raise ValueError()
                self.markers.add(marker.group(1))
                action = (unquote(marker.group(2)) or invocation_origin(
                    event.get('initiator', {}).get('stack')))
                if action is not None and action not in self.context.permits:
                    raise ValueError()
            self.requests[identity] = {'event': event, 'action': action, 'done': False,
                'claim': marker.group(1) if marker and not marker.group(2) and event.get('type') == 'Fetch' else None}
            if identity in self.extra_requests:
                self._request_extra(self.extra_requests.pop(identity))
            if identity in self.extra_responses:
                self._response_extra(self.extra_responses.pop(identity))
            if identity in self.waiting:
                self._process(self.waiting.pop(identity))
        except Exception:
            self._error()

    def _paused(self, event):
        try:
            if event.get('frameId') != self.frame:
                raise ValueError()
            identity = event.get('networkId')
            if not identity:
                raise ValueError()
            if identity not in self.requests:
                self.waiting[identity] = event
                return
            self._process(event)
        except Exception:
            self._error(event.get('requestId'))

    def _process(self, event):
        identity = event['networkId']
        entry = self.requests[identity]
        request = event['request']
        if event.get('frameId') != self.frame:
            raise ValueError()
        origin, logical = self.policy.classify(self.base, request['url'], event['resourceType'],
                                               request['method'], request['headers'])
        if event['resourceType'] == 'Document' and origin != self.base:
            raise ValueError()
        if 'responseStatusCode' in event:
            status = event['responseStatusCode']
            items = [(item['name'], item['value']) for item in event.get('responseHeaders', [])]
            require_header_items(items)
            lower = {name.lower(): value for name, value in items}
            if (300 <= status < 400 and 'location' in lower
                    or 'text/event-stream' in lower.get('content-type', '').lower()):
                raise ValueError()
            entry['status'] = status
            self.target_guard.send('Fetch.continueResponse', {'requestId': event['requestId']})
            return
        if event.get('responseErrorReason'):
            if entry.get('action') is not None:
                raise ValueError()
            # Let Chromium finish the failed background transport. Its failure
            # event records unavailable diagnostics without fabricating a body.
            self.target_guard.send('Fetch.continueRequest', {'requestId': event['requestId']})
            return
        entry.update(origin=origin, logical=logical, fetch_id=event['requestId'],
                     preflight=event['resourceType'] == 'Preflight' or request['method'] == 'OPTIONS')
        if logical is not None:
            request_items = list(request['headers'].items())
            require_header_items(request_items)
            body = None
            raw = request.get('postData')
            if request.get('hasPostData') and raw is None:
                raw = self.session.send('Network.getRequestPostData', {'requestId': identity})['postData']
            if raw is not None:
                body = parse_form_body(raw.encode('utf-8')) if is_form_content_type(request_items) else json.loads(raw)
                if body is not None and type(body) is not dict:
                    raise ValueError()
            lower = {name.lower(): value for name, value in request_items}
            traceparent = lower.get('traceparent')
            trace_id = None
            if traceparent is not None:
                if not re.fullmatch(r'[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}', traceparent):
                    raise ValueError()
                trace_id = traceparent.split('-')[1]
            spec = ports.RequestSpec(request['method'], logical, body, traceparent,
                                     query=parse_query(urlsplit(request['url']).query))
            entry.update(spec=spec, request_items=request_items, trace_id=trace_id,
                         actual_path=urlsplit(request['url']).path, fixture_id=None)
            if self.context.mode == 'mock':
                # Preflight responses are not invented from transport policy.
                if event['resourceType'] == 'Preflight' or request['method'] == 'OPTIONS':
                    raise ValueError()
                queue = self.context.mock_queue
                if queue.index >= len(queue.plan):
                    raise ValueError()
                fixture = queue.plan[queue.index]
                if ((fixture.method, fixture.path) != (spec.method, spec.path)
                        or fixture.query is not None and fixture.query != spec.query
                        or fixture.request_headers is not None and not match_headers(fixture.request_headers, request_items)):
                    raise ValueError()
                headers = {'content-type': 'application/json'}
                headers.update(header_map(fixture.response_headers or {}))
                text = json.dumps(copy.deepcopy(fixture.response), allow_nan=False)
                queue.index += 1
                entry['fixture_id'] = fixture.fixture_id
                self.mock_pending.append(identity)
                self._claim(entry)
                self.target_guard.send('Fetch.fulfillRequest', {
                    'requestId': event['requestId'], 'responseCode': fixture.status,
                    'responseHeaders': [{'name': name, 'value': value} for name, value in headers.items()],
                    'body': base64.b64encode(text.encode()).decode('ascii'),
                })
                return
        self._claim(entry)
        self.target_guard.send('Fetch.continueRequest', {'requestId': event['requestId']})

    def _claim(self, entry):
        nonce = entry.pop('claim', None)
        if nonce is None:
            return
        # Classification precedes this exact-request response-clone claim. A
        # background handle is discarded without reading its response body.
        expression = 'window.__refractBrowser.claimNative(' + json.dumps(nonce) + ',' + json.dumps(entry['action']) + ')'
        result = self.session.send('Runtime.evaluate', {
            'expression': expression, 'returnByValue': True,
        })
        if 'exceptionDetails' in result or (entry['action'] is not None and result.get('result', {}).get('value') is not True):
            raise ValueError()

    @staticmethod
    def _raw_headers(headers):
        # CDP ExtraInfo specifies newline-separated duplicate raw header values.
        items = [(name, value) for name, values in headers.items() for value in values.split('\n')]
        require_header_items(items)
        return items

    def _request_extra(self, event):
        entry = self.requests.get(event['requestId'])
        if entry is None:
            self.extra_requests[event['requestId']] = event
        else:
            try:
                entry['actual_request_items'] = self._raw_headers(event['headers'])
            except Exception:
                self._error()

    def _response_extra(self, event):
        entry = self.requests.get(event['requestId'])
        if entry is None:
            self.extra_responses[event['requestId']] = event
        else:
            try:
                entry['header_items'] = self._raw_headers(event['headers'])
                if 'finished' in entry:
                    self._finished(entry['finished'])
            except Exception:
                self._error()

    def _response(self, event):
        entry = self.requests.get(event['requestId'])
        if entry is not None:
            entry['status'] = event['response']['status']
            entry['needs_extra'] = event.get('hasExtraInfo', False)
            if not entry['needs_extra']:
                # Synthetic/cached responses may have no complete raw block.
                # Network.responseReceived alone filters forbidden headers.
                entry['header_items'] = None
            if 'finished' in entry:
                self._finished(entry['finished'])

    def _truncate(self):
        if _NOTICE not in self.notes:
            self.notes.append(_NOTICE)

    def _data(self, event):
        entry = self.requests.get(event['requestId'])
        if entry is None or entry.get('logical') is None:
            return
        entry['received_bytes'] = entry.get('received_bytes', 0) + event.get('dataLength', 0)
        if entry['received_bytes'] > 8 * 1024 * 1024:
            entry['over_limit'] = True
            if entry.get('action') is not None or self.context.mode == 'mock':
                self._error()
            else:
                self._truncate()
        elif entry.get('action') is None and entry['received_bytes'] > 256 * 1024 - self.background_bytes:
            entry['drop_diagnostic'] = True
            self._truncate()

    def _finished(self, event):
        identity = event['requestId']
        entry = self.requests.get(identity)
        if entry is None:
            return
        entry['finished'] = event
        if entry.get('logical') is not None and not entry.get('preflight') and 'header_items' not in entry:
            return
        try:
            entry['done'] = True
            if entry.get('logical') is None or entry.get('preflight') or entry.get('over_limit'):
                return
            diagnostic = entry['action'] is None
            if diagnostic and self.context.mode != 'mock' and (
                    self.background_count >= 100 or entry.get('drop_diagnostic')
                    or event.get('encodedDataLength', 0) > 256 * 1024 - self.background_bytes):
                self._truncate()
                return
            body = self.session.send('Network.getResponseBody', {'requestId': identity})
            text = (base64.b64decode(body['body'], validate=True).decode('utf-8')
                    if body.get('base64Encoded') else body['body'])
            if len(text.encode('utf-8')) > 8 * 1024 * 1024:
                raise ValueError()
            try:
                value = json.loads(text)
            except (ValueError, TypeError):
                value = None
            items = entry['header_items']
            spec = entry['spec']
            permit = self.context.permits.get(entry['action'])
            network = ports.BrowserNetworkIdentity(origin=entry['origin'], request_id=identity)
            public_request_id = self.request_namespace + ':' + identity
            recording = ports.RecordedResponse(
                int(entry['status']), {} if items is None else {name.lower(): v for name, v in items},
                value, text, entry['trace_id'], copy.deepcopy(spec),
                step_id=permit.step_id if permit else None, actual_path=entry['actual_path'],
                request_id=public_request_id, mock_fixture_id=entry['fixture_id'],
                user=self.context.user, session_generation=self.context.session_generation,
                request_header_items=copy.deepcopy(entry['request_items'] if self.context.mode == 'mock' else entry.get('actual_request_items')), header_items=copy.deepcopy(items),
                browser_identity=copy.deepcopy(network),
            )
            if diagnostic:
                size = len(json.dumps(asdict(recording), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))
                if self.background_count >= 100 or self.background_bytes + size > 256 * 1024:
                    if self.context.mode == 'mock':
                        # Mock consumption is exact; truncation must not conceal
                        # consumed fixture records from the core verifier.
                        raise ValueError()
                    self._truncate()
                    return
                self.background_count += 1
                self.background_bytes += size
                self.context.diagnostics.append(recording)
            else:
                self.context.traffic.append(ports.UiTraffic(
                    execution_id=permit.execution_id, action_id=permit.action_id,
                    step_id=permit.step_id, mode=permit.mode, request_id=public_request_id,
                    permit_token=permit.token, request=spec, response=recording,
                    mock_fixture_id=entry['fixture_id'], user=permit.user,
                    session_generation=permit.session_generation, context_id=permit.context_id,
                    browser_identity=network,
                ))
            entry['recording'] = recording
            self._flush_mocks()
        except Exception:
            self._error()
        finally:
            # Retain only in-flight requests and exact mock ordering state. Large
            # raw transport events are not an unbounded second diagnostics log.
            if identity not in self.mock_pending:
                self.requests.pop(identity, None)

    def _flush_mocks(self):
        while self.mock_pending:
            identity = self.mock_pending[0]
            entry = self.requests.get(identity)
            if entry is None or 'recording' not in entry:
                break
            self.context.mock_recordings.append(entry['recording'])
            self.mock_pending.pop(0)
            self.requests.pop(identity, None)

    def _failed(self, event):
        entry = self.requests.pop(event['requestId'], None)
        if entry is not None:
            # A CORS-blocked response never becomes usable response evidence,
            # even if the server completed its side of the exchange. Policy
            # failures have already made the context erroneous before aborting.
            if entry.get('action') is not None or event.get('corsErrorStatus'):
                self._error()
            elif 'background HTTP acquisition failed' not in self.notes:
                self.notes.append('background HTTP acquisition failed')

    def collect(self, action_id):
        # Wait only for current-origin work and a finite consumed mock boundary.
        pending_mock = set(self.mock_pending)
        while (any(e.get('action') == action_id and not e['done'] for e in self.requests.values())
               or pending_mock.intersection(self.mock_pending)):
            self.owner._check(self.context)
            self.context.page.wait_for_timeout(min(10, self.owner._remaining(self.context)))
        self.owner._check(self.context)
