"""Query declarations, binding ownership, and core evidence boundaries."""
import hashlib
import json
from dataclasses import fields
from types import SimpleNamespace

import pytest
import yaml

from refracto import ports
from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import _values, _references
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.model import RequestTemplate, ValueRef
from refracto.projection import backend, contract, frontend
from refracto.query import parse_query, request_path, require_wire_query, wire_query
from tests.fakes import FakeApi, FakeNormalizer, FakeRecorder, FakeUi


SENTINEL = "private-query-sentinel"


def request(query=None, *, present=True):
    result = {"method": "GET", "path": ["catalog", "search"]}
    if present:
        result["query"] = {} if query is None else query
    return result


def document(query=None, *, location="api", present=True, parameters=None):
    req = request(query, present=present)
    step = {"id": "search", "expect": {"response": [{"check": "success"}]}}
    if location == "api":
        step["do"] = {"request": req}
    else:
        step.update(do="click", target="search")
        step["expect"]["request"] = req
    return {"schema_version": 1, "scenario": "query.search", "users": [],
            "parameters": parameters or {}, "steps": [step]}


def load(tmp_path, raw):
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_scenario(str(path))


def resolver(template):
    return ports.RequestSpec(template.method, template.path, template.body,
                             query=wire_query(template.query or {}))


def run(scenario, *, api=None, recorder=None, normalizer=None, resolve_request=resolver, **kwargs):
    return backend.run(scenario, auth=None, api=api or FakeApi(), state=None,
                       recorder=recorder or FakeRecorder(), resolve_request=resolve_request,
                       normalizer=normalizer or FakeNormalizer(), **kwargs)


@pytest.mark.parametrize("location", ["api", "ui"])
@pytest.mark.parametrize("present,expected", [(False, None), (True, {})])
def test_loader_preserves_query_scope(tmp_path, location, present, expected):
    scenario = load(tmp_path, document(location=location, present=present))
    assert scenario.steps[0].request.query == expected


@pytest.mark.parametrize("location", ["api", "ui"])
def test_scalar_values_and_parameter_references_survive_preparation(tmp_path, location):
    declared = {"empty": "", "zero": 0, "flag": False, "float": 1.25,
                "parameter": {"from_parameter": "term"}, "literal": "{from_step: source}"}
    scenario = load(tmp_path, document(declared, location=location, parameters={"term": "x + &"}))
    prepared, bound = prepare_step(scenario.steps[0], scenario, {})
    assert bound == {}
    assert isinstance(scenario.steps[0].request.query["parameter"], ValueRef)
    assert wire_query(prepared.request.query) == {
        "empty": "", "zero": "0", "flag": "false", "float": "1.25",
        "parameter": "x + &", "literal": "{from_step: source}"}


@pytest.mark.parametrize("query", [None, [], "term", 1, {"": "x"}, {1: "x"},
                                    {"x": None}, {"x": []}, {"x": {}}, {"x": [1]},
                                    {"x": float("nan")}, {"x": float("inf")},
                                    {"x": {"from_parameter": "term", "extra": 1}},
                                    {"x": {"from_input": "term"}}])
@pytest.mark.parametrize("location", ["api", "ui"])
def test_loader_rejects_invalid_query(tmp_path, query, location):
    raw = document(location=location, parameters={"term": "value"})
    req = raw["steps"][0]["do"]["request"] if location == "api" else raw["steps"][0]["expect"]["request"]
    req["query"] = query
    with pytest.raises(DeclarationError):
        load(tmp_path, raw)


@pytest.mark.parametrize("parameter", [None, [], {}, [SENTINEL]])
def test_known_invalid_parameter_is_rejected_while_loading(tmp_path, parameter):
    with pytest.raises(DeclarationError, match="query") as error:
        load(tmp_path, document({"q": {"from_parameter": "term"}}, parameters={"term": parameter}))
    assert SENTINEL not in str(error.value)


