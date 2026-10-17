"""Business headers are declared strings; observations are complete raw blocks."""
import copy
import dataclasses
from types import SimpleNamespace

import pytest

from refracto import headers, ports
from refracto.contract import store
from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import _references, _values
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.model import Assertion, RequestTemplate
from refracto.normalization import normalize_response
from refracto.projection import backend, contract
from refracto.report import RunReport
from tests.fakes import FakeApi, FakeNormalizer, FakeRecorder
from tests.test_scenario_include import write_bundle
from tests.ui_support import ScriptedUi, run as run_ui

SENTINEL = "sensitive-business-header-sentinel"
UNSET = object()


def request(sid="read", business=UNSET, checks=None, *, ui=False):
    declaration = {"method": "GET", "path": [sid]}
    if business is not UNSET:
        declaration["headers"] = business
    step = {"id": sid, "expect": {"response": [{"check": "success"}] if checks is None else checks}}
    if ui:
        step.update(do="click", target="load")
        step["expect"]["request"] = declaration
    else:
        step["do"] = {"request": declaration}
    return step


def equals(value="no-store", name="Cache-Control"):
    return {"check": "header_equals", "header": name, "value": value}


def absent(name="X-Internal-Debug"):
    return {"check": "header_absent", "header": name}


def document(steps=None, parameters=None):
    return {"schema_version": 1, "scenario": "headers.example", "users": [],
            "parameters": parameters or {}, "steps": steps or [request()]}


def load(*steps, parameters=None):
    return _load_document(document(list(steps), parameters))


def resolver(scenario, step, template):
    return ports.RequestSpec(template.method, template.path, template.body,
                             headers=copy.deepcopy(template.headers or {}))


class ObservedApi(FakeApi):
    def __init__(self, request_items=None, response_items=None, *, payloads=None):
        super().__init__()
        # Explicit fixtures are independent of the caller's expected headers.
        self.request_items = request_items
        self.response_items = response_items
        self.payloads = payloads or {}

    def send(self, spec, session):
        response = super().send(spec, session)
        response.request_header_items = copy.deepcopy(self.request_items)
        response.header_items = copy.deepcopy(self.response_items)
        if spec.path in self.payloads:
            response.json = {"success": True, "data": copy.deepcopy(self.payloads[spec.path])}
        return response


def execute(scenario, *, api=None, mode="backend", normalizer=None, recorder=None,
            resolve_request=resolver, **kwargs):
    api = api or ObservedApi()
    options = dict(api=api, normalizer=normalizer or FakeNormalizer(),
                   recorder=recorder or FakeRecorder(), resolve_request=resolve_request, **kwargs)
    if mode == "e2e":
        return run_ui(scenario, None, auth=None, **options)
    return backend.run(scenario, auth=None, state=None, **options)


@pytest.mark.parametrize("ui", [False, True])
@pytest.mark.parametrize("mapping", [{}, {"Idempotency-Key": ""}, {"X-Key": "a b"},
    {"X-Key": {"from_parameter": "key"}}])
def test_literal_empty_and_parameter_headers_at_both_locations(ui, mapping):
    scenario = load(request(business=mapping, ui=ui), parameters={"key": SENTINEL})
    prepared, bound = prepare_step(scenario.steps[0], scenario, {})
    assert bound == {}
    assert prepared.request.headers == ({"X-Key": SENTINEL} if "from_parameter" in str(mapping) else mapping)
    assert load(request(ui=ui)).steps[0].request.headers is None


@pytest.mark.parametrize("ui", [False, True])
@pytest.mark.parametrize("mapping", [None, [], 3, "x", {"": "x"}, {"X Key": "x"},
    {"X:Key": "x"}, {"\u96ea": "x"}, {"X-Key\r\n": "x"}, {"X-Key": "x", "x-key": "x"},
    {"X-Key": None}, {"X-Key": True}, {"X-Key": 1}, {"X-Key": 1.0}, {"X-Key": []},
    {"X-Key": {}}, {"X-Key": " a"}, {"X-Key": "a "}, {"X-Key": "a\tb"},
    {"X-Key": "a\rb"}, {"X-Key": "a\nb"}, {"X-Key": "a\x00b"}, {"X-Key": "\u96ea"},
    {"X-Key": "a\x7fb"}, {"X-Key": {"from_parameter": "missing"}},
    {"X-Key": {"from_parameter": "key", "extra": "x"}},
    {"X-Key": {"from_input": "key"}}])
