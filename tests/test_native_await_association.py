"""Offline bounds and rejection cases for Chromium invocation ancestry."""
import pytest

from refracto_browser._async_origin import ASYNC_DEPTH, invocation_origin


def scope(origin='action'):
    return '__refract_invocation_' + 'a'*32 + '__' + origin


def stack(*names, parent=None, description=None):
    value = {'callFrames': [{'functionName': name} for name in names]}
    if parent is not None:
        value['parent'] = parent
    if description is not None:
        value['description'] = description
    return value


def test_nearest_scope_and_null_scope_win_over_outer_action():
    assert invocation_origin(stack(scope('first'), scope('second'))) == 'first'
    assert invocation_origin(stack(scope(''), scope('second'))) is None
    assert invocation_origin(stack(scope('owner%2Fcreate'))) == 'owner/create'


@pytest.mark.parametrize('edge', ['await', 'Promise.then'])
def test_only_proven_async_edges_reach_scope(edge):
    assert invocation_origin(stack('fetch', parent=stack(scope(), description=edge))) == 'action'


@pytest.mark.parametrize('edge', ['setTimeout', 'setInterval', 'requestAnimationFrame', 'queueMicrotask', '', None, [], {}])
def test_background_and_unknown_edges_stop_before_scope(edge):
    assert invocation_origin(stack('fetch', parent=stack(scope(), description=edge))) is None


@pytest.mark.parametrize('bad', [None, [], {}, {'callFrames': {}}, {'callFrames': [None]},
                                {'callFrames': [{'functionName': None}]},
                                stack('__refract_invocation_malformed', scope()),
                                stack('x'*4097, scope()), stack(*(['x']*129), scope())])
def test_malformed_or_oversized_stacks_do_not_provide_origin(bad):
    assert invocation_origin(bad) is None


def test_external_parent_identity_is_not_followed():
    assert invocation_origin({'callFrames': [], 'parentId': {'id': 'external'}}) is None


def test_depth_and_total_frame_budgets_are_finite():
    value = stack(scope(), description='await')
    for _ in range(ASYNC_DEPTH):
        value = stack('inner', parent=value, description='await')
    assert invocation_origin(value) == 'action'
    assert invocation_origin(stack('overflow', parent=value)) is None
    value = stack(scope(), description='await')
    for _ in range(9):
        value = stack(*(['inner']*128), parent=value, description='await')
    assert invocation_origin(value) is None