@pytest.mark.parametrize("query", [
    "      q: one\n      q: two",
    "      ? {from_parameter: key}\n      : value",
])
def test_duplicate_and_dynamic_query_keys_are_rejected(tmp_path, query):
    path = tmp_path / "scenario.yaml"
    path.write_text("schema_version: 1\nscenario: query.invalid\nusers: []\nsteps:\n"
                    "- id: search\n  do:\n    request:\n      method: GET\n      path: [search]\n"
                    "      query:\n" + "\n".join("  " + line for line in query.splitlines()) +
                    "\n  expect:\n    response: [{check: success}]\n")
    with pytest.raises(DeclarationError):
        load_scenario(str(path))


def test_wire_encoding_roundtrip_and_wire_equivalence():
    raw = {"\u96ea +&=%/": "Unicode \u96ea + & = % /", "blank": "", "zero": 0,
           "false": False, "float": -0.0, "scientific": 1e20}
    path = request_path("/catalog/search", raw)
    assert path.startswith("/catalog/search?")
    assert parse_query(path.partition("?")[2]) == wire_query(raw)
    assert wire_query({"n": 1}) == wire_query({"n": "1"})
    assert wire_query({"n": 1.0}) == {"n": "1.0"}
    assert parse_query("b=two+words&a=%2B%26%3D%25%2F&empty&blank=") == {
        "a": "+&=%/", "b": "two words", "empty": "", "blank": ""}
    assert parse_query("") == {}
    assert request_path("/catalog/search", {}) == "/catalog/search"


@pytest.mark.parametrize("raw", ["x=%", "x=%1", "x=%GG", "x=%FF", "x=%C3%28",
                                  "x=1&x=2", "x=1&%78=2", "x+y=1&x%20y=2", "=value"])
def test_observed_query_rejects_malformed_and_duplicate_values(raw):
    with pytest.raises(ValueError):
        parse_query(raw)


@pytest.mark.parametrize("path", ["/search?x=1", "/search#fragment"])
def test_path_cannot_hide_query_or_fragment(path):
    with pytest.raises(ValueError, match="embedded query or fragment"):
        request_path(path, {})


def with_source(raw):
    raw["steps"].insert(0, {"id": "source", "do": {"request": {"method": "POST", "path": ["source"]}},
                             "expect": {"response": [{"check": "success"}]}})
    return raw


@pytest.mark.parametrize("fields", [{}, {"cursor": None}, {"cursor": []}, {"cursor": {}},
                                   {"cursor": float("nan")}, {"cursor": [SENTINEL]}])
def test_unavailable_query_dependency_blocks_atomically_and_continues(tmp_path, fields):
    raw = with_source(document({"cursor": {"from_step": "source", "response_field": "cursor"},
                                "valid": {"from_step": "source", "response_field": "valid"}}))
    raw["steps"].append({"id": "independent", "do": {"request": {"method": "GET", "path": ["independent"]}},
                         "expect": {"response": [{"check": "success"}]}})
    scenario = load(tmp_path, raw)
    api = FakeApi({("POST", "source"): {"json": {"success": True, "data": {"valid": 0, **fields}}}})
    result = run(scenario, api=api)
    assert [step.status for step in result.steps] == ["PASSED", "BLOCKED", "PASSED"]
    assert result.steps[1].resolved_bindings == {}
    assert len(api.sent) == 2
    assert SENTINEL not in result.steps[1].detail


def test_query_only_response_binding_contract_and_recordings(tmp_path):
    scenario = load(tmp_path, with_source(document({
        "cursor": {"from_step": "source", "response_field": "cursor"},
        "blank": {"from_step": "source", "response_field": "blank"},
        "flag": {"from_step": "source", "response_field": "flag"}})))
    api = FakeApi({("POST", "source"): {"json": {"success": True, "data": {
        "cursor": 0, "blank": "", "flag": False}}}})
    result = run(scenario, api=api)
    assert [step.status for step in result.steps] == ["PASSED", "PASSED"]
    assert result.provider_recordings[1].request.query == {"cursor": "0", "blank": "", "flag": "false"}
    checked = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert checked.steps[0].status == "PASSED"
    assert len(api.sent) == 2


