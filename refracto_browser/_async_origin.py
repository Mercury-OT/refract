"""Bounded Chromium invocation ancestry, never endpoint or timing inference."""
import re
from urllib.parse import unquote


ASYNC_DEPTH = 32
_INVOCATION = re.compile(r'^__refract_invocation_[0-9a-f]{32}__(.*)$')
_PREFIX = '__refract_invocation_'
_EDGES = frozenset({'await', 'Promise.then'})


def invocation_origin(stack):
    """Return the nearest invocation's origin, or no evidence.

    Every asynchronous edge must be supported before its parent is inspected.
    A null/malformed inner scope is a barrier, not permission to use an outer
    scope. External parent IDs, truncated stacks and excessive input are not
    followed. This establishes origin only, not awaited completion membership.
    """
    frames_seen = 0
    for _ in range(ASYNC_DEPTH + 1):
        if type(stack) is not dict or type(stack.get('callFrames')) is not list:
            return None
        frames = stack['callFrames']
        frames_seen += len(frames)
        if len(frames) > 128 or frames_seen > 1024:
            return None
        for frame in frames:
            if type(frame) is not dict or type(frame.get('functionName')) is not str:
                return None
            name = frame['functionName']
            if len(name) > 4096:
                return None
            if name.startswith(_PREFIX):
                marker = _INVOCATION.fullmatch(name)
                return (unquote(marker.group(1)) or None) if marker else None
        parent = stack.get('parent')
        if (type(parent) is not dict or type(parent.get('description')) is not str
                or parent['description'] not in _EDGES):
            return None
        stack = parent
    return None
