"""Product-neutral query values and strict decoded HTTP query evidence.

Errors deliberately describe the invalid shape, never its potentially sensitive
keys or values. Paths and query parameters remain separate until transport.
"""
import json
import math
import re
from urllib.parse import unquote_plus, urlencode


def is_query_scalar(value):
    return type(value) in (str, int, bool) or (type(value) is float and math.isfinite(value))


def wire_query(mapping):
    """Return an independent mapping using the declared scalar wire spelling."""
    if type(mapping) is not dict:
        raise ValueError("query must be a mapping")
    result = {}
    for key, value in mapping.items():
        if type(key) is not str or not key:
            raise ValueError("query keys must be nonempty literal strings")
        if not is_query_scalar(value):
            raise ValueError("query values must be strings, integers, booleans, or finite floats")
        result[key] = value if type(value) is str else json.dumps(value, allow_nan=False)
    try:
        for key, value in result.items():
            key.encode("utf-8")
            value.encode("utf-8")
    except UnicodeError:
        raise ValueError("query requires valid UTF-8 strings") from None
    return result


def require_wire_query(mapping):
    """Validate actual evidence without coercing unsupported observed types."""
    if type(mapping) is not dict or any(type(value) is not str for value in mapping.values()):
        raise ValueError("observed query must be a mapping of strings")
    return wire_query(mapping)


def parse_query(rawstr):
    """Decode a URL query, rejecting malformed encoding and duplicate keys."""
    if type(rawstr) is not str:
        raise ValueError("URL query must be a string")
    if re.search(r"%(?![0-9a-fA-F]{2})", rawstr):
        raise ValueError("malformed query percent encoding")
    result = {}
    for pair in rawstr.split("&") if rawstr else []:
        key, _, value = pair.partition("=")
        try:
            key = unquote_plus(key, encoding="utf-8", errors="strict")
            value = unquote_plus(value, encoding="utf-8", errors="strict")
        except UnicodeError:
            raise ValueError("query requires valid UTF-8 encoding") from None
        if key in result:
            raise ValueError("duplicate decoded query key")
        result[key] = value
    return require_wire_query(result)


def request_path(path, query):
    """Encode each parameter once, leaving the separately owned route intact."""
    if type(path) is not str or not path or "?" in path or "#" in path:
        raise ValueError("request path must not contain an embedded query or fragment")
    encoded = urlencode(wire_query(query))
    return path + ("?" + encoded if encoded else "")
