"""Real Demo consumers and independently authored flat controls for inclusion.

The flat controls are committed source fixtures, never produced by the expansion
implementation. Chromium tests intentionally fail (not skip) if it is unavailable.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import httpx
import pytest

from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from refracto import ports
from refracto.contract import store
from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario
from tests.demo.conftest import RUN_PY, _free_port, _wait_until_up
from tests.demo.ui_fixtures import creation_plan


ROOT = Path(__file__).resolve().parents[2]
API_INCLUDE = ROOT / "scenarios/demo_include_items.yaml"
UI_INCLUDE = ROOT / "scenarios/demo_include_items_ui.yaml"
API_FLAT = ROOT / "tests/fixtures/include_demo_flat/items.yaml"
UI_FLAT = ROOT / "tests/fixtures/include_demo_flat/items_ui.yaml"


@pytest.fixture
def flat_demo_server():
    """A second fresh server makes IDs and evidence comparable without resets."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile() as log_file:
        process = subprocess.Popen(
            [sys.executable, str(RUN_PY), "--host", "127.0.0.1", "--port", str(port)],
            stdout=log_file, stderr=subprocess.STDOUT,
        )
        try:
            _wait_until_up(process, base_url, log_file)
            yield base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


class ObservedUi(DemoUiDriver):
    def __init__(self, config):
        super().__init__(config)
        self.opens = self.closes = 0
        self.contexts, self.permits, self.results = [], [], []
        self.scenario_ids = []

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None, **identity):
        self.opens += 1
        self.scenario_ids.append(scenario.id)
        context = super().open_stepwise(scenario, session, mode=mode, mock_plan=mock_plan, **identity)
        self.contexts.append(context)
        return context

    def perform_step(self, scenario, step, context, permit):
        self.contexts.append(context)
        self.scenario_ids.append(scenario.id)
        self.permits.append(permit)
        result = super().perform_step(scenario, step, context, permit)
        self.results.append(result)
        return result

    def close_stepwise(self, context):
        self.closes += 1
        super().close_stepwise(context)


class ObservedAuth:
    def __init__(self, delegate):
        self.delegate, self.roles = delegate, []

    def session(self, role):
        self.roles.append(role)
        return self.delegate.session(role)

    def identify(self, user):
        return self.delegate.identify(user)


class ObservedApi:
    def __init__(self, delegate):
        self.delegate, self.sent = delegate, []

    def send(self, spec, session):
        self.sent.append((spec.method, spec.path, deepcopy(spec.body)))
        return self.delegate.send(spec, session)


def _ui_plan():
    plan = creation_plan(("included-first", "1"))
    # The second inclusion navigates again in the same session. Its initial
    # list is the actual already-created state, not another empty-list fixture.
    plan.insert(3, ports.MockResponse(
        fixture_id="second-open-list", source="demo fixture: first item remains",
        method="GET", path="items", response=deepcopy(plan[2].response),
    ))
    return plan


def _run(path, base_url, projection):
    ui = ObservedUi(DemoConfig(base_url=base_url)) if projection != "backend" else None
    adapters = build_adapters(base_url, ui=ui)
    adapters.auth = ObservedAuth(adapters.auth)
    adapters.api = ObservedApi(adapters.api)
    projections = ("backend", "contract") if projection == "backend" else (projection,)
    report = run_scenario(path, adapters, projections=projections,
                          mock_plan=_ui_plan() if projection == "frontend" else None)
    assert report.status == "PASSED", (report.localize(), [
        (d.projection, s.step_id, s.status, s.detail)
        for d in report.domains for s in d.steps])
    assert report.degradations() == []
    assert adapters.auth.roles == ["user"]
    return report, adapters, ui


def _report_signature(report):
    """Exclude only names, fresh trace IDs, and sensitive diagnostic values."""
    return [(domain.projection, domain.status, [
        (step.status, step.attempts, step.skipped, step.not_checked,
         [(check.point, check.check, check.ok) for check in step.checks])
        for step in domain.steps]) for domain in report.domains]


