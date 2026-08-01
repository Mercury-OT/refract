from refracto.declaration import vocabulary as v


def test_observation_points():
    assert v.OBSERVATION_POINTS == ("frontend", "request", "response", "backend_state")


def test_valid_terms_per_point():
    assert v.is_valid("response", "success")
    assert v.is_valid("response", "has")
    assert v.is_valid("request", "request")
    assert v.is_valid("backend_state", "span_exists")
    assert v.is_valid("backend_state", "span_attr")
    assert v.is_valid("frontend", "visible")
    assert v.is_valid("frontend", "count_gt")


def test_term_wrong_point_is_invalid():
    assert not v.is_valid("response", "span_attr")
    assert not v.is_valid("frontend", "success")


def test_unknown_term_invalid():
    assert not v.is_valid("response", "nonsense")
