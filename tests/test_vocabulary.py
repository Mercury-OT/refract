from refracto.declaration import vocabulary as v


def test_observation_points():
    assert v.OBSERVATION_POINTS == ("frontend", "request", "response", "backend_state")


def test_valid_terms_per_point():
    assert v.is_valid("response", "success")
    assert v.is_valid("response", "has")
    assert v.is_valid("response", "field_equals")
    assert v.is_valid("request", "request")
    assert v.is_valid("backend_state", "span_exists")
    assert v.is_valid("backend_state", "span_attr")
    assert v.is_valid("frontend", "visible")
    assert v.is_valid("frontend", "count_gt")
    assert v.is_valid("frontend", "object_field_equals")
    assert v.is_valid("frontend", "no_anonymous")


def test_term_wrong_point_is_invalid():
    assert not v.is_valid("response", "span_attr")
    assert not v.is_valid("frontend", "success")


def test_unknown_term_invalid():
    assert not v.is_valid("response", "nonsense")


def test_field_equals_has_a_bounded_shape():
    assert v.required_params("response", "field_equals") == ("field", "value")
    assert v.VALUE_REF_SOURCES == {
        "from_bind": "bind",
        "from_input": "input",
    }


def test_frontend_identity_terms_have_bounded_shapes():
    assert v.required_params("frontend", "object_field_equals") == (
        "anchor", "id", "field", "value",
    )
    assert v.required_params("frontend", "no_anonymous") == ("anchor",)
