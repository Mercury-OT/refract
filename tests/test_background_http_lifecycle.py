"""Unrepresented background bodies must never become primary request evidence."""
from types import SimpleNamespace
import copy

import pytest

from refracto.errors import ActionFailure, ActionFailureReason as Reason
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy
from tests.test_browser_diagnostic_work import collector

NOTICE = 'background request body not represented'
BASE = 'https://' + 'example.com'


def request(subject, raw='["member", "reader"]', *, action=None, headers=None, query=''):
    subject.base = BASE
    subject.frame = 'frame'
    subject.policy = BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(BASE, '/api', 'records'),))
    subject.context.selecting_file = False
    subject.context.block_unassociated_mock = False
    subject.context.mock_queue = SimpleNamespace(index=0, plan=[object()])
    subject.guard_calls = []
    subject.target_guard = SimpleNamespace(send=lambda method, value: subject.guard_calls.append((method, copy.deepcopy(value))))
    subject.extra_requests = {}
    subject.extra_responses = {}
    subject.requests['network'] = {'action': action, 'done': False}
    return {'networkId': 'network', 'requestId': 'fetch', 'frameId': 'frame',
            'resourceType': 'Fetch', 'request': {'url': BASE + '/api/items' + query,
                'method': 'POST', 'headers': headers or {'Content-Type': 'application/json'},
                'hasPostData': True, 'postData': raw}}


def finish(subject):
    subject._response({'requestId': 'network', 'response': {'status': 200}, 'hasExtraInfo': True})
    subject._finished({'requestId': 'network', 'encodedDataLength': 20})
    assert 'network' in subject.requests  # The response header fence still applies.
    subject._response_extra({'requestId': 'network', 'headers': {'Content-Type': 'application/json'}})


def test_background_array_forwards_without_modification_or_invalid_recording():
    subject = collector()
    event = request(subject)
    before = copy.deepcopy(event)
    subject._process(event)
    assert event == before
    assert subject.guard_calls == [('Fetch.continueRequest', {'requestId': 'fetch'})]
    assert 'spec' not in subject.requests['network']
    assert subject.notes == [NOTICE]
    finish(subject)
    assert subject.requests == subject.extra_responses == {}
    assert subject.calls == [] and subject.background_reads == 0
    assert subject.context.traffic == subject.context.diagnostics == subject.context.mock_recordings == []
    assert subject.context.errors == []
    subject._finished({'requestId': 'network', 'encodedDataLength': 20})
    assert subject.calls == [] and subject.requests == {}


def test_repeated_background_arrays_do_not_accumulate_records_or_notes():
    subject = collector()
    for _ in range(120):
        subject._process(request(subject))
        finish(subject)
    assert subject.notes == [NOTICE]
    assert subject.calls == [] and subject.background_count == subject.background_bytes == 0
    assert subject.requests == {} and subject.context.errors == []


@pytest.mark.parametrize(('mode', 'action'), [('live', 'action'), ('mock', None), ('mock', 'action')])
def test_arrays_are_not_permitted_for_primary_or_mock_requests(mode, action):
    subject = collector(mode=mode)
    with pytest.raises(ValueError):
        subject._process(request(subject, action=action))
    assert subject.guard_calls == [] and subject.context.mock_queue.index == 0
    assert subject.notes == [] and 'spec' not in subject.requests['network']


@pytest.mark.parametrize('raw', ['1', 'true', '"text"', 'not json', '[NaN]', '[{"value": Infinity}]'])
def test_other_body_shapes_are_not_implicitly_supported(raw):
    subject = collector()
    with pytest.raises(ValueError):
        subject._process(request(subject, raw))
    assert subject.guard_calls == [] and subject.notes == []


@pytest.mark.parametrize(('headers', 'query'), [
    ({'Content-Type': 'application/json', 'traceparent': 'bad'}, ''),
    ({'Content-Type': 'application/json'}, '?bad=%FF'),
    ({'Content-Type': 'application/json', 'Cookie': 'secret'}, ''),
])
def test_background_exception_preserves_trace_query_and_credentials(headers, query):
    subject = collector()
    with pytest.raises((ValueError, ActionFailure)):
        subject._process(request(subject, headers=headers, query=query))
    assert subject.guard_calls == [] and subject.notes == []


@pytest.mark.parametrize('selection', ['selecting', 'ancestry'])
def test_file_selection_guard_precedes_array_exception(selection):
    subject = collector()
    event = request(subject)
    if selection == 'selecting':
        subject.context.selecting_file = True
    else:
        subject.requests['network']['denied_selection'] = True
    with pytest.raises(ActionFailure) as error:
        subject._process(event)
    assert error.value.reason is Reason.POLICY_DENIED
    assert subject.guard_calls == [] and subject.notes == []


@pytest.mark.parametrize(('status', 'headers'), [
    (302, [{'name': 'Location', 'value': '/elsewhere'}]),
    (200, [{'name': 'Content-Type', 'value': 'text/event-stream'}]),
])
def test_response_guards_apply_to_omitted_diagnostics(status, headers):
    subject = collector()
    event = request(subject)
    subject._process(event)
    with pytest.raises(ActionFailure) as error:
        subject._process(dict(event, responseStatusCode=status, responseHeaders=headers))
    assert error.value.reason is Reason.POLICY_DENIED
    assert subject.guard_calls == [('Fetch.continueRequest', {'requestId': 'fetch'})]


@pytest.mark.parametrize('cors', [False, True])
def test_omitted_background_failure_still_has_correct_failure_classification(cors):
    subject = collector()
    subject._process(request(subject))
    event = {'requestId': 'network'}
    if cors:
        event['corsErrorStatus'] = {'corsError': 'DisallowedByMode'}
    subject._failed(event)
    assert subject.requests == {}
    assert subject.context.errors == ([Reason.POLICY_DENIED] if cors else [])
    assert subject.notes == ([NOTICE] if cors else [NOTICE, 'background HTTP acquisition failed'])


def test_omitted_array_response_size_limits_are_still_visible():
    subject = collector()
    subject._process(request(subject))
    subject._data({'requestId': 'network', 'dataLength': 9 * 1024 * 1024})
    finish(subject)
    assert subject.notes == [NOTICE, 'background diagnostics truncated']
    assert subject.context.errors == [] and subject.requests == {} and subject.calls == []
