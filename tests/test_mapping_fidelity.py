"""A finite Documents mapping panel, separate from Scenario pass/fail.

The target runs in process. These cooperative tests neither certify arbitrary
adapters nor supply independent external evidence. Fixed sample oracles are
written below, not produced by the normalizer under test.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from adapters.documents.normalizer import DocumentResponseNormalizer
from adapters.documents.resolver import resolve_request
from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto import ports
from refracto.runner import run_scenario


SCENARIO = (Path(__file__).resolve().parents[1] / "examples/documents/scenarios"
            / "dictionary_document_reference.yaml")

# Deliberate duplication makes the selected mapping contract reviewable without
# running its implementation. These are known responses, not generated truth.
SAMPLES = [
    ({"identifier": "sample-7", "properties": {"title": "Before", "category": "memo"}},
     {"document_id": "sample-7", "title": "Before", "category": "memo",
      "document": {"identifier": "sample-7", "properties": {"title": "Before", "category": "memo"}}}),
    ({"identifier": "sample-7", "properties": {"title": "After", "category": "memo"}},
     {"document_id": "sample-7", "title": "After", "category": "memo",
      "document": {"identifier": "sample-7", "properties": {"title": "After", "category": "memo"}}}),
    ({"identifier": "sample-7", "properties": {"category": "memo"}},
     {"document_id": "sample-7", "category": "memo",
      "document": {"identifier": "sample-7", "properties": {"category": "memo"}}}),
]


class PreviousTitle(DocumentResponseNormalizer):
    """M2: retain the first title and mistakenly reuse it for later responses."""

    def __init__(self):
        self.previous = None
        self.injections = 0

    def normalize(self, response):
        normalized = super().normalize(response)
        fields = deepcopy(normalized.fields)
        if self.previous is not None and "title" in fields:
            fields["title"] = self.previous
            self.injections += 1
        elif "title" in fields:
            self.previous = fields["title"]
        return replace(normalized, fields=fields)


class FillMissingTitle(DocumentResponseNormalizer):
    """M3: a plausible cache fallback invents an unobserved title."""

    def __init__(self):
        self.previous = None
        self.injections = 0

    def normalize(self, response):
        normalized = super().normalize(response)
        fields = deepcopy(normalized.fields)
        if "title" in fields:
            self.previous = fields["title"]
        elif self.previous is not None:
            fields["title"] = self.previous
            self.injections += 1
        return replace(normalized, fields=fields)


class CaptureNormalization:
    """Capture the actual call; never normalize a report again after the run."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []

    def normalize(self, response):
        before = deepcopy(response)
        normalized = self.delegate.normalize(response)
        self.calls.append((before, deepcopy(response), deepcopy(normalized)))
        return normalized

    def assert_preserved_evidence(self):
        assert self.calls
        for before, after, normalized in self.calls:
            assert before == after == normalized.raw
            assert normalized.status == before.status
            assert normalized.succeeded is True


class ObservedDocuments(DocumentRestApp):
    """Target response faults; storage, routing and authentication still execute."""

    def __init__(self, fault=None):
        super().__init__()
        self.fault = fault
        self.injections = 0
        self.observed = []

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if method == "GET" and response.status == 200 and self.fault is not None:
            raw = deepcopy(response.body)
            properties = raw["resource"]["document"]["properties"]
            if self.fault == "changed":
                properties["title"] = "Changed title"
            elif self.fault == "missing":
                del properties["title"]
            else:
                raise AssertionError("unlisted target fault")
            self.injections += 1
            response = RestResponse(response.status, raw, response.headers)
        self.observed.append(deepcopy(response))
        return response


def _run(app, normalizer=None, scenario=SCENARIO, resolver=resolve_request):
    capture = CaptureNormalization(normalizer or DocumentResponseNormalizer())
    adapters = build_adapters(app)
    adapters.normalizer = capture
    adapters.resolve_request = resolver
    report = run_scenario(scenario, adapters, projections=("backend",))
    assert [domain.projection for domain in report.domains] == ["backend"]
    assert report.degradations() == []
    assert [step.step_id for step in report.domains[0].steps] == ["create", "read"]
    assert [before.step_id for before, _, _ in capture.calls] == ["create", "read"]
    assert [before.status for before, _, _ in capture.calls] == [201, 200]
    assert [before.json for before, _, _ in capture.calls] == [item.body for item in app.observed[-2:]]
    assert [before.request.path for before, _, _ in capture.calls] == [item[1] for item in app.requests[-2:]]
    capture.assert_preserved_evidence()
    return report, capture


def _failed_fields(report):
    failures = report.localize()
    assert all(item[:4] == ("backend", "read", "response", "field_equals") for item in failures)
    return {item[4].split(" expected=", 1)[0] for item in failures}


@pytest.mark.parametrize("sample", SAMPLES, ids=["original", "changed", "missing"])
def test_literal_samples_define_the_normal_mapping(sample):
    document, expected = deepcopy(sample)
    raw = ports.RecordedResponse(200, {}, {"receipt": {"state": "accepted"},
        "resource": {"document": document}}, "", None,
        ports.RequestSpec("GET", "/v3/documents/sample-7"))
    capture = CaptureNormalization(DocumentResponseNormalizer())
    result = capture.normalize(raw)
    assert result.fields == expected
    capture.assert_preserved_evidence()


@pytest.mark.parametrize("faulty,second", [(PreviousTitle, 1), (FillMissingTitle, 2)],
                         ids=["M2-stale", "M3-invented"])