def test_include_query_parameters_results_and_expanded_review(tmp_path):
    child = document({"cursor": {"from_parameter": "cursor"}}, parameters={"cursor": 0})
    child["scenario"] = "query.child"
    child["results"] = {"next": {"from_step": "search", "response_field": "next_cursor"}}
    child_path = tmp_path / "child.yaml"
    child_path.write_text(yaml.safe_dump(child), encoding="utf-8")
    raw = with_source(document({"cursor": {"from_step": "included", "result": "next"}}))
    raw["steps"].insert(1, {"id": "included", "do": {"include": "query.child"},
                              "with": {"cursor": {"from_step": "source", "response_field": "cursor"}}})
    (tmp_path / "scenario.includes.json").write_text(json.dumps({"manifest_version": 1, "scenarios": {
        "query.child": {"path": "child.yaml", "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}))
    scenario = load(tmp_path, raw)
    assert [step.id for step in scenario.steps] == ["source", "included/search", "search"]
    prior = {"source": ports.NormalizedResponse(True, {"cursor": 0}, 200, None),
             "included/search": ports.NormalizedResponse(True, {"next_cursor": 1}, 200, None)}
    assert prepare_step(scenario.steps[1], scenario, prior)[0].request.query == {"cursor": 0}
    assert prepare_step(scenario.steps[2], scenario, prior)[0].request.query == {"cursor": 1}
    view = expansion_view(scenario)
    source = view["steps"][2]["do"]["request"]["query"]["entries"]["cursor"]
    assert source == {"kind": "reference", "from_step": "included/search", "response_field": "next_cursor"}
    positions = list(_values(raw["steps"][2], 2))
    refs = [ref for location, value in positions for ref in _references(value, location)]
    assert refs == [("included", "next", "/steps/2/do/request/query/cursor")]
    raw["steps"][1]["with"]["cursor"] = [SENTINEL]
    with pytest.raises(DeclarationError, match="instantiated query") as error:
        load(tmp_path, raw)
    assert SENTINEL not in str(error.value)


@pytest.mark.parametrize("change", ["drop", "add", "alter", "embedded", "fragment", "typed"])
def test_resolver_cannot_change_query_or_embed_it_in_path(tmp_path, change):
    scenario = load(tmp_path, document({"q": SENTINEL}))
    api = FakeApi()
    def bad_resolver(*args):
        spec = resolver(*args)
        if change == "drop":
            spec.query = {}
        elif change == "add":
            spec.query["extra"] = "1"
        elif change == "alter":
            spec.query["q"] = "other"
        elif change == "typed":
            spec.query["q"] = 1
        else:
            spec.path += "?q=" + SENTINEL if change == "embedded" else "#" + SENTINEL
        return spec
    result = run(scenario, api=api, resolve_request=bad_resolver)
    assert result.steps[0].status == "ERROR"
    assert api.sent == []
    assert SENTINEL not in result.steps[0].detail


@pytest.mark.parametrize("mutation", ["driver", "recorder", "normalizer"])
def test_query_evidence_cannot_be_rewritten(tmp_path, mutation):
    scenario = load(tmp_path, document({"q": SENTINEL}))
    class MutatingApi(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            if mutation == "driver":
                spec.query["q"] = "forged"
            return response
    class MutatingRecorder(FakeRecorder):
        def record(self, response):
            if mutation == "recorder":
                response.request.query["q"] = "forged"
            super().record(response)
    class MutatingNormalizer(FakeNormalizer):
        def normalize(self, response):
            if mutation == "normalizer":
                response.request.query["q"] = "forged"
            return super().normalize(response)
    result = run(scenario, api=MutatingApi(), recorder=MutatingRecorder(), normalizer=MutatingNormalizer())
    assert result.steps[0].status == "ERROR"
    assert SENTINEL not in result.steps[0].detail


def test_each_poll_attempt_records_prepared_query(tmp_path):
    raw = document({"q": SENTINEL, "cursor": 0})
    raw["steps"][0]["poll"] = {"on_timeout": "FAIL"}
    raw["steps"][0]["expect"]["response"] = [{"check": "has", "field": "ready"}]
    scenario = load(tmp_path, raw)
    class PollApi(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.json = {"success": True, "data": {"ready": True} if len(self.sent) > 1 else {}}
            return response
    api = PollApi()
    clock = SimpleNamespace(time=0)
    def sleep(seconds):
        clock.time += seconds
    result = run(scenario, api=api, poll_config=SimpleNamespace(timeout=2, interval=1),
                 now=lambda: clock.time, sleep=sleep)
    assert result.steps[0].status == "PASSED"
    assert len(result.provider_recordings) == 2
    assert [r.request.query for r in result.provider_recordings] == [{"q": SENTINEL, "cursor": "0"}] * 2
    assert api.sent[0].query is not api.sent[1].query
    assert len({r.request.traceparent for r in result.provider_recordings}) == 2


@pytest.mark.parametrize("declared,actual,status", [
    ({"q": 1}, {"q": "1"}, "PASSED"),
    ({"q": "wanted"}, {"q": "wrong"}, "FAILED"),
    ({"q": "wanted"}, {}, "FAILED"),
    ({"q": "wanted"}, {"q": "wanted", "extra": "1"}, "FAILED"),
    ({}, {"q": "extra"}, "FAILED"), ({}, {}, "PASSED"),
    (None, {"q": "unconstrained"}, "PASSED"),
])
def test_single_ui_request_query_scope(tmp_path, declared, actual, status):
    scenario = load(tmp_path, document(declared, location="ui", present=declared is not None))
    ui = FakeUi(outgoing=[ports.RequestSpec("GET", "catalog/search", query=actual)])
    fixture = ports.MockResponse(fixture_id="one", source="test", method="GET", path="catalog/search",
                                  response={"success": True})
    result = frontend.run(scenario, ui=ui, normalizer=FakeNormalizer(), mock_plan=[fixture])
    assert result.steps[0].status == status
    assert result.steps[0].checks[0].point == "request"


@pytest.mark.parametrize("queries,status", [
    ([{"q": "other"}, {"q": "wanted"}], "PASSED"),
    ([{"q": "other"}, {}], "ERROR"),
    ([{"q": "wanted"}, {"q": "wanted"}], "ERROR"),
])
def test_declared_query_selects_exactly_one_of_multiple_associated_requests(tmp_path, queries, status):
    scenario = load(tmp_path, document({"q": "wanted"}, location="ui"))
    ui = FakeUi(outgoing=[ports.RequestSpec("GET", "catalog/search", query=q) for q in queries])
    fixtures = [ports.MockResponse(fixture_id=str(i), source="test", method="GET", path="catalog/search",
                                  response={"success": True}) for i in range(len(queries))]
    result = frontend.run(scenario, ui=ui, normalizer=FakeNormalizer(), mock_plan=fixtures)
    assert result.steps[0].status == status
    assert len(result.mock_consumption) == len(queries)


def test_mock_fixture_query_is_checked_independently_of_declaration(tmp_path):
    scenario = load(tmp_path, document(location="ui", present=False))
    ui = FakeUi(outgoing=[ports.RequestSpec("GET", "catalog/search", query={"q": SENTINEL})])
    fixture = ports.MockResponse(fixture_id="one", source="test", method="GET", path="catalog/search",
                                  response={"success": True}, query={"q": "wrong"})
    result = frontend.run(scenario, ui=ui, normalizer=FakeNormalizer(), mock_plan=[fixture])
    assert result.steps[0].status == "ERROR"
    assert "fixture query" in result.steps[0].detail
    assert SENTINEL not in repr(result)


def test_query_models_hide_values_and_independent_defaults():
    for model in (RequestTemplate("GET", "search", query={"q": SENTINEL}),
                  ports.RequestSpec("GET", "search", query={"q": SENTINEL}),
                  ports.MockResponse(fixture_id="one", source="test", method="GET", path="search",
                                     response={}, query={"q": SENTINEL})):
        assert SENTINEL not in repr(model)
        query_field = next(field for field in fields(model) if field.name == "query")
        assert query_field.kw_only and query_field.metadata["sensitive"] and not query_field.repr
    first, second = ports.RequestSpec("GET", "search"), ports.RequestSpec("GET", "search")
    first.query["q"] = SENTINEL
    assert second.query == {}
    with pytest.raises(ValueError):
        require_wire_query({"q": 1})