def test_invalid_header_maps_are_rejected_without_values(ui, mapping):
    with pytest.raises(DeclarationError) as error:
        load(request(business=mapping, ui=ui), parameters={"key": SENTINEL})
    assert SENTINEL not in str(error.value)


@pytest.mark.parametrize("name", ["Authorization", "Proxy-Authorization", "Cookie", "Set-Cookie",
    "Host", "Content-Length", "Content-Type", "Transfer-Encoding", "Connection", "TE", "Trailer",
    "Upgrade", "Expect", "Accept-Encoding", "Origin", "Referer", "User-Agent", "Traceparent",
    "Tracestate", "proxy-custom", "Sec-Fetch-Site", "x-refract-custom"])
@pytest.mark.parametrize("ui", [False, True])
def test_credentials_transport_and_reserved_prefixes_rejected(name, ui):
    with pytest.raises(DeclarationError):
        load(request(business={name.swapcase(): SENTINEL}, ui=ui))


@pytest.mark.parametrize("value", [None, True, False, 0, 1.0, [], {}, " padded", "padded ", "a\nb", "\u96ea"])
def test_known_parameter_and_response_assertion_values_must_be_strings(value):
    for step in (request(business={"X-Key": {"from_parameter": "key"}}),
                 request(checks=[equals({"from_parameter": "key"})]), request(checks=[equals(value)])):
        with pytest.raises(DeclarationError):
            load(step, parameters={"key": value})


@pytest.mark.parametrize("checks", [[equals(), equals(name="cache-control")],
    [equals(), absent("CACHE-CONTROL")], [absent(), absent("x-internal-debug")],
    [{"check": "header_equals", "header": "X-Key"}],
    [{"check": "header_equals", "header": "X-Key", "value": "", "extra": 1}],
    [{"check": "header_absent", "header": "X-Key", "value": ""}],
    [absent("bad name")], [absent({"from_parameter": "key"})]])
def test_response_header_constraint_shape_is_strict(checks):
    with pytest.raises(DeclarationError):
        load(request(checks=checks), parameters={"key": "x"})


@pytest.mark.parametrize("items,status", [
    ([("IDEMPOTENCY-KEY", SENTINEL), ("User-Agent", "browser")], "PASSED"),
    ([("Idempotency-Key", "wrong")], "FAILED"), ([], "FAILED"),
    (None, "ERROR"), ({"Idempotency-Key": SENTINEL}, "ERROR"),
    ([("Idempotency-Key", SENTINEL), ("idempotency-key", SENTINEL)], "ERROR"),
    ([("Idempotency-Key", SENTINEL), ("bad name", "x")], "ERROR"),
    ([("Idempotency-Key", SENTINEL), ("Other", 1)], "ERROR"),
])
@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_actual_request_headers_control_result_and_continuation(items, status, mode):
    scenario = load(request(business={"Idempotency-Key": SENTINEL}), request("later"))
    api = ObservedApi(items, [])
    result = execute(scenario, api=api, mode=mode)
    assert [step.status for step in result.steps] == [status, "BLOCKED" if status == "ERROR" else "PASSED"]
    assert len(result.provider_recordings) == (1 if status == "ERROR" else 2)
    assert SENTINEL not in repr(result) + result.steps[0].detail


@pytest.mark.parametrize("checks,items,status", [
    ([equals()], [("CACHE-CONTROL", "no-store")], "PASSED"),
    ([equals()], [("Cache-Control", "No-Store")], "FAILED"),
    ([equals()], [("Cache-Control", "no-store ")], "FAILED"),
    ([equals()], [], "FAILED"), ([equals("")], [("Cache-Control", "")], "PASSED"),
    ([absent()], [], "PASSED"), ([absent()], [("X-Internal-Debug", "")], "FAILED"),
    ([absent()], None, "ERROR"), ([equals()], None, "ERROR"),
    ([absent()], {"Cache-Control": "no-store"}, "ERROR"),
    ([absent()], [("X-Internal-Debug", ""), ("x-internal-debug", "")], "ERROR"),
    ([equals()], [("Cache-Control", "no-store"), ("cache-control", "no-store")], "ERROR"),
    ([equals()], [("Cache-Control", "no-store"), ("Set-Cookie", "a"), ("Set-Cookie", "b")], "PASSED"),
])
@pytest.mark.parametrize("mode", ["backend", "e2e", "contract"])
def test_response_complete_pair_semantics_all_consumers(checks, items, status, mode):
    scenario = load(request(checks=checks))
    api = ObservedApi([], items)
    result = execute(scenario, api=api, mode="backend" if mode == "contract" else mode)
    if mode == "contract":
        result = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert result.steps[0].status == status


