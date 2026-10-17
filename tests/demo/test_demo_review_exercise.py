"""Real HTTP exercise runs plus one bounded injected state-observation fault.

This checks source fidelity and sensitivity, not human review performance. The
fault changes returned observation evidence, not product storage or core logic.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from adapters.demo.wiring import build_adapters
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parents[2] / "docs/review-exercise"
VERSIONS = ("baseline", "case-01", "case-02", "case-03")


class ObservedApi:
    def __init__(self, delegate):
        self.delegate, self.sent = delegate, []

    def send(self, spec, session):
        self.sent.append((spec.method, spec.path, deepcopy(spec.body)))
        return self.delegate.send(spec, session)


class ObservedState:
    """Replace just one existing creation observation value."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.originals, self.returned, self.creation_observations = [], [], []

    def observe(self, trace_id):
        original = self.delegate.observe(trace_id)
        assert original.trace_id == trace_id
        self.originals.append(deepcopy(original))
        result = deepcopy(original)
        for span in result.spans:
            if span.name == "item.create":
                assert type(span.attributes["row_count"]) is int
                assert span.attributes["row_count"] == 3
                self.creation_observations.append((trace_id, span.attributes["row_count"]))
                span.attributes["row_count"] = 2
        # The underlying adapter's returned object must remain untouched.
        assert original == self.originals[-1]
        self.returned.append(deepcopy(result))
        return result


class PollClock:
    """Advance the runner's existing test clock without sleeping in real time.

    HTTP and trace reads still use the real Demo. This is not a timeout or
    performance test; no application clock, assertion or returned fact changes.
    """

    def __init__(self):
        self.time = 0.0

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += seconds


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("form", ("included", "flat"))
@pytest.mark.parametrize("observation", ("direct", "row-count-2"))
def test_review_source_runs_and_observation_control(demo_server, version, form, observation):
    """Each parametrized call receives the existing fresh Demo server fixture."""
    adapters = build_adapters(demo_server)
    adapters.api = ObservedApi(adapters.api)
    if observation != "direct":
        adapters.state = ObservedState(adapters.state)
    clock = PollClock()
    report = run_scenario(
        ROOT / version / f"{form}.yaml", adapters, projections=("backend",),
        now=clock.now, sleep=clock.sleep)
    assert report.degradations() == []
    assert [domain.projection for domain in report.domains] == ["backend"]
    domain = report.domains[0]
    first_local = "persist" if version == "case-01" else "create"
    first_id = f"setup/{first_local}" if form == "included" else first_local
    assert [step.step_id for step in domain.steps] == [first_id, "update", "read"]
    created_name = "review-final" if version == "case-02" else "review-draft"
    # Assert traffic and the real response, including the deliberately wrong
    # caller wiring. Successful execution does not endorse that requirement.
    assert adapters.api.sent[0] == ("POST", "items", {"name": created_name, "rows": [1, 2, 3]})
    creation = domain.provider_recordings[0]
    assert creation.json["success"] is True
    assert creation.json["data"]["name"] == created_name
    item_id = creation.json["data"]["itemId"]
    assert type(item_id) is int and item_id > 0
    assert creation.json["data"]["count"] == 3
    detects = observation == "row-count-2" and version != "case-03"
    if detects:
        assert report.status == "FAILED"
        assert [step.status for step in domain.steps] == ["FAILED", "PASSED", "PASSED"]
        assert [step.after_failures for step in domain.steps[1:]] == [[first_id], [first_id]]
        assert len(adapters.api.sent) == len(domain.provider_recordings) == 3
        failed = [(check.point, check.check) for check in domain.checks if not check.ok]
        assert failed == [("backend_state", "span_attr")]
        assert all(check.ok for check in domain.steps[0].checks if check.check != "span_attr")
    else:
        assert report.status == "PASSED", report.localize()
        assert [step.status for step in domain.steps] == ["PASSED"] * 3
        assert all(check.ok for check in domain.checks)
    # Current execution continues after an ordinary check failure. The user
    # declaration is explicitly migrated; the business checks and fault remain.
    assert adapters.api.sent == [
        ("POST", "items", {"name": created_name, "rows": [1, 2, 3]}),
        ("PUT", f"items/{item_id}", {"name": "review-final"}),
        ("GET", "items", None),
    ]
    assert domain.provider_recordings[1].json["data"]["itemId"] == item_id
    assert domain.provider_recordings[2].json["data"]["items"] == [
        {"id": item_id, "name": "review-final", "count": 3}]
    if observation != "direct":
        probe = adapters.state
        assert probe.creation_observations
        assert all(trace_id == domain.steps[0].trace_id and count == 3
                   for trace_id, count in probe.creation_observations)
        assert len(probe.originals) == len(probe.returned)
        for original, returned in zip(probe.originals, probe.returned):
            expected = deepcopy(original)
            for span in expected.spans:
                if span.name == "item.create":
                    span.attributes["row_count"] = 2
            assert returned == expected
