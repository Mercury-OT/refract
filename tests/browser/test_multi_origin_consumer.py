"""Unchanged declarations against independent actual page/API/static listeners."""
import pytest

from refracto.declaration.loader import load_scenario
from examples.browser_multi_origin.run import CASES, ROOT, digest, run_case


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("implementation", ["promise", "async"])
def test_fixed_consumer_panel_retains_supported_and_unassociated_results(case, implementation):
    row = run_case(case, implementation)
    supported = implementation == "promise" or case == "c01_static_ready"
    assert row["status"] == ("PASSED" if supported else "FAILED"), row["steps"]
    assert row["scenario_sha256"] == digest(ROOT / "scenarios" / (case + ".yaml"))
    assert {request["channel"] for request in row["server_requests"]} >= {"page", "static"}
    api = [request for request in row["server_requests"]
           if request["channel"] == "api" and request["method"] != "OPTIONS"]
    if case == "c01_static_ready":
        assert not api
    else:
        assert api  # A residual must exercise a real request, not fail at setup.
    for received in row["server_requests"]:
        names = {name.lower() for name in received["headers"]}
        assert not any(name.startswith("x-refract-") for name in names)
        assert "traceparent" not in names
        if received["channel"] != "api":
            assert "authorization" not in names and "cookie" not in names
    if supported:
        assert all(record["actual_origin"] == row["service_origins"]["api"]
                   for record in row["recorded_requests"])
        assert len(api) == len(row["recorded_requests"])
    else:
        assert not row["recorded_requests"]
        assert any(step["status"] == "ERROR" and "missing" in step["detail"] for step in row["steps"])
    if case == "c09_anonymous_refusal":
        assert all("authorization" not in {key.lower() for key in request["headers"]} for request in api)
    if case == "c10_named_access":
        assert all({key.lower(): value for key, value in request["headers"].items()}.get("authorization")
                   == "Bearer creator" for request in api)


@pytest.mark.parametrize("case", CASES)
def test_fixed_maintenance_change_preserves_scenarios_and_obligations(case):
    path = ROOT / "scenarios" / (case + ".yaml")
    original = digest(path)
    row = run_case(case, "promise", maintenance=True)
    assert row["status"] == "PASSED", row["steps"]
    assert row["scenario_sha256"] == original == digest(path)
    assert row["binding_configuration"] == {"selector_prefix": "v2-", "api_prefix": "/service"}
    assert all(request["path"].startswith("/service/") for request in row["server_requests"]
               if request["channel"] == "api")


def test_panel_files_are_exact_and_valid():
    paths = sorted((ROOT / "scenarios").glob("*.yaml"))
    assert {path.stem for path in paths} == set(CASES)
    for path in paths:
        assert load_scenario(path).id == "records.multi_origin." + path.stem


@pytest.mark.parametrize("identity", ["r2", "r3"])
def test_public_list_rejects_substitution_of_each_remaining_initial_record(monkeypatch, identity):
    from examples.browser_multi_origin.app import Application

    original = Application.response

    def changed_response(self, method, path, query, body, headers):
        status, payload = original(self, method, path, query, body, headers)
        if method == "GET" and path == "/records":
            payload["data"]["records"] = [
                {**item, "id": "unexpected", "name": "Unexpected"} if item["id"] == identity else item
                for item in payload["data"]["records"]
            ]
        return status, payload

    monkeypatch.setattr(Application, "response", changed_response)
    row = run_case("c02_public_list", "promise")
    assert row["status"] == "FAILED", row["steps"]
    checks = row["steps"][-1]["checks"]
    assert any(check["check"] == "collection_length" and check["ok"] for check in checks)
    assert sum(check["check"] == "collection_matching_count" and not check["ok"] for check in checks) == 1


def test_consumer_normalization_uses_actual_sample_fields_and_refusals():
    from refracto import ports
    from examples.browser_multi_origin.adapter import Normalizer
    def recorded(body):
        return ports.RecordedResponse(200, {}, body, "", None, ports.RequestSpec("GET", "records-api/records"))
    normalizer = Normalizer()
    first = normalizer.normalize(recorded({"success": True, "data": {"name": "literal independent sample"}}))
    changed = normalizer.normalize(recorded({"success": True, "data": {"name": "changed sample"}}))
    absent = normalizer.normalize(recorded({"success": True, "data": {}}))
    refused = normalizer.normalize(recorded({"success": False, "data": {"reason": "authentication_required"}}))
    assert first.fields == {"name": "literal independent sample"}
    assert changed.fields == {"name": "changed sample"}
    assert "name" not in absent.fields
    assert refused.succeeded is False
    with pytest.raises(ValueError):
        normalizer.normalize(recorded({"data": {"name": "missing success evidence"}}))


def test_measurement_rejects_omitted_duplicate_and_miscounted_units():
    import copy
    from examples.browser_multi_origin.measure import validate_panel
    rows = [{"implementation": implementation, "case_id": case, "status": "FAILED"}
            for implementation in ("promise", "async") for case in CASES]
    panel = {"records": rows, "expected_units": 20, "executed_units": 20,
             "status_counts": {"FAILED": 20}}
    assert len(validate_panel(panel)) == 20
    for mutation in ("omit", "duplicate", "count"):
        broken = copy.deepcopy(panel)
        if mutation == "omit":
            broken["records"].pop()
        elif mutation == "duplicate":
            broken["records"][-1] = broken["records"][0]
        else:
            broken["status_counts"] = {"PASSED": 20}
        with pytest.raises(ValueError):
            validate_panel(broken)