@pytest.mark.parametrize("field", ["request_header_items", "header_items", "headers"])
@pytest.mark.parametrize("seam", ["normalizer", "raw_alias", "recorder"])
def test_sensitive_header_evidence_cannot_be_rewritten(field, seam):
    scenario = load(request(business={"X-Key": SENTINEL}, checks=[equals()]))
    def mutate(response):
        if field == "headers":
            response.request.headers["X-Key"] = "forged"
        else:
            setattr(response, field, [("X-Key", "forged")])
    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            norm = super().normalize(response)
            if seam == "normalizer":
                mutate(response)
            elif seam == "raw_alias":
                norm.raw = copy.deepcopy(response)
                mutate(norm.raw)
            return norm
    class Recorder(FakeRecorder):
        def record(self, response):
            if seam == "recorder":
                mutate(response)
            return super().record(response)
    result = execute(scenario, api=ObservedApi([("X-Key", SENTINEL)], [("Cache-Control", "no-store")]),
                     normalizer=Normalizer(), recorder=Recorder())
    assert result.steps[0].status == "ERROR"
    assert SENTINEL not in repr(result) + result.steps[0].detail


@pytest.mark.parametrize("seam", ["drop", "add", "alter", "driver"])
def test_request_map_ownership_is_protected(seam):
    scenario = load(request(business={"X-Key": SENTINEL}))
    class Api(ObservedApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            if seam == "driver":
                response.request.headers.clear()
            return response
    api = Api([("X-Key", SENTINEL)], [])
    def resolve(*args):
        spec = resolver(*args)
        if seam == "drop":
            spec.headers.clear()
        elif seam == "add":
            spec.headers["X-Other"] = "value"
        elif seam == "alter":
            spec.headers["X-Key"] = "wrong"
        return spec
    result = execute(scenario, api=api, resolve_request=resolve)
    assert result.steps[0].status == "ERROR"
    assert len(api.sent) == (1 if seam == "driver" else 0)
    assert SENTINEL not in repr(result) + result.steps[0].detail


def test_resolver_case_changes_preserve_business_map_and_empty_values():
    scenario = load(request(business={"X-Key": ""}))
    result = execute(scenario, api=ObservedApi([("X-KEY", "")], []),
        resolve_request=lambda s, st, t: ports.RequestSpec(t.method, t.path, headers={"x-key": ""}))
    assert result.status == "PASSED"


def test_rawless_normalizer_uses_actual_captured_headers():
    class NoRaw(FakeNormalizer):
        def normalize(self, response):
            return dataclasses.replace(super().normalize(response), raw=None)
    result = execute(load(request(checks=[equals()])), normalizer=NoRaw(),
                     api=ObservedApi([], [("Cache-Control", "no-store")]))
    assert result.status == "PASSED"


@pytest.mark.parametrize("value", [None, True, 42, [], {}, " padded", "a\nb", "\u96ea", UNSET])
@pytest.mark.parametrize("use", ["request", "response"])
def test_runtime_invalid_values_block_consumer_atomically(value, use):
    reference = {"from_step": "source", "response_field": "key"}
    consumer = request(business={"X-Key": reference}) if use == "request" else request(checks=[equals(reference)])
    consumer["do"]["request"]["body"] = {"known": {"from_step": "source", "response_field": "known"}}
    scenario = load(request("source"), consumer, request("later"))
    payload = {"known": "ok", **({} if value is UNSET else {"key": value})}
    api = ObservedApi([], [], payloads={"source": payload})
    result = execute(scenario, api=api)
    assert [step.status for step in result.steps] == ["PASSED", "BLOCKED", "PASSED"]
    assert result.steps[1].resolved_bindings == {}
    assert [item.path for item in api.sent] == ["source", "later"]


def test_parameter_and_response_references_in_contract_are_not_header_references():
    ref = {"from_step": "source", "response_field": "cache"}
    scenario = load(request("source"), request(checks=[equals(ref)]))
    api = ObservedApi([], [("Cache-Control", SENTINEL)], payloads={"source": {"cache": SENTINEL}})
    result = execute(scenario, api=api)
    assert result.status == "PASSED"
    checked = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert checked.status == "PASSED"
    consumer = store.consumer_contract(scenario)
    provider = store.provider_contract(result.provider_recordings, FakeNormalizer())
    assert ("read", "GET", "read") in consumer.entries
    assert SENTINEL not in repr(consumer)
    # Provider JSON fields retain their existing contract; the raw header block is hidden.
    assert SENTINEL not in repr(provider.entries[("read", "GET", "read")])
    parameter = load(request(checks=[equals({"from_parameter": "cache"})]), parameters={"cache": SENTINEL})
    result = execute(parameter, api=ObservedApi([], [("Cache-Control", SENTINEL)]))
    assert contract.run(parameter, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"


def test_include_rewriting_named_results_expansion_and_impact(tmp_path):
    child = document([request(business={"X-Key": {"from_parameter": "key"}},
                              checks=[equals({"from_parameter": "key"})])], {"key": "default"})
    child["scenario"] = "shared.headers"
    child["results"] = {"next": {"from_step": "read", "response_field": "next"}}
    root = document([request("source"), {"id": "setup", "do": {"include": "shared.headers"},
        "with": {"key": {"from_step": "source", "response_field": "key"}}},
        request("after", business={"X-Key": {"from_step": "setup", "result": "next"}})])
    path, _ = write_bundle(tmp_path, root, child)
    scenario = load_scenario(path)
    prior = {"source": ports.NormalizedResponse(True, {"key": "one"}, 200, None),
             "setup/read": ports.NormalizedResponse(True, {"next": "two"}, 200, None)}
    assert prepare_step(scenario.steps[1], scenario, prior)[0].request.headers == {"X-Key": "one"}
    assert prepare_step(scenario.steps[1], scenario, prior)[0].expect.response[0].params["value"] == "one"
    assert prepare_step(scenario.steps[2], scenario, prior)[0].request.headers == {"X-Key": "two"}
    viewed = expansion_view(scenario)["steps"][2]["do"]["request"]["headers"]["entries"]["X-Key"]
    assert viewed == {"kind": "reference", "from_step": "setup/read", "response_field": "next"}
    positions = list(_values(root["steps"][2], 2))
    assert [ref for location, value in positions for ref in _references(value, location)] == [
        ("setup", "next", "/steps/2/do/request/headers/X-Key")]
    root["steps"][1]["with"]["key"] = 42
    path, _ = write_bundle(tmp_path, root, child)
    with pytest.raises(DeclarationError, match="instantiated header"):
        load_scenario(path)


@pytest.mark.parametrize("wrong_first", [False, True])
def test_poll_checks_every_actual_attempt_and_keeps_prepared_headers(wrong_first):
    step = request(business={"X-Key": SENTINEL}, checks=[equals()])
    step["poll"] = {"on_timeout": "FAIL"}
    class PollApi(ObservedApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.header_items = [("Cache-Control", "pending" if len(self.sent) == 1 else "no-store")]
            if len(self.sent) == 1 and wrong_first:
                response.request_header_items = []
            return response
    api = PollApi([("X-Key", SENTINEL)], [])
    clock = SimpleNamespace(time=0)
    def sleep(seconds):
        clock.time += seconds
    result = execute(load(step), api=api, poll_config=SimpleNamespace(timeout=2, interval=1),
                     now=lambda: clock.time, sleep=sleep)
    assert result.status == ("FAILED" if wrong_first else "PASSED")
    assert len(result.provider_recordings) == 2
    assert [r.request.headers for r in result.provider_recordings] == [{"X-Key": SENTINEL}] * 2
    assert api.sent[0].headers is not api.sent[1].headers
    assert [c.ok for c in result.checks if c.point == "request"] == [not wrong_first, True]


def test_default_representations_and_metadata_hide_all_header_values():
    spec = ports.RequestSpec("GET", "items", headers={"X-Key": SENTINEL})
    response = ports.RecordedResponse(200, {"Set-Cookie": SENTINEL}, {}, "", None, spec,
        request_header_items=[("Cookie", SENTINEL)], header_items=[("X-Key", SENTINEL)])
    fixture = ports.MockResponse(fixture_id="one", source="test", method="GET", path="items", response={},
                                 request_headers={"X-Key": SENTINEL}, response_headers={"X-Key": SENTINEL})
    template = RequestTemplate("GET", "items", headers={"X-Key": SENTINEL})
    assertion = Assertion("header_equals", {"header": "X-Key", "value": SENTINEL})
    for item in (spec, response, fixture, template, assertion):
        assert SENTINEL not in repr(item)
    for cls, names in ((ports.RequestSpec, ["headers"]), (ports.RecordedResponse,
            ["headers", "header_items", "request_header_items"]), (RequestTemplate, ["headers"]),
            (ports.MockResponse, ["request_headers", "response_headers"])):
        fields = {field.name: field for field in dataclasses.fields(cls)}
        assert all(fields[name].repr is False and fields[name].metadata["sensitive"] for name in names)
    assert ports.RequestSpec("GET", "a").headers is not ports.RequestSpec("GET", "b").headers


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("items,status", [([("X-Key", SENTINEL), ("Other", "extra")], "PASSED"),
    ([], "FAILED"), ([("X-Key", "wrong")], "FAILED"), (None, "ERROR"),
    ([("X-Key", SENTINEL), ("x-key", SENTINEL)], "ERROR")])
def test_ui_core_uses_raw_headers_for_selected_request(mode, items, status):
    scenario = load(request(business={"X-Key": SENTINEL}, checks=[equals()], ui=True))
    def mutate(index, result, permit):
        for response in [t.response for t in result.evidence.traffic] + result.evidence.mock_recordings:
            response.request_header_items = copy.deepcopy(items)
            response.header_items = [("Cache-Control", "no-store")]
        return result
    ui = ScriptedUi(count=1, requests=[[ports.RequestSpec("GET", "read")]], mutate=mutate)
    result = run_ui(scenario, ui, mode=mode, auth=None)
    assert result.steps[0].status == status
    assert SENTINEL not in repr(result) + result.steps[0].detail


@pytest.mark.parametrize("observed,status", [
    ([[('X-Key', 'other')], [('X-Key', SENTINEL)]], "PASSED"),
    ([[], [('X-Key', 'other')]], "ERROR"),
    ([[('X-Key', SENTINEL)], [('x-key', SENTINEL)]], "ERROR"),
    ([None, [('X-Key', SENTINEL)]], "ERROR"),
])
def test_multiple_associated_requests_use_declared_header_subset(observed, status):
    scenario = load(request(business={"X-Key": SENTINEL}, ui=True))
    def mutate(index, result, permit):
        for traffic, block in zip(result.evidence.traffic, observed):
            traffic.response.request_header_items = block
        return result
    ui = ScriptedUi(count=1, requests=[[ports.RequestSpec("GET", "read") for _ in observed]], mutate=mutate)
    assert run_ui(scenario, ui, auth=None).steps[0].status == status


@pytest.mark.parametrize("fixture_side", ["request_headers", "response_headers"])
def test_mock_fixture_checks_detect_header_tampering_without_declared_headers(fixture_side):
    scenario = load(request(ui=True))
    def mutate(index, result, permit):
        for response in [t.response for t in result.evidence.traffic] + result.evidence.mock_recordings:
            response.request_header_items = [("X-Key", "wrong")]
            response.header_items = [("X-Key", "wrong")]
        return result
    ui = ScriptedUi(count=1, requests=[[ports.RequestSpec("GET", "read")]], mutate=mutate)
    plan = [dataclasses.replace(ui.plan()[0], **{fixture_side: {"X-Key": SENTINEL}})]
    result = run_ui(scenario, ui, mode="mock", auth=None, mock_plan=plan)
    assert result.steps[0].status == "ERROR"
    assert SENTINEL not in repr(result) + result.steps[0].detail


@pytest.mark.parametrize("value", ["\x00", "\x01", "\x08", "\x0b", "\x1f", "\x7f", "\u96ea"])
def test_malformed_unrelated_headers_cannot_prove_absence(value):
    with pytest.raises(ValueError, match="malformed"):
        headers.evaluate("header_absent", "X-Internal-Debug", None, [("Unrelated", value)])


def test_observed_ows_and_obstext_are_not_trimmed_or_normalized():
    assert headers.evaluate("header_absent", "X-Internal-Debug", None,
                            [("Unrelated", "\t value \t\xff")]) == (True, "")
    assert not headers.evaluate("header_equals", "X-Key", "value", [("X-Key", "\tvalue")])[0]


@pytest.mark.parametrize("items", [(('X-Key', 'value'),), [None], [["X-Key"]],
                                    [["X-Key", "value", "extra"]], [(1, "value")]])
def test_complete_evidence_rejects_malformed_pair_collections(items):
    with pytest.raises(ValueError):
        headers.match_headers({"X-Key": "value"}, items)


def test_no_flattened_or_normalized_fallback_for_new_response_checks():
    response = ports.RecordedResponse(200, {"X-Key": SENTINEL}, {}, "", None, ports.RequestSpec("GET", "read"))
    norm = ports.NormalizedResponse(True, {"X-Key": SENTINEL}, 200, response)
    with pytest.raises(ValueError, match="evidence"):
        backend._eval_response(Assertion("header_equals", {"header": "X-Key", "value": SENTINEL}), norm)


@pytest.mark.parametrize("mutation", ["add", "erase", "replace"])
def test_normalizer_cannot_supply_or_erase_raw_header_evidence(mutation):
    response = ports.RecordedResponse(200, {}, {}, "", None, ports.RequestSpec("GET", "read"),
        header_items=None if mutation == "add" else [("X-Key", SENTINEL)])
    class Change(FakeNormalizer):
        def normalize(self, supplied):
            norm = super().normalize(supplied)
            if mutation == "replace":
                norm.raw = dataclasses.replace(supplied, header_items=[])
            else:
                supplied.header_items = [("X-Key", SENTINEL)] if mutation == "add" else None
            return norm
    with pytest.raises(ValueError, match="protected header evidence") as error:
        normalize_response(Change(), response)
    assert SENTINEL not in str(error.value)


@pytest.mark.parametrize("policy,status", [("FAIL", "FAILED"), ("SKIP", "SKIPPED")])
def test_poll_timeout_preserves_every_failed_request_check(policy, status):
    step = request(business={"X-Key": SENTINEL}, checks=[equals()])
    step["poll"] = {"on_timeout": policy}
    clock = SimpleNamespace(time=0)
    def sleep(seconds):
        clock.time += seconds
    result = execute(load(step), api=ObservedApi([], []), poll_config=SimpleNamespace(timeout=1, interval=1),
                     now=lambda: clock.time, sleep=sleep)
    assert result.steps[0].status == status
    request_checks = [check for check in result.checks if check.point == "request"]
    assert len(request_checks) == len(result.provider_recordings)
    assert request_checks and all(not check.ok for check in request_checks)


def test_request_header_failure_retains_response_binding_and_honors_explicit_stop():
    first = request(business={"X-Key": "wanted"})
    later = request("later", business={"X-Key": {"from_step": "read", "response_field": "key"}})
    api = ObservedApi([("X-Key", "actual")], [], payloads={"read": {"key": "actual"}})
    result = execute(load(first, later), api=api)
    assert [step.status for step in result.steps] == ["FAILED", "PASSED"]
    assert result.steps[1].after_failures == ["read"]
    first["on_failure"] = "stop"
    stopped = execute(load(first, later), api=ObservedApi([], []))
    assert [step.status for step in stopped.steps] == ["FAILED", "BLOCKED"]


def test_contract_preserves_header_evidence_when_status_is_invalid():
    scenario = load(request(checks=[equals(), {"check": "status_equals", "value": 200}]))
    raw = ports.RecordedResponse(None, {}, {}, "", None, ports.RequestSpec("GET", "read"),
        step_id="read", template_path="read", header_items=[("Cache-Control", "no-store")],
        user=None, session_generation=0)
    result = contract.run(scenario, [raw], FakeNormalizer())
    assert result.steps[0].status == "FAILED"
    assert "header" not in result.checks[0].detail


def test_contract_missing_recording_or_reference_is_an_error_without_values():
    scenario = load(request(checks=[equals(SENTINEL)]))
    assert contract.run(scenario, [], FakeNormalizer()).steps[0].status == "ERROR"
    scenario = load(request("source"), request(checks=[equals({"from_step": "source", "response_field": "key"})]))
    api = ObservedApi([], [("Cache-Control", SENTINEL)])
    recorded = execute(load(request("source"), request()), api=api)
    checked = contract.run(scenario, recorded.provider_recordings, FakeNormalizer())
    assert checked.steps[0].status == "ERROR"
    assert SENTINEL not in repr(checked)


@pytest.mark.parametrize("mode", ["backend", "e2e"])
@pytest.mark.parametrize("seam", ["resolver", "api", "normalizer", "recorder_record", "recorder_read"])
def test_header_bearing_port_exceptions_are_value_free(mode, seam):
    scenario = load(request(business={"X-Key": SENTINEL}, checks=[equals(SENTINEL)]))
    class Api(ObservedApi):
        def send(self, spec, session):
            if seam == "api":
                raise RuntimeError(repr(spec.headers))
            return super().send(spec, session)
    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            if seam == "normalizer":
                raise RuntimeError(repr(response.header_items))
            return super().normalize(response)
    class Recorder(FakeRecorder):
        def record(self, response):
            if seam == "recorder_record":
                raise RuntimeError(repr(response.request_header_items))
            return super().record(response)
        def responses(self):
            if seam == "recorder_read" and self._responses:
                raise RuntimeError(repr(self._responses[0].header_items))
            return super().responses()
    def resolve(*args):
        if seam == "resolver":
            raise RuntimeError(repr(args[2].headers))
        return resolver(*args)
    result = execute(scenario, mode=mode, api=Api([("X-Key", SENTINEL)], [("Cache-Control", SENTINEL)]),
                     normalizer=Normalizer(), recorder=Recorder(), resolve_request=resolve)
    assert result.steps[0].status == "ERROR"
    assert SENTINEL not in repr(result) + " ".join(step.detail for step in result.steps)


@pytest.mark.parametrize("seam", ["open", "action", "snapshot", "close"])
@pytest.mark.parametrize("mode", ["live", "mock"])
def test_header_bearing_ui_lifecycle_exceptions_are_value_free(seam, mode):
    steps = [request(business={"X-Key": SENTINEL}, ui=True)]
    if seam == "snapshot":
        steps.append({"id": "wait", "do": "wait", "duration": 1,
                      "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}})
    scenario = load(*steps)
    def observed(index, result, permit):
        for response in [t.response for t in result.evidence.traffic] + result.evidence.mock_recordings:
            response.request_header_items = [("X-Key", SENTINEL)]
        return result
    class Ui(ScriptedUi):
        def open_stepwise(self, *args, **kwargs):
            if seam == "open":
                raise RuntimeError(SENTINEL)
            return super().open_stepwise(*args, **kwargs)
        def perform_step(self, *args):
            if seam == "action":
                raise RuntimeError(SENTINEL)
            return super().perform_step(*args)
        def snapshot(self, context):
            raise RuntimeError(SENTINEL)
        def close_stepwise(self, context):
            if seam == "close":
                raise RuntimeError(SENTINEL)
            return super().close_stepwise(context)
    ui = Ui(count=1, requests=[[ports.RequestSpec("GET", "read")]], mutate=observed)
    result = run_ui(scenario, ui, mode=mode, auth=None, sleep=lambda _: None)
    assert any(step.status == "ERROR" for step in result.steps)
    assert SENTINEL not in repr(result) + " ".join(step.detail for step in result.steps)


def test_contract_normalizer_exception_with_captured_headers_is_value_free():
    scenario = load(request(checks=[equals(SENTINEL)]))
    result = execute(scenario, api=ObservedApi([], [("Cache-Control", SENTINEL)]))
    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            raise RuntimeError(repr(response.header_items))
    checked = contract.run(scenario, result.provider_recordings, Normalizer())
    assert checked.steps[0].status == "ERROR"
    assert SENTINEL not in checked.steps[0].detail + repr(checked)


def test_legacy_unrelated_port_exception_keeps_its_existing_diagnostic():
    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            raise RuntimeError("legacy normalization diagnostic")
    result = execute(load(request()), normalizer=Normalizer())
    assert result.steps[0].detail == "legacy normalization diagnostic"


@pytest.mark.parametrize("mode", ["backend", "e2e"])
@pytest.mark.parametrize("correct_request", [False, True])
def test_skip_timeout_cannot_hide_request_failure_or_resume_flow(mode, correct_request):
    step = request(business={"X-Key": SENTINEL}, checks=[equals()])
    step["poll"] = {"on_timeout": "SKIP"}
    scenario = load(step, request("later"))
    api = ObservedApi([("X-Key", SENTINEL)] if correct_request else [], [])
    clock = SimpleNamespace(time=0)
    def sleep(seconds):
        clock.time += seconds
    domain = execute(scenario, mode=mode, api=api,
        poll_config=SimpleNamespace(timeout=1, interval=1), now=lambda: clock.time, sleep=sleep)
    report = RunReport(scenario.id, [domain])
    assert [step.status for step in domain.steps] == ["SKIPPED", "BLOCKED"]
    assert domain.steps[1].blocked_by == ["read"]
    origin = domain.steps[0].response_origin
    assert origin.timed_out is True and origin.is_final is False
    assert api.sent and all(sent.path == "read" for sent in api.sent)
    assert len(domain.checks) == len(domain.provider_recordings)
    assert all(check.ok is correct_request for check in domain.checks)
    assert domain.status == report.status == ("DEGRADED" if correct_request else "FAILED")
    assert domain.passed is report.passed is correct_request
    diagnostic = repr(report) + str(report.localize()) + str(report.degradations())
    diagnostic += " ".join(step.detail for step in domain.steps)
    assert SENTINEL not in diagnostic


@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_ordinary_request_failure_still_continues_after_aggregation_fix(mode):
    scenario = load(request(business={"X-Key": SENTINEL}), request("later"))
    api = ObservedApi([], [])
    domain = execute(scenario, mode=mode, api=api)
    report = RunReport(scenario.id, [domain])
    assert [step.status for step in domain.steps] == ["FAILED", "PASSED"]
    assert [sent.path for sent in api.sent] == ["read", "later"]
    assert domain.steps[1].after_failures == ["read"]
    assert domain.status == report.status == "FAILED"
    assert domain.passed is report.passed is False


@pytest.mark.parametrize("seam", ["action", "snapshot", "close"])
@pytest.mark.parametrize("mode", ["live", "mock"])
def test_observed_headers_promote_sensitivity_for_later_ui_callbacks(mode, seam):
    steps = [request(ui=True)]
    if seam == "action":
        steps.append({"id": "next", "do": "click", "target": "next"})
    elif seam == "snapshot":
        steps.append({"id": "wait", "do": "wait", "duration": 1,
                      "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}})
    def observed(index, result, permit):
        for response in [item.response for item in result.evidence.traffic] + result.evidence.mock_recordings:
            response.request_header_items = [("Cookie", SENTINEL)]
        return result
    class Ui(ScriptedUi):
        def perform_step(self, *args):
            if seam == "action" and self.evidence:
                raise RuntimeError(str(self.evidence[0].traffic[0].response.request_header_items))
            return super().perform_step(*args)
        def snapshot(self, context):
            raise RuntimeError(str(self.evidence[0].traffic[0].response.request_header_items))
        def close_stepwise(self, context):
            if seam == "close":
                raise RuntimeError(str(self.evidence[0].traffic[0].response.request_header_items))
            return super().close_stepwise(context)
    ui = Ui(count=1, requests=[[ports.RequestSpec("GET", "read")]], mutate=observed)
    result = run_ui(load(*steps), ui, mode=mode, auth=None, sleep=lambda _: None)
    assert any(step.status == "ERROR" for step in result.steps)
    assert SENTINEL not in repr(result) + " ".join(step.detail for step in result.steps)


@pytest.mark.parametrize("container", ["traffic", "diagnostic_recorded", "mock_recordings"])
@pytest.mark.parametrize("field", ["request_header_items", "header_items", "headers"])
def test_returned_headers_protect_close_even_when_evidence_validation_fails(container, field):
    def observed(index, result, permit):
        evidence = result.evidence
        response = evidence.traffic[0].response
        if container != "traffic":
            response = copy.deepcopy(response)
            object.__setattr__(evidence, container, [response])
        setattr(response, field, {"Cookie": SENTINEL} if field == "headers" else [("Cookie", SENTINEL)])
        # Invalid attribution fails before a response assertion or normalizer.
        object.__setattr__(evidence, "step_id", "invalid")
        return result
    class Ui(ScriptedUi):
        def close_stepwise(self, context):
            evidence = self.evidence[0]
            response = evidence.traffic[0].response if container == "traffic" else getattr(evidence, container)[0]
            raise RuntimeError(str(getattr(response, field)))
    ui = Ui(count=1, requests=[[ports.RequestSpec("GET", "read")]], mutate=observed)
    result = run_ui(load(request(ui=True)), ui, auth=None)
    assert result.steps[0].status == "ERROR"
    assert "UI close failed" in result.steps[0].detail
    assert SENTINEL not in result.steps[0].detail + repr(result)


def test_legacy_ui_without_captured_header_blocks_preserves_close_diagnostic():
    class Ui(ScriptedUi):
        def close_stepwise(self, context):
            raise RuntimeError("legacy UI close diagnostic")
    ui = Ui(count=1, requests=[[ports.RequestSpec("GET", "read")]])
    result = run_ui(load(request(ui=True)), ui, auth=None)
    assert result.steps[0].detail == "UI context close failed: legacy UI close diagnostic"
