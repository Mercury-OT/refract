"""One UTC base spans projections and attempts without changing polling time."""
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from threading import Lock

import pytest

from refracto import ports, runner
from refracto.declaration import run_values
from refracto.declaration.loader import _load_document
from refracto.declaration.model import Scenario
from refracto.declaration.run_values import bind_run_values
from refracto.projection import backend, contract, e2e, frontend
from refracto.report import RunReport
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder, FakeUi
from tests.test_response_field_comparison import document, request
from tests.test_run_values_runtime import adapters, EchoApi, parameter, source_file
from tests.ui_support import ScriptedUi, rendered, response


BASE = "2026-10-24T08:00:00.123Z"
BASE_DT = datetime(2026, 10, 24, 8, 0, 0, 123999, timezone.utc)


def time_document(ui=False):
    item = request("create", checks=[
        {"check": "status_equals", "value": 201},
        {"check": "field_equals", "field": "name", "value": parameter("name")}], ui=ui)
    transport = item["expect"]["request"] if ui else item["do"]["request"]
    transport.update(method="POST", path=["records"], body={"name": parameter("name")})
    return document(item, parameters={"name": {"from_run": "time"}})


def test_clock_read_once_and_truncated_base_shared_across_all_four_projections(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run_values, "_utc_now", lambda: calls.append("clock") or BASE_DT)
    spec = ports.RequestSpec("POST", "records", {"name": BASE})
    recorded = ports.RecordedResponse(201, {}, response({"name": BASE}), "", None, spec)
    ui = FakeUi(rendered=rendered(BASE), outgoing=[spec], recorded=[recorded])
    api = EchoApi()
    report = runner.run_scenario(source_file(tmp_path, time_document(ui=True)), adapters(api, ui),
        mock_plan=[ports.MockResponse(fixture_id="create", source="fixed clock fixture", method="POST",
            path="records", status=201, response=response({"name": BASE}))])
    assert calls == ["clock"]
    assert report.status == "PASSED" and report.degradations() == []
    assert [d.projection for d in report.domains] == ["backend", "frontend", "e2e", "contract"]
    assert report.run_time == BASE and report.run_time_source == "actual"
    assert report.run_time_values == {"name": BASE} and report.run_unique is None
    assert api.sent[0].body["name"] == BASE
    assert len(ui.permits) == 2
    assert BASE not in repr(report)


def test_fixed_time_is_repeatable_without_reading_clock_or_reusing_unique_token(tmp_path, monkeypatch):
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("fixed time read the clock"))
    raw = time_document()
    raw["parameters"]["token"] = {"from_run": "unique"}
    path = source_file(tmp_path, raw)
    first = runner.run_scenario(path, adapters(), projections=("backend", "contract"), run_time=BASE)
    second = runner.run_scenario(path, adapters(), projections=("backend", "contract"), run_time=BASE)
    assert first.status == second.status == "PASSED"
    assert first.run_time == second.run_time == BASE
    assert first.run_time_source == second.run_time_source == "fixed"
    assert first.run_time_values == second.run_time_values == {"name": BASE}
    assert first.run_unique != second.run_unique
    first.run_time_values["name"] = "changed"
    assert second.run_time_values == {"name": BASE}


def test_repeated_concurrent_runs_freeze_independent_copies(monkeypatch):
    loaded = _load_document(time_document())
    before = copy.deepcopy(loaded)
    monkeypatch.setattr(runner, "load_scenario", lambda path: loaded)
    lock, ticks = Lock(), []
    def clock():
        with lock:
            instant = BASE_DT + timedelta(seconds=len(ticks))
            ticks.append(instant)
            return instant
    monkeypatch.setattr(run_values, "_utc_now", clock)
    def execute(_):
        api = EchoApi()
        report = runner.run_scenario("unused", adapters(api), projections=("backend", "contract"))
        assert report.status == "PASSED"
        assert api.sent[0].body["name"] == report.run_time_values["name"] == report.run_time
        return report
    first = execute(None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        reports = [first, *pool.map(execute, range(8))]
    assert len(ticks) == len(reports) == 9
    assert len({report.run_time for report in reports}) == 9
    assert loaded == before and loaded.run_time is None and loaded.run_time_values == {}


def test_validation_filtering_and_plain_runs_do_not_read_wall_clock(tmp_path, monkeypatch):
    from refracto.cli import main
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("clock read without execution"))
    path = source_file(tmp_path, time_document())
    assert main(["validate", str(path)]) == 0
    assert main(["validate", str(path), "--expand"]) == 0
    skipped = runner.run_scenario(path, adapters(), projections=("backend",), module="other")
    assert skipped.status == "NOT_SELECTED" and skipped.run_time is None
    assert skipped.run_time_values == {} and skipped.run_time_source is None
    raw = time_document()
    raw["parameters"]["name"] = "plain"
    plain = runner.run_scenario(source_file(tmp_path, raw), adapters(), projections=("backend",), run_time=BASE)
    assert plain.status == "PASSED" and plain.run_time is None and plain.run_time_values == {}


