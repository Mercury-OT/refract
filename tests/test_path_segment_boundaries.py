"""One declared path segment must not silently navigate to another route."""
from dataclasses import replace

import pytest

from refracto import ports
from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.query import request_path
from tests.test_response_field_comparison import document, execute, request
from tests.test_scenario_include import include, leaf, parent, write_bundle


@pytest.mark.parametrize("segment", [".", ".."])
@pytest.mark.parametrize("position", ["literal", "parameter"])
@pytest.mark.parametrize("ui", [False, True])
def test_known_dot_segments_rejected_before_runtime(segment, position, ui):
    step = request("read", ui=ui)
    transport = step["expect"]["request"] if ui else step["do"]["request"]
    transport["path"] = ["records", segment if position == "literal" else {"from_parameter": "id"}]
    with pytest.raises(DeclarationError, match="dot segment"):
        _load_document(document(step, parameters={"id": segment}))


@pytest.mark.parametrize("segment", [".", ".."])
@pytest.mark.parametrize("parameter", [False, True])
def test_include_override_dot_segments_rejected_before_runtime(tmp_path, segment, parameter):
    child = leaf()
    child["steps"][0]["do"]["request"]["path"] = ["records", {"from_parameter": "name"}]
    root = parent([include(**{"with": {"name": {"from_parameter": "id"} if parameter else segment}})],
                  parameters={"id": segment})
    path, _ = write_bundle(tmp_path, root, child)
    with pytest.raises(DeclarationError, match="dot segment"):
        load_scenario(path)


@pytest.mark.parametrize("segment", [".", ".."])
@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_response_dot_segment_blocks_only_consumer_without_sending(segment, mode):
    consumer = request("consumer")
    consumer["do"]["request"]["path"] = ["records", {"from_step": "source", "response_field": "id"}]
    scenario = _load_document(document(request("source", []), consumer, request("independent")))
    result, api = execute(scenario, {"source": {"id": segment}, "independent": {}}, mode=mode)
    assert [step.status for step in result.steps] == ["COMPLETED", "BLOCKED", "PASSED"]
    assert result.steps[1].resolved_bindings == {}
    assert [sent.path for sent in api.sent] == ["source", "independent"]


@pytest.mark.parametrize("segment,encoded", [
    ("%2e", "%252e"), ("%2e%2e", "%252e%252e"), ("a/b", "a%2Fb"),
    ("a..b", "a..b"), ("...", "..."), (0, "0"),
])
@pytest.mark.parametrize("position", ["literal", "parameter", "response"])
def test_percent_and_punctuation_data_keep_single_encoding(segment, encoded, position):
    step = request("consumer")
    declared = ({"from_parameter": "id"} if position == "parameter" else
                {"from_step": "source", "response_field": "id"} if position == "response" else segment)
    step["do"]["request"]["path"] = ["records", declared]
    scenario = _load_document(document(request("source", []), step, parameters={"id": segment}))
    prepared, _ = prepare_step(scenario.steps[1], scenario,
                              {"source": ports.NormalizedResponse(True, {"id": segment}, 200, None)})
    assert prepared.request.path == "records/" + encoded


@pytest.mark.parametrize("path", ["records/../notes", "records/./notes", "../records", "/./records"])
def test_transport_path_guard_rejects_raw_dot_segments(path):
    with pytest.raises(ValueError, match="dot segment"):
        request_path(path, {})


def test_resolver_cannot_introduce_a_dot_route_before_send():
    scenario = _load_document(document(request("read"), request("later")))
    result, api = execute(scenario, resolve_request=lambda template:
                          ports.RequestSpec(template.method, "records/../notes", template.body))
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert api.sent == []


def test_programmatic_request_path_cannot_bypass_guard():
    scenario = _load_document(document(request("read"), request("later")))
    scenario.steps[0].request = replace(scenario.steps[0].request,
                                       path="records/../notes", path_segments=None)
    result, api = execute(scenario)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert api.sent == []
