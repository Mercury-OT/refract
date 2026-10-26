"""Decode observed ordinary forms without consulting Scenario expectations.

This bounded policy rejects unrepresentable fields instead of choosing values.
Non-form requests retain BrowserSupport's existing JSON decoding path.
"""

import re

from refracto.query import parse_query


_FORM = "application/x-www-form-urlencoded"
_FORM_CLAIM = re.compile(r"\s*" + re.escape(_FORM) + r"(?=$|[\s;])", re.IGNORECASE | re.ASCII)
_FORM_HEADER = re.compile(
    r"[ \t]*" + re.escape(_FORM) + r"[ \t]*"
    r'(?:;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8")[ \t]*)?',
    re.IGNORECASE | re.ASCII,
)


def _combined_media_values(value):
    """Split combined media values without mistaking quoted parameters for one."""
    start, quoted, escaped = 0, False, False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "," and not quoted:
            yield value[start:index]
            start = index + 1
    yield value[start:]


def is_form_content_type(header_items):
    """Recognize actual form media types and reject ambiguous form claims."""
    values = [value for name, value in header_items if name.lower() == "content-type"]
    claimed = any(_FORM_CLAIM.match(part) for value in values
                  for part in _combined_media_values(value))
    if not claimed:
        return False
    if len(values) != 1 or _FORM_HEADER.fullmatch(values[0]) is None:
        raise ValueError("browser form Content-Type is unsupported or ambiguous")
    return True


def parse_form_body(raw):
    """Preserve absent bytes; otherwise decode once into independent strings."""
    if raw is None:
        return None
    try:
        if type(raw) is not bytes:
            raise ValueError
        return parse_query(raw.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeError):
        raise ValueError("browser form body is invalid") from None
