"""Bounded business headers and complete, sensitive HTTP header evidence.

All diagnostics intentionally describe the condition, never a header value.
Raw pairs remain ordered and duplicate-preserving; maps cannot establish absence.
"""
import re

CHECKS = frozenset({"header_equals", "header_absent"})
_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", re.ASCII)
_RESERVED = frozenset(name.lower() for name in (
    "Authorization", "Proxy-Authorization", "Cookie", "Set-Cookie", "Host",
    "Content-Length", "Content-Type", "Transfer-Encoding", "Connection", "TE",
    "Trailer", "Upgrade", "Expect", "Accept-Encoding", "Origin", "Referer",
    "User-Agent", "Traceparent", "Tracestate",
))


def validate_name(name, *, business=False):
    if type(name) is not str or _TOKEN.fullmatch(name) is None:
        raise ValueError("header name must be a nonempty literal ASCII HTTP token")
    folded = name.lower()
    if business and (folded in _RESERVED or folded.startswith(("proxy-", "sec-", "x-refract-"))):
        raise ValueError("credential and transport header declarations are forbidden")
    return folded


def validate_value(value):
    if (type(value) is not str or value != value.strip()
            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
        raise ValueError("header value must be a string of visible ASCII without surrounding whitespace")
    return value


def header_map(mapping, *, business=False):
    if type(mapping) is not dict:
        raise ValueError("headers must be a mapping")
    result = {}
    for name, value in mapping.items():
        folded = validate_name(name, business=business)
        if folded in result:
            raise ValueError("duplicate case-insensitive header name")
        result[folded] = validate_value(value)
    return result


def business_headers(mapping):
    return header_map(mapping, business=True)


def require_header_items(items):
    if type(items) is not list:
        raise ValueError("complete header evidence is unavailable or malformed")
    for pair in items:
        if (type(pair) not in (tuple, list) or len(pair) != 2
                or type(pair[0]) is not str or type(pair[1]) is not str):
            raise ValueError("complete header evidence is unavailable or malformed")
        validate_name(pair[0])
        # Observations preserve HTTP field-value bytes, including HTAB and
        # obs-text, without adopting the sender's narrower ASCII constraint.
        if any((ord(char) < 32 and char != "\t") or ord(char) == 127 or ord(char) > 255
               for char in pair[1]):
            raise ValueError("complete header evidence is malformed")
    return items


def _observed(items, name):
    folded = validate_name(name)
    matches = [value for key, value in require_header_items(items) if key.lower() == folded]
    if len(matches) > 1:
        raise ValueError("asserted header has multiple occurrences; evidence is unsupported")
    return matches


def match_headers(expected, items):
    """Subset comparison; validate every asserted name before returning mismatch."""
    wanted = header_map(expected)
    if not wanted:
        return True
    observed = {name: _observed(items, name) for name in wanted}
    return all(observed[name] == [value] for name, value in wanted.items())


def evaluate(check, name, expected, items):
    observed = _observed(items, name)
    if check == "header_equals":
        validate_value(expected)
        ok = observed == [expected]
        return ok, "" if ok else "response header is missing or differs from its declaration"
    if check == "header_absent":
        ok = not observed
        return ok, "" if ok else "response header required absent is present"
    raise ValueError("unsupported response header check")


def declared(step):
    return bool((step.request is not None and step.request.headers)
                or any(assertion.check in CHECKS for assertion in step.expect.response))


def recorded(response):
    return bool(getattr(response.request, "headers", None) or response.headers
                or response.request_header_items is not None or response.header_items is not None)


def call_port(operation, callback, *args, sensitive=False, **kwargs):
    """Do not copy an external exception's header data into a report.

    This only guards explicitly header-bearing port calls. It does not inspect
    arbitrary values, serialize objects, or sanitize unrelated port behavior.
    """
    try:
        return callback(*args, **kwargs)
    except Exception:
        if not sensitive:
            raise
        raise ValueError(f"{operation} failed while handling sensitive header data") from None
