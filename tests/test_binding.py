"""Tests for declaration binding and placeholder substitution."""
import pytest

from refracto.declaration.binding import resolve_bindings, substitute
from refracto.declaration.model import Binding, Expect, RequestTemplate, Step
from refracto.ports import NormalizedResponse


def make_norm(fields):
    return NormalizedResponse(succeeded=True, fields=fields, status=200, raw=None)


def make_step(bind):
    return Step(
        id="s",
        request=RequestTemplate(method="GET", path="x/{jobId}"),
        expect=Expect(),
        bind=bind,
    )


def test_resolve_bindings_empty_returns_empty_dict():
    step = make_step([])
    assert resolve_bindings(step, {}) == {}


def test_resolve_bindings_reads_field_from_prior_step():
    step = make_step([Binding(placeholder="jobId", from_step="create_job", field="jobId")])
    prior = {"create_job": make_norm({"jobId": 42})}
    assert resolve_bindings(step, prior) == {"jobId": 42}


def test_resolve_bindings_falsy_zero_is_valid():
    step = make_step([Binding(placeholder="count", from_step="create_job", field="count")])
    prior = {"create_job": make_norm({"count": 0})}
    assert resolve_bindings(step, prior) == {"count": 0}


def test_resolve_bindings_falsy_empty_string_is_valid():
    step = make_step([Binding(placeholder="note", from_step="create_job", field="note")])
    prior = {"create_job": make_norm({"note": ""})}
    assert resolve_bindings(step, prior) == {"note": ""}


def test_resolve_bindings_falsy_false_is_valid():
    step = make_step([Binding(placeholder="flag", from_step="create_job", field="flag")])
    prior = {"create_job": make_norm({"flag": False})}
    assert resolve_bindings(step, prior) == {"flag": False}


def test_resolve_bindings_none_value_raises():
    step = make_step([Binding(placeholder="jobId", from_step="create_job", field="jobId")])
    prior = {"create_job": make_norm({"jobId": None})}
    with pytest.raises(Exception) as exc:
        resolve_bindings(step, prior)
    assert "jobId" in str(exc.value)
    assert "null" in str(exc.value).lower()


def test_resolve_bindings_missing_field_raises():
    step = make_step([Binding(placeholder="jobId", from_step="create_job", field="jobId")])
    prior = {"create_job": make_norm({"other": 1})}
    with pytest.raises(Exception):
        resolve_bindings(step, prior)


def test_resolve_bindings_missing_from_step_raises():
    step = make_step([Binding(placeholder="jobId", from_step="create_job", field="jobId")])
    with pytest.raises(Exception):
        resolve_bindings(step, {})


def test_resolve_bindings_multiple():
    step = make_step([
        Binding(placeholder="jobId", from_step="create_job", field="jobId"),
        Binding(placeholder="ownerId", from_step="create_job", field="ownerId"),
    ])
    prior = {"create_job": make_norm({"jobId": 42, "ownerId": "u1"})}
    assert resolve_bindings(step, prior) == {"jobId": 42, "ownerId": "u1"}


def test_substitute_path_url_encodes_slash():
    template = RequestTemplate(method="GET", path="jobs/{jobId}/result")
    result = substitute(template, {"jobId": "a/b"})
    assert result.path == "jobs/a%2Fb/result"


def test_substitute_path_stringifies_int():
    template = RequestTemplate(method="GET", path="jobs/{jobId}/status")
    result = substitute(template, {"jobId": 42})
    assert result.path == "jobs/42/status"


def test_substitute_path_no_placeholder_unchanged():
    template = RequestTemplate(method="POST", path="jobs")
    result = substitute(template, {})
    assert result.path == "jobs"


def test_substitute_body_whole_placeholder_preserves_int_type():
    template = RequestTemplate(method="POST", path="archives", body={"job": "{jobId}", "note": "archived"})
    result = substitute(template, {"jobId": 42})
    assert result.body == {"job": 42, "note": "archived"}
    assert isinstance(result.body["job"], int)


def test_substitute_body_none_passthrough():
    template = RequestTemplate(method="POST", path="jobs", body=None)
    result = substitute(template, {})
    assert result.body is None


def test_substitute_body_nested_dict_and_list():
    template = RequestTemplate(
        method="POST",
        path="archives",
        body={
            "job": "{jobId}",
            "meta": {"owner": "{ownerId}", "tag": "static"},
            "items": ["{jobId}", "literal", {"nested": "{ownerId}"}],
        },
    )
    result = substitute(template, {"jobId": 42, "ownerId": "u1"})
    assert result.body == {
        "job": 42,
        "meta": {"owner": "u1", "tag": "static"},
        "items": [42, "literal", {"nested": "u1"}],
    }


def test_substitute_method_copied_unchanged():
    template = RequestTemplate(method="POST", path="jobs", body={"a": 1})
    result = substitute(template, {})
    assert result.method == "POST"


def test_substitute_does_not_mutate_input_template():
    original_body = {"job": "{jobId}", "meta": {"owner": "{ownerId}"}}
    template = RequestTemplate(method="POST", path="archives", body=original_body)
    substitute(template, {"jobId": 42, "ownerId": "u1"})
    assert original_body == {"job": "{jobId}", "meta": {"owner": "{ownerId}"}}


def test_substitute_returns_new_request_template_instance():
    template = RequestTemplate(method="GET", path="jobs/{jobId}")
    result = substitute(template, {"jobId": 1})
    assert result is not template
