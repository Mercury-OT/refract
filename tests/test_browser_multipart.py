"""Complete native bytes and strict multipart observation, without fixtures as evidence."""
import base64
import hashlib

import pytest

from refracto_browser._multipart import OVERHEAD_LIMIT, multipart_boundary, native_body, parse_multipart


def multipart(payload=b'\x00\xff\x80', *, name='attachment', filename='sample.bin', text=b'neutral'):
    return (b'--boundary\r\nContent-Disposition: form-data; name="title"\r\n\r\n' + text
            + b'\r\n--boundary\r\nContent-Disposition: form-data; name="' + name.encode()
            + b'"; filename="' + filename.encode() + b'"\r\nContent-Type: application/octet-stream\r\n\r\n'
            + payload + b'\r\n--boundary--\r\n')


@pytest.mark.parametrize('payload', [b'', b'neutral text\n', b'\x00\xff\x80', b'%PDF-1.7\n', b'\x89PNG\r\n\x1a\n'])
def test_complete_native_bytes_preserve_actual_file(payload):
    raw = multipart(payload)
    request = {'postData': 'not evidence', 'postDataEntries': [
        {'bytes': base64.b64encode(raw[:7]).decode()}, {'bytes': ''},
        {'bytes': base64.b64encode(raw[7:]).decode()}]}
    captured = native_body(request, 1024)
    assert captured == raw
    body, files = parse_multipart(captured, b'boundary', 100)
    assert body == {'title': 'neutral'}
    assert files['attachment'].data == payload
    assert files['attachment'].sha256 == hashlib.sha256(payload).hexdigest()
    assert files['attachment'].filename == 'sample.bin'


@pytest.mark.parametrize('entries', [None, [], [{}], [{'bytes': ''}, {}], [{'bytes': None}],
    [{'bytes': '%%%'}], [{'bytes': 'YQ==='}], [{'bytes': 'YR=='}], [{'bytes': '', 'other': ''}],
    [{'bytes': ''}] * 129])
def test_missing_disk_entries_and_invalid_encodings_never_fall_back(entries):
    with pytest.raises((ValueError, TypeError)):
        native_body({'postData': 'complete-looking text', 'postDataEntries': entries}, 100)


@pytest.mark.parametrize('header', ['multipart/form-data', 'multipart/form-data; boundary=a; boundary=b',
    'multipart/form-data; boundary=a, application/json', 'multipart/mixed; boundary=a',
    'multipart/form-data; boundary="a\\b"'])
def test_invalid_or_ambiguous_content_type(header):
    with pytest.raises(ValueError):
        multipart_boundary([('Content-Type', header)])


def test_complete_fileless_and_empty_bodies_are_observed():
    assert parse_multipart(b'--boundary--\r\n', b'boundary', 10) == ({}, None)
    raw = b'--boundary\r\nContent-Disposition: form-data; name="title"\r\n\r\nneutral\r\n--boundary--\r\n'
    assert parse_multipart(raw, b'boundary', 10) == ({'title': 'neutral'}, None)


@pytest.mark.parametrize('change', [
    lambda r: r[:-1], lambda r: b'preamble'+r, lambda r: r+b'epilogue',
    lambda r: r.replace(b'name="title"', b'name="attachment"'),
    lambda r: r.replace(b'name="title"', b'name="title"; name="other"'),
    lambda r: r.replace(b'Content-Type: application/octet-stream', b'Content-Type: multipart/mixed'),
    lambda r: r.replace(b'Content-Type: application/octet-stream', b'Content-Transfer-Encoding: base64'),
    lambda r: r.replace(b'Content-Type: application/octet-stream', b'Content-Type: application/octet-stream\r\nContent-Type: text/plain'),
    lambda r: r.replace(b'neutral', b'\xff'),
    lambda r: r.replace(b'filename="sample.bin"', b'filename="../sample.bin"'),
])
def test_ambiguous_or_incomplete_multipart_is_invalid(change):
    with pytest.raises((ValueError, UnicodeError)):
        parse_multipart(change(multipart()), b'boundary', 100)


def test_decoded_file_and_total_overhead_limits_are_exact():
    raw = multipart(b'x' * 100)
    assert parse_multipart(raw, b'boundary', 100)[1]['attachment'].data == b'x' * 100
    with pytest.raises(ValueError):
        parse_multipart(multipart(b'x' * 101), b'boundary', 100)
    with pytest.raises(ValueError):
        parse_multipart(multipart(b'', text=b'x' * OVERHEAD_LIMIT), b'boundary', 100)
    with pytest.raises(ValueError):
        native_body({'postDataEntries': [{'bytes': base64.b64encode(b'x' * 101).decode()}]}, 100)


def test_part_budget_and_multiple_files_are_invalid():
    part = b'--boundary\r\nContent-Disposition: form-data; name="%d"\r\n\r\nx\r\n'
    raw = b''.join(part % i for i in range(33)) + b'--boundary--\r\n'
    with pytest.raises(ValueError):
        parse_multipart(raw, b'boundary', 100)
    raw = multipart().replace(b'name="title"', b'name="title"; filename="extra.bin"')
    with pytest.raises(ValueError):
        parse_multipart(raw, b'boundary', 100)


def test_unnamed_empty_part_means_absent_file_but_is_still_counted():
    assert parse_multipart(multipart(b'', filename=''), b'boundary', 100) == ({'title': 'neutral'}, None)
    with pytest.raises(ValueError):
        parse_multipart(multipart(b'nonempty', filename=''), b'boundary', 100)
    raw = multipart(b'', filename='').replace(b'name="title"', b'name="title"; filename=""').replace(b'neutral', b'')
    with pytest.raises(ValueError):
        parse_multipart(raw, b'boundary', 100)


def test_earlier_terminal_boundary_cannot_be_misread_as_file_bytes():
    raw = multipart(b'first\r\n--boundary--\r\nepilogue')
    with pytest.raises(ValueError):
        parse_multipart(raw, b'boundary', 100)


@pytest.mark.parametrize('embedded', [b'\r\n--boundary \t\r\n', b'\r\n--boundary-- \t\r\n',
                                      b'\n--boundary\n', b'\r--boundary\r'])
def test_padded_or_noncanonical_delimiter_lines_are_not_file_bytes(embedded):
    with pytest.raises(ValueError):
        parse_multipart(multipart(b'first'+embedded+b'not-a-part'), b'boundary', 100)


def test_literal_near_boundary_binary_is_preserved():
    payload = b'\0\xff\r\n--boundaryX\r\n--boundary--X\r\n--boundary-X\r\nlast'
    assert parse_multipart(multipart(payload), b'boundary', 100)[1]['attachment'].data == payload
