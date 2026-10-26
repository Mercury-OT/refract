"""Offline checks for truthful, bounded browser form observation."""

import pytest

from refracto_browser._request_body import is_form_content_type, parse_form_body


FORM = "application/x-www-form-urlencoded"


@pytest.mark.parametrize("value", [
    FORM,
    FORM.upper(),
    " \t" + FORM + "\t ",
    FORM + ";charset=UTF-8",
    FORM + '; charset="utf-8"',
    FORM.upper() + ' ; CHARSET = "UTF-8"\t',
])
def test_form_media_type_is_case_insensitive_and_utf8_only(value):
    assert is_form_content_type([("Other", "irrelevant"), ("cOnTeNt-TyPe", value)]) is True


@pytest.mark.parametrize("headers", [
    [],
    [("Content-Type", "application/json")],
    [("Content-Type", "text/plain;charset=UTF-8")],
    [("Content-Type", FORM + "-other")],
    [("Content-Type", "x-" + FORM)],
    [("Content-Type", 'text/plain; note="' + FORM + '"')],
    [("Content-Type", 'text/plain; note="prefix,' + FORM + '"')],
    [("Content-Type", "application/json"), ("content-type", "text/plain")],
])
def test_non_form_headers_retain_the_existing_json_path(headers):
    assert is_form_content_type(headers) is False


@pytest.mark.parametrize("headers", [
    [("Content-Type", FORM), ("content-type", FORM)],
    [("Content-Type", "application/json"), ("content-type", FORM)],
    [("Content-Type", FORM + ", application/json")],
    [("Content-Type", "application/json, " + FORM)],
    [("Content-Type", "application/json;charset=utf-8, " + FORM)],
    [("Content-Type", FORM + ";charset=ascii")],
    [("Content-Type", FORM + ";charset=utf8")],
    [("Content-Type", FORM + ";charset=utf-8;charset=utf-8")],
    [("Content-Type", FORM + ";boundary=private-sentinel")],
    [("Content-Type", FORM + ";")],
    [("Content-Type", FORM + ';charset="utf-8')],
    [("Content-Type", FORM + ";charset=utf-8, " + FORM)],
    [("Content-Type", FORM + " charset=utf-8")],
    [("Content-Type", FORM + "\n")],
])
def test_ambiguous_or_unsupported_form_headers_fail_without_values(headers):
    with pytest.raises(ValueError) as error:
        is_form_content_type(headers)
    assert str(error.value) == "browser form Content-Type is unsupported or ambiguous"
    assert "private-sentinel" not in str(error.value)


@pytest.mark.parametrize("raw,expected", [
    (None, None),
    (b"", {}),
    (b"&&", {}),
    (b"name=sample&category=draft", {"name": "sample", "category": "draft"}),
    (b"blank=&bare&zero=0&false=false&null=null", {
        "blank": "", "bare": "", "zero": "0", "false": "false", "null": "null"}),
    (b"space+key=space+value&plus=%2B&percent=%252F&separators=%26%3D%3B", {
        "space key": "space value", "plus": "+", "percent": "%2F", "separators": "&=;"}),
    (b"caf%C3%A9=%E9%9B%AA", {"caf\u00e9": "\u96ea"}),
    ("caf\u00e9=\u96ea".encode(), {"caf\u00e9": "\u96ea"}),
    (b"record%5Bid%5D=22&record.name=sample", {"record[id]": "22", "record.name": "sample"}),
    (b"value=a=b", {"value": "a=b"}),
])
def test_form_decoding_preserves_actual_flat_strings_and_body_absence(raw, expected):
    assert parse_form_body(raw) == expected
    if expected:
        assert all(type(key) is str and type(value) is str
                   for key, value in parse_form_body(raw).items())


@pytest.mark.parametrize("raw", [
    b"a=1&a=2", b"a=1&%61=2", b"a+b=1&a%20b=2", b"a=1&a=1",
    b"=value", b"=", b"good=value&=other", b"q=%", b"q=%2Z", b"q=%FF",
    b"q=%C3%28", b"q=\xff", b"q=\xc3(", b"%ED%A0%80=bad", b"q=%ED%A0%80",
    "value=string-instead-of-observed-bytes", bytearray(b"a=1"), {"a": "1"}, 0, False,
])
def test_unrepresentable_form_body_fails_without_leaking_input(raw):
    with pytest.raises(ValueError) as error:
        parse_form_body(raw)
    assert str(error.value) == "browser form body is invalid"


def test_decoded_maps_are_fresh_and_do_not_mutate_observed_bytes():
    raw = b"value=private-form-sentinel"
    first = parse_form_body(raw)
    first["value"] = "changed"
    assert parse_form_body(raw) == {"value": "private-form-sentinel"}
    assert raw == b"value=private-form-sentinel"
