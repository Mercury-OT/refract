"""Real HTTP evidence for separate parents reusing one creation declaration."""
from pathlib import Path
import shutil

import httpx
import pytest
import yaml

from adapters.demo.auth import DemoAuthenticator
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.wiring import build_adapters
from refracto.runner import run_scenario


EXAMPLES = Path(__file__).resolve().parents[2] / "examples/scenario-reuse"
PARENTS = {
    "update": EXAMPLES / "create_update_read.yaml",
    "delete": EXAMPLES / "create_delete_read.yaml",
}


class ObservedAuthentication(DemoAuthenticator):
    """Observe synthetic sessions; the Demo server does not authenticate users."""

    def __init__(self):
        self.acquired = []

    def session(self, user):
        acquired = super().session(user)
        self.acquired.append((user, acquired))
        return acquired


class ObservedHttp:
    """Retain the real HTTP driver while observing its credential objects."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []

    def send(self, spec, session):
        self.calls.append((spec, session))
        return self.delegate.send(spec, session)


class MissingObservedField(DemoResponseNormalizer):
    """A labeled normalized-observation fault; actual HTTP evidence stays intact."""

    def __init__(self, method, field):
        self.method, self.field = method, field
        self.removed = 0

    def normalize(self, response):
        observed = super().normalize(response)
        if response.request.method == self.method:
            assert self.field in observed.fields
            del observed.fields[self.field]
            self.removed += 1
        return observed


def read_items(base_url):
    response = httpx.get(f"{base_url}/items", timeout=5)
    response.raise_for_status()
    assert response.json()["success"] is True
    return response.json()["data"]["items"]


def retained_item(base_url):
    # Same name as the deletion input intentionally excludes name-based identity.
    response = httpx.post(f"{base_url}/items", json={"name": "Delete test record"}, timeout=5)
    response.raise_for_status()
    assert response.json()["success"] is True
    item_id = response.json()["data"]["itemId"]
    return next(item for item in read_items(base_url) if item["id"] == item_id)


@pytest.mark.parametrize("order", [("update", "delete"), ("delete", "update")])
def test_two_paths_execute_separate_creation_and_sessions_on_one_target(demo_server, order):
    retained = retained_item(demo_server)
    adapters = build_adapters(demo_server)
    adapters.auth = authentication = ObservedAuthentication()
    adapters.api = observed_http = ObservedHttp(adapters.api)
    reports, created_ids, trace_sets = {}, {}, []

    for run_index, kind in enumerate(order):
        report = run_scenario(PARENTS[kind], adapters, projections=("backend",))
        reports[kind] = report
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        assert len(report.domains) == 1
        domain = report.domains[0]
        assert domain.projection == "backend"
        assert [(step.step_id, step.status) for step in domain.steps] == [
            ("create/create_request", "PASSED"), (kind, "PASSED"), ("read", "PASSED")]
        assert all(step.user == "user" and step.session_generation == 1 for step in domain.steps)
        creation, change, listing = domain.provider_recordings
        assert [record.step_id for record in domain.provider_recordings] == [
            "create/create_request", kind, "read"]
        assert [record.request.method for record in domain.provider_recordings] == [
            "POST", "PUT" if kind == "update" else "DELETE", "GET"]
        expected_name = "Test record" if kind == "update" else "Delete test record"
        assert creation.request.path == "items"
        assert creation.request.body == {"name": expected_name}
        assert creation.json["data"]["name"] == expected_name
        item_id = creation.json["data"]["itemId"]
        assert item_id != retained["id"] and item_id not in created_ids.values()
        created_ids[kind] = item_id
        assert change.request.path == f"items/{item_id}"
        assert listing.request.path == "items"
        for step in domain.steps[1:]:
            assert list(step.resolved_bindings.values()) == [item_id]
            assert {source.origin.step_id for source in step.binding_sources.values()} == {"create/create_request"}
        assert all(record.user == "user" and record.session_generation == 1
                   for record in domain.provider_recordings)
        traces = {step.trace_id for step in domain.steps}
        assert None not in traces and len(traces) == 3
        for step, record in zip(domain.steps, domain.provider_recordings):
            assert record.request.traceparent.split("-")[1] == step.trace_id
            assert dict(record.request_header_items)["traceparent"] == record.request.traceparent
        assert all(traces.isdisjoint(previous) for previous in trace_sets)
        trace_sets.append(traces)

        assert len(authentication.acquired) == run_index + 1
        acquired = authentication.acquired[-1][1]
        run_calls = observed_http.calls[run_index * 3:(run_index + 1) * 3]
        assert len(run_calls) == 3
        assert all(credentials is acquired.credentials for _, credentials in run_calls)
        if kind == "update":
            assert change.request.body == {"name": "Updated test record"}
            assert change.json["data"]["itemId"] == item_id
            assert any(item["id"] == item_id and item["name"] == "Updated test record"
                       for item in listing.json["data"]["items"])
        else:
            assert change.request.body is None
            assert change.json["data"]["deleted"] == 1
            assert all(item["id"] != item_id for item in listing.json["data"]["items"])
        current_items = read_items(demo_server)
        assert next(item for item in current_items if item["id"] == retained["id"]) == retained
        if "update" in created_ids:
            assert next(item for item in current_items if item["id"] == created_ids["update"])["name"] == "Updated test record"

    assert reports["update"] is not reports["delete"]
    assert len(observed_http.calls) == 6
    first_session, second_session = [entry[1] for entry in authentication.acquired]
    assert first_session.principal_id == second_session.principal_id
    assert first_session.authentication_id != second_session.authentication_id
    assert first_session.credentials is not second_session.credentials
    final_items = read_items(demo_server)
    assert {item["id"] for item in final_items} == {retained["id"], created_ids["update"]}
    assert all(item["id"] != created_ids["delete"] for item in final_items)


@pytest.mark.parametrize("kind", ["update", "delete"])
def test_missing_consumed_id_blocks_dependent_actions_without_reusing_other_evidence(demo_server, kind):
    adapters = build_adapters(demo_server)
    adapters.normalizer = fault = MissingObservedField("POST", "itemId")
    report = run_scenario(PARENTS[kind], adapters, projections=("backend",))
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["FAILED", "BLOCKED", "BLOCKED"]
    assert [(check.step, check.check) for check in domain.checks if not check.ok] == [
        ("create/create_request", "has")]
    for step in domain.steps[1:]:
        assert step.blocked_by == ["create/create_request"]
        assert step.resolved_bindings == {}
    assert fault.removed == 1
    assert len(domain.provider_recordings) == 1
    creation = domain.provider_recordings[0]
    assert creation.request.method == "POST"
    # The target did return an ID; this is an observation fault, not a target bug.
    assert creation.json["data"]["itemId"] == read_items(demo_server)[0]["id"]


def test_wrong_update_input_fails_the_unchanged_final_name_requirement(demo_server, tmp_path):
    shutil.copytree(EXAMPLES, tmp_path / "reuse")
    path = tmp_path / "reuse/create_update_read.yaml"
    original = yaml.safe_load(path.read_text(encoding="utf-8"))
    altered = yaml.safe_load(path.read_text(encoding="utf-8"))
    altered["steps"][1]["do"]["request"]["body"]["name"] = {"from_parameter": "initial_name"}
    assert altered["steps"][2] == original["steps"][2]
    path.write_text(yaml.safe_dump(altered, sort_keys=False), encoding="utf-8")
    report = run_scenario(path, build_adapters(demo_server), projections=("backend",))
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "FAILED"]
    assert [(check.step, check.check) for check in domain.checks if not check.ok] == [
        ("read", "collection_matching_count")]
    assert domain.provider_recordings[1].request.body == {"name": "Test record"}
    assert read_items(demo_server)[0]["name"] == "Test record"


def test_missing_list_observation_cannot_satisfy_absence_count(demo_server):
    adapters = build_adapters(demo_server)
    adapters.normalizer = fault = MissingObservedField("GET", "items")
    report = run_scenario(PARENTS["delete"], adapters, projections=("backend",))
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "FAILED"]
    assert [(check.step, check.check) for check in domain.checks if not check.ok] == [
        ("read", "collection_matching_count")]
    assert fault.removed == 1
    assert domain.provider_recordings[-1].json["data"]["items"] == []
    assert read_items(demo_server) == []