def _assert_sources(report, parent_path, child_path, child_scenario):
    scenario = load_scenario(parent_path)
    assert report.source_lookup == scenario.source_lookup
    for step in scenario.steps:
        if "/" in step.id:
            call_id, source_step_id = step.id.split("/")
            expected = {"scenario_id": child_scenario, "step_id": source_step_id,
                        "include_step_id": call_id,
                        "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}
        else:
            expected = {"scenario_id": scenario.id, "step_id": step.id,
                        "include_step_id": None,
                        "sha256": hashlib.sha256(parent_path.read_bytes()).hexdigest()}
        expected.update(source_user="user", effective_user="user")
        assert report.source_lookup[step.id] == expected


def _assert_ui_lifecycle(ui, domain, *, included):
    assert ui.opens == ui.closes == 1
    assert len(ui.permits) == 8
    assert all(context is ui.contexts[0] for context in ui.contexts)
    assert [permit.action for permit in ui.permits] == ["open", "click", "fill", "click"] * 2
    assert [permit.value for permit in ui.permits if permit.action == "fill"] == ["included-first", "1"]
    assert len({permit.action_id for permit in ui.permits}) == 8
    assert len({permit.execution_id for permit in ui.permits}) == 1
    expected_root_id = "demo.include_items_ui" if included else "demo.include_items_ui_flat_control"
    assert ui.scenario_ids == [expected_root_id] * 9
    separator = "/" if included else "_"
    expected_ids = [f"{prefix}{separator}{leaf}" for prefix in ("first", "second")
                    for leaf in ("open_page", "open_form", "fill_name", "create")]
    assert [permit.step_id for permit in ui.permits] == expected_ids
    assert [step.step_id for step in domain.steps] == expected_ids
    assert [step.status for step in domain.steps] == ["COMPLETED"] * 3 + ["PASSED"] + ["COMPLETED"] * 3 + ["PASSED"]
    assert list(domain.steps[6].resolved_bindings.values()) == ["1"]
    assert list(domain.steps[7].resolved_bindings.values()) == ["1"]
    for permit, result in zip(ui.permits, ui.results):
        evidence = result.evidence
        assert evidence.step_id == permit.step_id
        assert evidence.action_id == permit.action_id
        assert evidence.execution_id == permit.execution_id
        assert all(traffic.step_id == permit.step_id for traffic in evidence.traffic)


@pytest.mark.parametrize("projection", ["backend", "frontend", "e2e"])
def test_independent_flat_controls_execute_on_real_demo(demo_server, projection):
    """Independent flat business controls, explicitly migrated to current users."""
    path = API_FLAT if projection == "backend" else UI_FLAT
    report, adapters, ui = _run(path, demo_server, projection)
    if ui is not None:
        _assert_ui_lifecycle(ui, report.domains[0], included=False)
    else:
        assert adapters.api.sent == [
            ("POST", "items", {"name": "included-first", "rows": [1, 2, 3]}),
            ("POST", "items", {"name": "1", "rows": [1, 2, 3]}),
            ("PUT", "items/2", {"name": "included-updated"}),
            ("GET", "items", None),
        ]


def _concrete_plan_signature(scenario):
    """Compare instantiated models using fixed distinct source-response evidence.

    No include-expansion function is used to build the expected flat fixture or
    to select its actions. IDs are explicitly mapped by ordered control positions.
    """
    prior, signatures, creations = {}, [], 0
    for step in scenario.steps:
        concrete, _ = prepare_step(step, scenario, prior)
        request = concrete.request
        signatures.append((concrete.action, concrete.target, concrete.value, concrete.duration,
            concrete.poll, concrete.request_asserted,
            None if request is None else (request.method, request.path, request.body),
            [(point, [(a.check, a.params) for a in getattr(concrete.expect, point)])
             for point in ("frontend", "response", "backend_state")]))
        if request is not None and request.method == "POST":
            creations += 1
            prior[step.id] = ports.NormalizedResponse(True, {
                "itemId": creations, "itemKey": str(creations), "name": request.body["name"]},
                200, None)
    return signatures


@pytest.mark.parametrize("included,flat", [(API_INCLUDE, API_FLAT), (UI_INCLUDE, UI_FLAT)])
def test_include_models_match_independently_authored_flat_controls(included, flat):
    assert _concrete_plan_signature(load_scenario(included)) == _concrete_plan_signature(load_scenario(flat))


def test_api_include_reuses_actual_response_and_matches_flat_runtime(demo_server, flat_demo_server):
    included, adapters, _ = _run(API_INCLUDE, demo_server, "backend")
    flat, flat_adapters, _ = _run(API_FLAT, flat_demo_server, "backend")
    assert _report_signature(included) == _report_signature(flat)
    _assert_sources(included, API_INCLUDE, ROOT / "scenarios/include_shared/create_item.yaml",
                    "demo.include_create_item")
    assert adapters.api.sent == flat_adapters.api.sent
    backend, contract = included.domains
    assert [step.step_id for step in backend.steps] == ["first/create", "second/create", "update", "read"]
    assert [record.step_id for record in backend.provider_recordings] == ["first/create", "second/create", "update", "read"]
    assert [record.json["data"]["itemKey"] for record in backend.provider_recordings[:2]] == ["1", "2"]
    assert list(backend.steps[1].resolved_bindings.values()) == ["1"]
    # Three independently named results are read from the real response: the
    # key supplies a later include argument, the ID selects the object, and the
    # original name participates in the list assertion. None is a return script.
    assert list(backend.steps[2].resolved_bindings.values()) == [2]
    assert list(backend.steps[3].resolved_bindings.values()) == [1, "included-first", 2]
    assert contract.status == "PASSED"
    # Qualified IDs, not method/path alone, retain both POST contract entries.
    consumer = store.consumer_contract(load_scenario(API_INCLUDE))
    provider = store.provider_contract(backend.provider_recordings, DemoResponseNormalizer())
    assert set(consumer.entries) == set(provider.entries)
    assert ("first/create", "POST", "items") in consumer.entries
    assert ("second/create", "POST", "items") in consumer.entries
    assert httpx.get(demo_server + "/items").json() == httpx.get(flat_demo_server + "/items").json()


def test_current_named_result_example_executes_create_update_read(demo_server, tmp_path):
    """Current executable copy preserves the historical three-step obligations."""
    example = ROOT / "examples/scenario-reuse"
    shared = tmp_path / "shared"
    shared.mkdir()
    child = shared / "create_item.yaml"
    child.write_bytes((example / "shared/create_item.yaml").read_bytes())
    parent = tmp_path / "create_update_read.yaml"
    parent.write_bytes((example / "create_update_read.yaml").read_bytes())
    parent.with_suffix(".includes.json").write_text(json.dumps({
        "manifest_version": 1,
        "scenarios": {"shared.create_item": {
            "path": "shared/create_item.yaml",
            "sha256": hashlib.sha256(child.read_bytes()).hexdigest(),
        }},
    }), encoding="utf-8")
    report, adapters, _ = _run(parent, demo_server, "backend")
    assert adapters.api.sent == [
        ("POST", "items", {"name": "Test record"}),
        ("PUT", "items/1", {"name": "Updated test record"}),
        ("GET", "items", None),
    ]
    assert [domain.projection for domain in report.domains] == ["backend", "contract"]
    assert [step.step_id for step in report.domains[0].steps] == [
        "create/create_request", "update", "read"]
    assert [record.step_id for record in report.domains[0].provider_recordings] == [
        "create/create_request", "update", "read"]
    assert httpx.get(demo_server + "/items").json()["data"]["items"] == [
        {"id": 1, "name": "Updated test record", "count": 0}]


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_ui_include_reuses_one_context_and_matches_flat_runtime(demo_server, flat_demo_server, projection):
    included, _, ui = _run(UI_INCLUDE, demo_server, projection)
    flat, _, flat_ui = _run(UI_FLAT, flat_demo_server, projection)
    assert _report_signature(included) == _report_signature(flat)
    _assert_sources(included, UI_INCLUDE, ROOT / "scenarios/include_shared/create_item_ui.yaml",
                    "demo.include_create_item_ui")
    domain, flat_domain = included.domains[0], flat.domains[0]
    _assert_ui_lifecycle(ui, domain, included=True)
    _assert_ui_lifecycle(flat_ui, flat_domain, included=False)
    assert [(p.action, p.target, p.value) for p in ui.permits] == [(p.action, p.target, p.value) for p in flat_ui.permits]
    if projection == "frontend":
        fixture_ids = ["initial-list", "create-1", "list-1", "second-open-list", "create-2", "list-2"]
        assert [entry["fixture_id"] for entry in domain.mock_consumption] == fixture_ids
        assert [entry["fixture_id"] for entry in flat_domain.mock_consumption] == fixture_ids
        assert not domain.provider_recordings
        assert httpx.get(demo_server + "/items").json()["data"]["items"] == []
    else:
        assert [record.step_id for record in domain.provider_recordings] == ["first/create", "second/create"]
        assert [record.json["data"]["itemKey"] for record in domain.provider_recordings] == ["1", "2"]
        assert len({record.trace_id for record in domain.provider_recordings}) == 2
        assert all(record.request.method == "POST" for record in domain.provider_recordings)
        assert httpx.get(demo_server + "/items").json()["data"]["items"] == [
            {"id": 1, "name": "included-first", "count": 3},
            {"id": 2, "name": "1", "count": 3},
        ]
    assert httpx.get(demo_server + "/items").json() == httpx.get(flat_demo_server + "/items").json()


def test_ui_child_failure_continues_second_include_with_observed_named_result(demo_server):
    driver = ObservedUi(DemoConfig(base_url=demo_server))
    plan = _ui_plan()
    # A real intercepted response carries an incorrect name. The declaration
    # stays untouched; background list content cannot replace this response.
    plan[1].response["data"]["name"] = "incorrect-response-name"
    report = run_scenario(UI_INCLUDE, build_adapters(demo_server, ui=driver),
                          projections=("frontend",), mock_plan=plan)
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["COMPLETED"] * 3 + ["FAILED"] + ["COMPLETED"] * 3 + ["PASSED"]
    assert driver.opens == driver.closes == 1
    assert len(driver.permits) == 8
    assert all(context is driver.contexts[0] for context in driver.contexts)
    assert all(permit.step_id.startswith("first/") for permit in driver.permits[:4])
    assert all(permit.step_id.startswith("second/") for permit in driver.permits[4:])
    assert [step.after_failures for step in domain.steps[4:]] == [["first/create"]] * 4
    assert list(domain.steps[6].resolved_bindings.values()) == ["1"]
    assert any(projection == "frontend" and step == "first/create" and check == "field_equals"
               for projection, step, point, check, detail in report.localize())
    assert report.source_lookup["first/create"]["scenario_id"] == "demo.include_create_item_ui"
    assert report.source_lookup["first/create"]["include_step_id"] == "first"
    assert [entry["fixture_id"] for entry in domain.mock_consumption] == [
        "initial-list", "create-1", "list-1", "second-open-list", "create-2", "list-2"]
    assert [(check.step, check.check) for check in domain.checks if not check.ok] == [
        ("first/create", "field_equals")]
    assert not domain.provider_recordings  # Mock traffic is not live provider evidence.
    assert httpx.get(demo_server + "/items").json()["data"]["items"] == []
