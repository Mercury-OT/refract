"""Bounded member reads use retained observations, never expected substitutes."""
import copy
from types import MappingProxyType

import pytest

from refracto import ports
from refracto.declaration.binding import DependencyUnavailable, prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document
from refracto.declaration.model import Assertion
from refracto.projection import backend, contract
from refracto.runner import PollConfig
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.test_response_field_comparison import document, request, execute, resolver

SENTINEL = "member-reference-private-sentinel"


def selected(kind="key", *, source="source", field="record", key="id", matching=None):
    ref = {"from_step": source, "response_field": field}
    if kind == "key":
        ref["key"] = key
    elif kind == "list":
        ref.update(matching={"code": "B"} if matching is None else matching, member_field=key)
    return ref


def scenario(ref, *, parameters=None, position="body", extra_steps=()):
    consume = request("consume")
    transport = consume["do"]["request"]
    if position == "body":
        transport["body"] = {"selected": ref}
    elif position == "path":
        transport["path"].append(ref)
    elif position in ("query", "headers"):
        transport[position] = {"x": ref}
    elif position == "assertion":
        consume["expect"]["response"].append({"check": "field_equals", "field": "selected", "value": ref})
    elif position == "fill":
        consume = {"id": "consume", "do": "fill", "target": "entry", "value": ref}
    return _load_document(document(request("source"), consume, *extra_steps, parameters=parameters))


def prepared(ref, data, *, parameters=None, position="body"):
    case = scenario(ref, parameters=parameters, position=position)
    result, bound = prepare_step(case.steps[1], case, {"source": ports.NormalizedResponse(True, data, 200, None)})
    return case, result, bound


@pytest.mark.parametrize("kind", ["key", "list"])
@pytest.mark.parametrize("value", [0, False, "", "text", [], {}, [None, False, 0], {"nested": [1, None]}])
def test_selected_values_preserve_exact_type_and_are_independently_owned(kind, value):
    record = {"code": "B", "id": copy.deepcopy(value)}
    data = {"record": record if kind == "key" else [record]}
    case, step, bound = prepared(selected(kind), data)
    actual = step.request.body["selected"]
    assert type(actual) is type(value) and actual == value
    if isinstance(actual, (dict, list)):
        assert actual is not record["id"]
        actual.clear()
        assert record["id"] == value
    assert len(bound) == 1
    assert case.steps[1].request.body["selected"] != actual


@pytest.mark.parametrize("position", ["path", "body", "query", "headers", "assertion", "fill"])
@pytest.mark.parametrize("kind", ["key", "list"])
def test_existing_value_positions_accept_bounded_references(position, kind):
    record = {"code": "B", "id": "selected"}
    _, step, bound = prepared(selected(kind), {"record": record if kind == "key" else [record]}, position=position)
    assert list(bound.values()) == ["selected"]
    if position == "path":
        assert step.request.path == "consume/selected"


@pytest.mark.parametrize("ref", [
    {"from_step": "source", "response_field": "record", "key": "id", "matching": {"code": "B"}, "member_field": "id"},
    {"from_step": "source", "response_field": "record", "matching": {"code": "B"}},
    {"from_step": "source", "response_field": "record", "member_field": "id"},
    {"from_step": "source", "response_field": "record", "key": "id", "default": 1},
    {"from_parameter": "expected", "key": "id"},
    {"from_step": "source", "result": "record", "key": "id"},
    selected(source="missing"), selected(source="consume"),
])
def test_malformed_shapes_and_sources_are_rejected(ref):
    with pytest.raises(DeclarationError):
        scenario(ref, parameters={"expected": {"id": 1}})


@pytest.mark.parametrize("key", [None, "", " ", 0, False, [], {}, {"from_parameter": "key"}])
@pytest.mark.parametrize("kind", ["key", "list"])
def test_literal_nonblank_selector_names_required(kind, key):
    with pytest.raises(DeclarationError):
        scenario(selected(kind, key=key), parameters={"key": "id"})


@pytest.mark.parametrize("matching", [None, [], {}, {"": "B"}, {1: "B"}, {"code": []},
    {"code": float("nan")}, {"code": selected()}, {"code": selected("list")},
    {"code": {"from_parameter": "complex"}}])
def test_predicates_reject_invalid_scalar_and_recursive_selector_forms(matching):
    ref = selected("list")
    ref["matching"] = matching
    with pytest.raises(DeclarationError):
        scenario(ref, parameters={"complex": []})