@pytest.mark.parametrize("base", ["sensitive-invalid-time", True, {}, "2026-02-29T00:00:00.000Z"])
@pytest.mark.parametrize("with_marker", [False, True])
def test_invalid_fixed_time_is_a_configuration_error_before_any_port_call(tmp_path, monkeypatch, base, with_marker):
    class Auth(FakeAuth):
        def identify(self, user):
            pytest.fail("invalid fixed time reached authentication")
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("invalid fixed time fell back to clock"))
    raw = time_document()
    raw["users"] = ["editor"]
    if not with_marker:
        raw["parameters"]["name"] = "plain"
    api = EchoApi()
    with pytest.raises(ValueError) as error:
        runner.run_scenario(source_file(tmp_path, raw), adapters(api, auth=Auth()),
                            projections=("backend",), run_time=base)
    assert api.sent == [] and "sensitive-invalid-time" not in str(error.value)


def test_offset_overflow_prevents_authentication_and_transport(tmp_path):
    class Auth(FakeAuth):
        def identify(self, user):
            pytest.fail("overflow reached authentication")
    raw = time_document()
    raw["users"] = ["editor"]
    raw["parameters"]["name"] = {"from_run": "time", "offset": {"days": 1}}
    api = EchoApi()
    with pytest.raises(ValueError, match="overflows"):
        runner.run_scenario(source_file(tmp_path, raw), adapters(api, auth=Auth()),
                            projections=("backend",), run_time="9999-12-31T23:59:59.999Z")
    assert api.sent == []


@pytest.mark.parametrize("field_name", ["run_time", "run_time_source", "run_time_values"])
@pytest.mark.parametrize("model", [Scenario, RunReport])
def test_time_evidence_is_keyword_only_sensitive_and_hidden(model, field_name):
    item = next(item for item in fields(model) if item.name == field_name)
    assert item.kw_only and not item.repr and not item.compare and item.metadata["sensitive"]
    assert field_name not in model.__match_args__


@pytest.mark.parametrize("projection", ["backend", "e2e", "frontend", "contract"])
def test_unbound_time_is_rejected_before_ports_even_when_unused(projection, monkeypatch):
    raw = document(request(ui=projection == "frontend"), parameters={"unused": {"from_run": "time"}})
    raw["users"] = ["reader"]
    scenario = _load_document(raw)
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("projection read clock"))
    class Auth(FakeAuth):
        calls = []
        def identify(self, user):
            self.calls.append("identify")
            return super().identify(user)
    auth, api, ui = Auth(), EchoApi(), ScriptedUi(count=1)
    if projection == "contract":
        result = contract.run(scenario, [], FakeNormalizer())
    elif projection == "frontend":
        result = frontend.run(scenario, ui=ui, auth=auth, normalizer=FakeNormalizer(), mock_plan=ui.plan())
    elif projection == "e2e":
        result = e2e.run(scenario, ui=None, auth=auth, api=api, state=None,
            recorder=FakeRecorder(), normalizer=FakeNormalizer(), resolve_request=adapters().resolve_request)
    else:
        result = backend.run(scenario, auth=auth, api=api, state=None,
            recorder=FakeRecorder(), normalizer=FakeNormalizer(), resolve_request=adapters().resolve_request)
    assert result.status == "FAILED" and result.steps[0].status == "ERROR"
    assert auth.calls == [] and api.sent == [] and ui.open_calls == 0


def test_polling_keeps_base_and_uses_its_separate_monotonic_clock(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run_values, "_utc_now", lambda: calls.append("wall") or BASE_DT)
    step = request("ready", checks=[{"check": "field_equals", "field": "ready", "value": True},
        {"check": "field_equals", "field": "time", "value": parameter("time")}], poll={"on_timeout": "FAIL"})
    step["do"]["request"]["query"] = {"time": parameter("time")}
    raw = document(step, parameters={"time": {"from_run": "time"}})
    class PollApi(FakeApi):
        def send(self, spec, session):
            self.responses[(spec.method, spec.path)] = {"json": response({
                "ready": bool(self.sent), "time": spec.query["time"]})}
            return super().send(spec, session)
    api, monotonic = PollApi(), [0.0]
    report = runner.run_scenario(source_file(tmp_path, raw), adapters(api),
        projections=("backend", "contract"), poll_config=runner.PollConfig(timeout=2, interval=1),
        now=lambda: monotonic[0], sleep=lambda amount: monotonic.__setitem__(0, monotonic[0] + amount))
    assert calls == ["wall"] and monotonic == [1.0]
    assert report.status == "PASSED"
    assert [spec.query for spec in api.sent] == [{"time": BASE}, {"time": BASE}]


def test_frozen_low_level_contract_replays_without_resampling(monkeypatch):
    from tests.test_response_field_comparison import execute
    scenario, _ = bind_run_values(_load_document(time_document()), run_time=BASE)
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("contract read wall clock"))
    result, _ = execute(scenario, api=EchoApi())
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert result.status == replay.status == "PASSED"
    assert scenario.run_time == BASE


def test_unused_time_is_still_frozen_and_clock_failure_is_sanitized(tmp_path, monkeypatch):
    raw = document(request(), parameters={"unused": {"from_run": "time"}})
    monkeypatch.setattr(run_values, "_utc_now", lambda: BASE_DT)
    report = runner.run_scenario(source_file(tmp_path, raw), adapters(), projections=("backend",))
    assert report.run_time == BASE and report.run_time_values == {"unused": BASE}
    def broken():
        raise RuntimeError("sensitive-clock-detail")
    monkeypatch.setattr(run_values, "_utc_now", broken)
    with pytest.raises(ValueError) as error:
        runner.run_scenario(source_file(tmp_path, raw), adapters(), projections=("backend",))
    assert "sensitive" not in str(error.value)