def test_fixed_response_sequence_detects_mapping_fault_without_a_scenario(faulty, second):
    normalizer = faulty()
    capture = CaptureNormalization(normalizer)
    for index in (0, second):
        document, expected = deepcopy(SAMPLES[index])
        response = ports.RecordedResponse(200, {}, {"receipt": {"state": "accepted"},
            "resource": {"document": document}}, "", None,
            ports.RequestSpec("GET", "/v3/documents/sample-7"))
        actual = capture.normalize(response)
        assert (actual.fields == expected) is (index == 0)
    capture.assert_preserved_evidence()
    assert normalizer.injections == 1
    actual = capture.calls[-1][2].fields
    assert actual["title"] == "Before"
    # Only this selected alias changed; the current whole document stays raw.
    assert {key: value for key, value in actual.items() if key != "title"} == {
        key: value for key, value in SAMPLES[second][1].items() if key != "title"}


@pytest.mark.parametrize("wrong_object", [False, True], ids=["normal", "M1-wrong-object"])
def test_resolver_object_mapping_is_checked_against_real_created_identity(wrong_object):
    app = ObservedDocuments()
    # Explicit fixture setup, not a hidden business action inside an adapter.
    _, token = app.authenticate("editor")
    seeded = app.handle("POST", "/v3/documents", {"title": "Unrelated document", "category": "memo"},
                        {"x-session-key": token})
    assert seeded.status == 201
    unrelated_id = seeded.body["resource"]["document"]["identifier"]
    routed = []

    def resolver(action):
        result = resolve_request(action)
        if action.method == "GET":
            if wrong_object:
                result = replace(result, path=f"/v3/documents/{unrelated_id}")
            routed.append((action.path, result.path))
        return result

    report, capture = _run(app, resolver=resolver)
    assert app.request_count == 3 and app.injections == 0 and len(routed) == 1
    created_id = capture.calls[0][0].json["resource"]["document"]["identifier"]
    read_id = capture.calls[1][0].json["resource"]["document"]["identifier"]
    assert created_id != unrelated_id
    assert routed[0][0].strip("/") == f"documents/{created_id}"
    expected_route = f"/v3/documents/{created_id}"
    mapping_matches = routed[0][1] == expected_route
    assert mapping_matches is not wrong_object
    assert app.requests[-1][1] == routed[0][1]
    assert read_id == (unrelated_id if wrong_object else created_id)
    assert report.status == ("FAILED" if wrong_object else "PASSED")
    assert _failed_fields(report) == ({"field='document_id'", "field='title'"} if wrong_object else set())


@pytest.mark.parametrize("fault,normalizer,scenario_status,mapping_matches", [
    (None, DocumentResponseNormalizer, "PASSED", True),
    ("changed", DocumentResponseNormalizer, "FAILED", True),
    ("changed", PreviousTitle, "PASSED", False),
    ("missing", DocumentResponseNormalizer, "FAILED", True),
    ("missing", FillMissingTitle, "PASSED", False),
], ids=["normal", "M2-target-only", "M2-combined", "M3-target-only", "M3-combined"])
def test_real_run_keeps_scenario_and_mapping_outcomes_separate(fault, normalizer, scenario_status, mapping_matches):
    app = ObservedDocuments(fault)
    mapping = normalizer()
    report, capture = _run(app, mapping)
    assert app.request_count == 2
    assert app.injections == (0 if fault is None else 1)
    assert getattr(mapping, "injections", 0) == (0 if mapping_matches else 1)
    before, _, actual = capture.calls[-1]
    # These expected observations are prescribed by the explicit target fixture,
    # not read from either the tested mapping or Scenario result.
    properties = {"category": "memo"}
    expected_fields = {"category": "memo"}
    if fault != "missing":
        title = "Changed title" if fault == "changed" else "Dictionary document"
        properties["title"] = title
        expected_fields["title"] = title
    created_id = capture.calls[0][0].json["resource"]["document"]["identifier"]
    document = {"identifier": created_id, "properties": properties}
    assert before.json == {"receipt": {"state": "accepted"}, "resource": {"document": document}}
    expected_fields.update(document_id=created_id, document=document)
    assert (actual.fields == expected_fields) is mapping_matches
    assert report.status == scenario_status
    assert _failed_fields(report) == ({"field='title'"} if scenario_status == "FAILED" else set())
    assert [step.status for step in report.domains[0].steps] == ["PASSED", scenario_status]


def test_M4_omitted_title_obligation_passes_identical_faulty_observations(tmp_path):
    original = SCENARIO.read_bytes()
    strong_data = yaml.safe_load(original)
    weak_data = deepcopy(strong_data)
    checks = weak_data["steps"][1]["expect"]["response"]
    assert checks.pop(3) == {"check": "field_equals", "field": "title", "value": {"from_parameter": "title"}}
    restored = deepcopy(weak_data)
    restored["steps"][1]["expect"]["response"].insert(3, strong_data["steps"][1]["expect"]["response"][3])
    assert restored == strong_data
    weak = tmp_path / "weak.yaml"
    weak.write_text(yaml.safe_dump(weak_data, sort_keys=False), encoding="utf-8")
    strong_app, weak_app = ObservedDocuments("changed"), ObservedDocuments("changed")
    strong, strong_calls = _run(strong_app)
    weaker, weak_calls = _run(weak_app, scenario=weak)
    assert strong_app.injections == weak_app.injections == 1
    assert strong_app.request_count == weak_app.request_count == 2
    assert [call[0].json for call in strong_calls.calls] == [call[0].json for call in weak_calls.calls]
    assert [call[2].fields for call in strong_calls.calls] == [call[2].fields for call in weak_calls.calls]
    assert strong.status == "FAILED" and weaker.status == "PASSED"
    assert _failed_fields(strong) == {"field='title'"} and _failed_fields(weaker) == set()
    assert len(strong.domains[0].steps[1].checks) == len(weaker.domains[0].steps[1].checks) + 1
    assert SCENARIO.read_bytes() == original