@pytest.mark.parametrize("kind,data", [
    ("key", {}), ("key", {"record": None}), ("key", {"record": []}),
    ("key", {"record": {1: "invalid", "id": 1}}), ("key", {"record": {}}),
    ("key", {"record": {"id": None}}),
    ("list", {}), ("list", {"record": {}}), ("list", {"record": []}),
    ("list", {"record": [None, {"code": "B", "id": 1}]}),
    ("list", {"record": [{1: 1}, {"code": "B", "id": 1}]}),
    ("list", {"record": [{"code": "B"}]}),
    ("list", {"record": [{"code": "B", "id": None}]}),
    ("list", {"record": [{"code": "A", "id": 1}]}),
    ("list", {"record": [{"code": "B", "id": 1}, {"code": "B", "id": 1}]}),
])
def test_unavailable_selection_blocks_before_action_and_preserves_independent_continuation(kind, data):
    case = scenario(selected(kind), extra_steps=[request("independent")])
    result, api = execute(case, {"source": data})
    assert [step.status for step in result.steps] == ["PASSED", "BLOCKED", "PASSED"]
    assert [spec.path for spec in api.sent] == ["source", "independent"]
    assert result.steps[1].resolved_bindings == {}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), (), object(), {1: "bad"}, {"nested": float("inf")}])
@pytest.mark.parametrize("kind", ["key", "list"])
def test_invalid_selected_json_like_data_is_unavailable(kind, value):
    data = {"code": "B", "id": value}
    with pytest.raises(DependencyUnavailable):
        prepared(selected(kind), {"record": data if kind == "key" else [data]})


def test_mapping_proxy_is_not_a_normalized_dictionary():
    with pytest.raises(DependencyUnavailable):
        prepared(selected(), {"record": MappingProxyType({"id": 1})})


@pytest.mark.parametrize("kind", ["key", "list"])
def test_cycle_selected_is_rejected_but_unrelated_opaque_data_is_not(kind):
    cycle = []
    cycle.append(cycle)
    member = {"code": "B", "id": cycle}
    with pytest.raises(DependencyUnavailable):
        prepared(selected(kind), {"record": member if kind == "key" else [member]})
    member["id"] = 1
    member["unrelated"] = object()
    assert list(prepared(selected(kind), {"record": member if kind == "key" else [member]})[2].values()) == [1]


@pytest.mark.parametrize("value", [False, "", [], {}, None])
def test_invalid_path_values_never_send_the_consumer(value):
    case = scenario(selected(), position="path")
    result, api = execute(case, {"source": {"record": {"id": value}}})
    assert result.steps[1].status == "BLOCKED"
    assert [spec.path for spec in api.sent] == ["source"]
    assert result.steps[1].resolved_bindings == {}


def test_zero_path_and_literal_punctuation_are_not_interpreted_as_traversal():
    _, step, _ = prepared(selected(key="a.b/c"), {"record": {"a.b/c": 0}}, position="path")
    assert step.request.path == "consume/0"


@pytest.mark.parametrize("predicate", [False, 0, True, 1, 1.0, None, ""])
def test_strict_matching_and_present_null_do_not_alias(predicate):
    options = [False, 0, True, 1, 1.0, None, ""]
    rows = [{"code": value, "id": index} for index, value in enumerate(options)]
    rows.insert(0, {"id": 99})
    expected = next(index for index, value in enumerate(options) if type(value) is type(predicate) and value == predicate)
    _, _, bound = prepared(selected("list", matching={"code": predicate}), {"record": rows})
    assert list(bound.values()) == [expected]


def test_multi_predicates_use_the_same_member_and_actual_parameter_and_response_values():
    ref = selected("list", matching={"code": {"from_parameter": "code"},
                                     "enabled": {"from_step": "source", "response_field": "enabled"}})
    data = {"enabled": False, "record": [{"code": "B", "enabled": 0, "id": 1},
        {"code": "A", "enabled": False, "id": 2}, {"code": "B", "enabled": False, "id": 22}]}
    case, step, bound = prepared(ref, data, parameters={"code": "B"})
    assert step.request.body["selected"] == 22
    assert list(bound.values()) == [False, 22]
    data["enabled"] = []
    with pytest.raises(DependencyUnavailable):
        prepare_step(case.steps[1], case, {"source": ports.NormalizedResponse(True, data, 200, None)})


def test_whole_key_and_strictly_distinct_matching_references_have_distinct_safe_identities():
    refs = [selected("whole"), selected(key="id"), selected(key="code")]
    refs += [selected("list", field="rows", matching={"code": value}) for value in (False, 0, 1, 1.0, SENTINEL)]
    step = request("consume")
    step["do"]["request"]["body"] = {str(index): ref for index, ref in enumerate(refs)}
    case = _load_document(document(request("source"), step))
    assert len({binding.placeholder for binding in case.steps[1].bind}) == len(refs)
    assert SENTINEL not in repr(case.steps[1].bind)
    view = expansion_view(case)["steps"][1]["do"]["request"]["body"]["entries"]
    assert view["0"] == {"kind": "reference", "from_step": "source", "response_field": "record"}
    assert view["1"]["key"] == "id" and view["2"]["key"] == "code"
    assert view["3"]["matching"]["code"]["value"] is False
    assert type(view["4"]["matching"]["code"]["value"]) is int


