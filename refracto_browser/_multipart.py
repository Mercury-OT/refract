"""Bounded multipart observations from complete native Chromium byte entries."""
import base64
import hashlib
import re

from refracto.files import require_files
from refracto.ports import UploadFile
from ._request_body import _combined_media_values


OVERHEAD_LIMIT = 64 * 1024
_TOKEN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
_BOUNDARY = re.compile(r"[0-9A-Za-z'()+_,./:=?\-]{1,70}", re.ASCII)
_MEDIA = re.compile(r'[ \t]*multipart/form-data[ \t]*;[ \t]*boundary[ \t]*=[ \t]*(?:"([^"\\]*)"|(' + _TOKEN + r'))[ \t]*', re.IGNORECASE | re.ASCII)
_DISPOSITION = re.compile(r'form-data((?:;[ \t]*(?:name|filename)="[^"\\\r\n]*")+)', re.ASCII)
_PARAMETER = re.compile(r';[ \t]*(name|filename)="([^"\\\r\n]*)"', re.ASCII)
_CONTENT_TYPE = re.compile(_TOKEN + '/' + _TOKEN + r'(?:;[ \t]*charset=(?:utf-8|"utf-8"))?', re.IGNORECASE | re.ASCII)


def multipart_boundary(header_items):
    values = [value for name, value in header_items if name.lower() == 'content-type']
    if not any(re.match(r'\s*multipart/', part, re.IGNORECASE | re.ASCII)
               for value in values for part in _combined_media_values(value)):
        return None
    match = _MEDIA.fullmatch(values[0]) if len(values) == 1 else None
    boundary = (match.group(1) or match.group(2)) if match else None
    if boundary is None or _BOUNDARY.fullmatch(boundary) is None:
        raise ValueError('browser multipart Content-Type is invalid')
    return boundary.encode('ascii')


def native_body(request, limit):
    """Never fill missing entries from a selected file, a fixture, or text data."""
    entries = request.get('postDataEntries')
    if type(entries) is not list or not 1 <= len(entries) <= 128:
        raise ValueError('browser multipart byte evidence is unavailable')
    encoded_limit = 4 * ((limit + 2) // 3) + 4 * len(entries)
    encoded_size = 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {'bytes'} or type(entry['bytes']) is not str:
            raise ValueError('browser multipart byte evidence is incomplete')
        encoded_size += len(entry['bytes'])
        if encoded_size > encoded_limit:
            raise ValueError('browser multipart byte budget exceeded')
    chunks, size = [], 0
    for entry in entries:
        chunk = base64.b64decode(entry['bytes'], validate=True)
        # Reject noncanonical padding/encodings as ambiguous evidence.
        if base64.b64encode(chunk).decode('ascii') != entry['bytes']:
            raise ValueError('browser multipart byte encoding is invalid')
        size += len(chunk)
        if size > limit:
            raise ValueError('browser multipart byte budget exceeded')
        chunks.append(chunk)
    return b''.join(chunks)


def parse_multipart(raw, boundary, max_file_bytes):
    """Decode only observed framing, text, filename and file bytes."""
    if type(raw) is not bytes or len(raw) > max_file_bytes + OVERHEAD_LIMIT:
        raise ValueError('browser multipart byte budget exceeded')
    opening, closing = b'--' + boundary + b'\r\n', b'\r\n--' + boundary + b'--\r\n'
    if raw == b'--' + boundary + b'--\r\n':
        return {}, None
    if not raw.startswith(opening) or not raw.endswith(closing):
        raise ValueError('browser multipart framing is incomplete')
    # MIME permits transport padding on delimiter lines. Ignoring those lines
    # (or an earlier closing delimiter) would turn framing into invented file
    # bytes. Recognize all delimiter lines, then accept only our canonical
    # CRLF framing without padding, early closure or epilogue. Near-boundary
    # bytes with other suffixes are ordinary payload and remain unchanged.
    delimiter = re.compile(rb'(?:\A|(?<=[\r\n]))--' + re.escape(boundary)
                           + rb'(?:--)?[ \t]*(?=[\r\n]|\Z)')
    count = 0
    for match in delimiter.finditer(raw):
        count += 1
        final = match.end() == len(raw) - 2
        expected = b'--' + boundary + (b'--' if final else b'')
        if (count > 33 or match.group() != expected
                or raw[match.end():match.end() + 2] != b'\r\n'
                or match.start() and raw[match.start() - 2:match.start()] != b'\r\n'):
            raise ValueError('browser multipart framing is ambiguous')
    interior = raw[len(opening):-len(closing)]
    parts = interior.split(b'\r\n--' + boundary + b'\r\n')
    if len(parts) > 32:
        raise ValueError('browser multipart part budget exceeded')
    body, files, names, file_size, file_parts = {}, {}, set(), 0, 0
    for part in parts:
        header, separator, payload = part.partition(b'\r\n\r\n')
        if not separator or len(header) > OVERHEAD_LIMIT:
            raise ValueError('browser multipart part is incomplete')
        headers = {}
        for line in header.split(b'\r\n'):
            name, colon, value = line.partition(b':')
            if not colon or re.fullmatch(_TOKEN.encode(), name) is None:
                raise ValueError('browser multipart part header is invalid')
            key = name.decode('ascii').lower()
            if key in headers or key not in {'content-disposition', 'content-type'}:
                raise ValueError('browser multipart part header is unsupported')
            headers[key] = value.strip(b' \t').decode('utf-8', errors='strict')
        disposition = headers.get('content-disposition', '')
        if _DISPOSITION.fullmatch(disposition) is None:
            raise ValueError('browser multipart disposition is invalid')
        parameters = _PARAMETER.findall(disposition)
        params = dict(parameters)
        if len(params) != len(parameters) or 'name' not in params or not params['name']:
            raise ValueError('browser multipart disposition is ambiguous')
        name = params['name']
        if any(ord(c) < 32 or ord(c) == 127 for c in name) or name in names:
            raise ValueError('browser multipart field is ambiguous')
        names.add(name)
        content_type = headers.get('content-type')
        if content_type is not None and (_CONTENT_TYPE.fullmatch(content_type) is None
                                        or content_type.lower().startswith('multipart/')):
            raise ValueError('browser multipart part type is unsupported')
        if 'filename' in params:
            file_parts += 1
            if file_parts > 1 or len(payload) > max_file_bytes:
                raise ValueError('browser multipart file budget exceeded')
            if not params['filename']:
                if payload:
                    raise ValueError('browser multipart unnamed file is invalid')
                # A normal unselected file input serializes an unnamed empty
                # part. Observe absence; a named empty file remains a file.
                continue
            if re.search(r'%(?:22|0a|0d)', params['filename'], re.IGNORECASE):
                raise ValueError('browser escaped file names are unsupported')
            file_size = len(payload)
            files[name] = UploadFile(filename=params['filename'], data=payload,
                                     sha256=hashlib.sha256(payload).hexdigest())
            require_files(files)
        else:
            if len(payload) > OVERHEAD_LIMIT:
                raise ValueError('browser multipart overhead budget exceeded')
            if content_type is not None and content_type.lower() not in {
                    'text/plain', 'text/plain; charset=utf-8', 'text/plain; charset="utf-8"'}:
                raise ValueError('browser multipart text type is unsupported')
            body[name] = payload.decode('utf-8', errors='strict')
    if len(raw) - file_size > OVERHEAD_LIMIT:
        raise ValueError('browser multipart overhead budget exceeded')
    return body, files or None