def test_selectors_in_separate_steps_do_not_alias_review_metadata():
    steps = [request("source")]
    for index, key in enumerate(("id", "code")):
        step = request("consumer" + str(index))
        step["do"]["request"]["path"].append(selected(key=key))
        steps.append(step)
    case = _load_document(document(*steps))
    view = expansion_view(case)
    assert [step["do"]["request"]["path"][1]["key"] for step in view["steps"][1:]] == ["id", "code"]
    assert len({step.bind[0].placeholder for step in case.steps[1:]}) == 2


@pytest.mark.parametrize("kind", ["key", "list"])
def test_response_looking_selected_data_is_not_a_second_declaration(kind):
    value = {"from_step": "never", "response_field": SENTINEL, "key": "no"}
    member = {"code": "B", "id": value}
    _, step, _ = prepared(selected(kind), {"record": member if kind == "key" else [member]})
    assert step.request.body["selected"] == value


def test_failed_source_count_does_not_license_ambiguous_selection():
    case = scenario(selected("list"), extra_steps=[request("independent")])
    case.steps[0].expect.response.append(Assertion(
        "collection_matching_count", {"field": "record", "matching": {"code": "B"}, "count": 1}))
    result, api = execute(case, {"source": {"record": [{"code": "B", "id": 1}, {"code": "B", "id": 2}]}})
    assert [step.status for step in result.steps] == ["FAILED", "BLOCKED", "PASSED"]
    assert [spec.path for spec in api.sent] == ["source", "independent"]


def test_failed_source_assertion_keeps_usable_evidence_and_explicit_stop_still_stops():
    case = scenario(selected())
    case.steps[0].expect.response.append(Assertion("has", {"field": "missing"}))
    result, _ = execute(case, {"source": {"record": {"id": 22}}})
    assert [step.status for step in result.steps] == ["FAILED", "PASSED"]
    case.steps[0].on_failure = "stop"
    result, _ = execute(case, {"source": {"record": {"id": 22}}})
    assert [step.status for step in result.steps] == ["FAILED", "BLOCKED"]


def test_partial_resolutions_not_published_and_blocked_consumer_does_not_authenticate():
    case = scenario(selected(), extra_steps=[request("independent")])
    case.users = ["reader", "other"]
    case.steps[0].user = case.steps[2].user = "reader"
    case.steps[1].user = "other"
    class Auth(FakeAuth):
        def __init__(self):
            self.calls = []
        def session(self, user):
            self.calls.append(user)
            return super().session(user)
    auth = Auth()
    api = FakeApi({("GET", "source"): {"json": {"success": True, "data": {"record": {}}}}})
    result = backend.run(case, api=api, auth=auth, normalizer=FakeNormalizer(), recorder=FakeRecorder(),
                         resolve_request=resolver, state=None)
    assert result.steps[1].status == "BLOCKED" and result.steps[1].resolved_bindings == {}
    assert auth.calls == ["reader"]


def test_sensitive_predicates_and_selected_values_not_in_default_report_or_error():
    case = scenario(selected("list", matching={"code": SENTINEL}), position="path")
    result, _ = execute(case, {"source": {"record": [{"code": SENTINEL, "id": {"secret": SENTINEL}}]}})
    assert result.steps[1].status == "BLOCKED"
    assert SENTINEL not in repr(result)
    assert SENTINEL not in case.steps[1].request.path


@pytest.mark.parametrize("kind,bad", [("key", {}), ("key", []), ("list", []),
    ("list", [{"code": "B", "id": 1}, {"code": "B", "id": 1}])])
def test_contract_rejects_unavailable_actual_selection_even_if_only_used_in_path(kind, bad):
    case = scenario(selected(kind), position="path")
    member = {"code": "B", "id": 22}
    result, _ = execute(case, {"source": {"record": member if kind == "key" else [member]}})
    from tests.fakes import FakeNormalizer
    assert contract.run(case, result.provider_recordings, FakeNormalizer()).passed
    changed = copy.deepcopy(result.provider_recordings)
    changed[0].json["data"]["record"] = bad
    checked = contract.run(case, changed, FakeNormalizer())
    assert not checked.passed and checked.steps[0].status == "ERROR"


def test_final_poll_observation_supplies_selection_not_earlier_attempt():
    case = scenario(selected(), position="path")
    from refracto.declaration.model import Assertion, PollPolicy
    case.steps[0].poll = PollPolicy("FAIL")
    case.steps[0].expect.response.append(Assertion("field_equals", {"field": "ready", "value": True}))
    class ChangingApi(FakeApi):
        def send(self, spec, session):
            if spec.path == "source":
                final = len(self.sent) > 0
                self.responses[("GET", "source")] = {"json": {"success": True, "data": {
                    "ready": final, "record": {"id": 22 if final else 11}}}}
            return super().send(spec, session)
    clock = [0]
    result, api = execute(case, api=ChangingApi(), poll_config=PollConfig(timeout=3, interval=1),
        now=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    assert result.passed
    assert [spec.path for spec in api.sent] == ["source", "source", "consume/22"]
    assert [record.is_final for record in result.provider_recordings if record.step_id == "source"] == [False, True]


def test_separate_runs_never_reuse_a_prior_selected_value():
    case = scenario(selected())
    first, _ = execute(case, {"source": {"record": {"id": 22}}})
    second, api = execute(case, {"source": {"record": {}}})
    assert first.passed and second.steps[1].status == "BLOCKED"
    assert [spec.path for spec in api.sent] == ["source"]


def test_nonscalar_predicate_reports_the_actual_dependency_source():
    ref = selected("list", matching={"code": {"from_step": "predicate", "response_field": "code"}})
    consume = request("consume")
    consume["do"]["request"]["body"] = {"selected": ref}
    case = _load_document(document(request("predicate"), request("source"), consume))
    result, api = execute(case, {"predicate": {"code": []}, "source": {"record": [{"code": "B", "id": 22}]}})
    assert result.steps[-1].status == "BLOCKED"
    assert result.steps[-1].blocked_by == ["predicate"]
    assert result.steps[-1].resolved_bindings == {}
    assert [spec.path for spec in api.sent] == ["predicate", "source"]


@pytest.mark.parametrize("kind", ["key", "list"])
@pytest.mark.parametrize("position,bad", [
    ("path", False), ("path", ""), ("path", []), ("path", {}), ("path", 1.5),
    ("query", []), ("query", {}), ("query", None),
    ("headers", False), ("headers", 22), ("headers", []), ("headers", {}),
    ("headers", " bad"), ("headers", "bad\nvalue"),
    ("scalar_assertion", []), ("scalar_assertion", {}),
    ("header_assertion", False), ("header_assertion", []), ("header_assertion", " bad"),
])
def test_contract_selector_use_sites_follow_runtime_rules(kind, position, bad):
    """Valid later recordings cannot excuse an impossible bound consumer."""
    from refracto.query import wire_query
    ref = selected(kind)
    case = scenario(ref, position=position if position in ("path", "query", "headers") else "body")
    if position == "scalar_assertion":
        case = _load_document(document(request("source"), request("consume", [
            {"check": "collection_matching_count", "field": "rows", "matching": {"code": ref}, "count": 1}])))
    elif position == "header_assertion":
        case = _load_document(document(request("source"), request("consume", [
            {"check": "header_equals", "header": "x", "value": ref}])))

    def transport(template):
        return ports.RequestSpec(template.method, template.path, template.body,
                                 query=wire_query(template.query or {}), headers=dict(template.headers or {}))

    class HeaderApi(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.request_header_items = list(spec.headers.items())
            response.header_items = [("x", "valid")]
            return response

    member = {"code": "B", "id": "valid"}
    data = {"record": member if kind == "key" else [member]}
    responses = {("GET", "source"): {"json": {"success": True, "data": data}},
                 ("GET", "consume"): {"json": {"success": True, "data": {"rows": [{"code": "valid"}]}}}}
    result, _ = execute(case, api=HeaderApi(responses), resolve_request=transport)
    assert result.passed
    assert contract.run(case, result.provider_recordings, FakeNormalizer()).passed

    changed = copy.deepcopy(result.provider_recordings)
    actual_member = changed[0].json["data"]["record"]
    if kind == "list":
        actual_member = actual_member[0]
    actual_member["id"] = bad
    checked = contract.run(case, changed, FakeNormalizer())
    assert not checked.passed and checked.steps[0].status == "ERROR"

    changed_responses = copy.deepcopy(responses)
    changed_responses[("GET", "source")]["json"] = changed[0].json
    rerun, api = execute(case, api=HeaderApi(changed_responses), resolve_request=transport)
    assert rerun.steps[1].status == "BLOCKED"
    assert rerun.steps[1].resolved_bindings == {}
    assert [spec.path for spec in api.sent] == ["source"]
