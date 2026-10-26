"""Run inputs are frozen once; response composition consumes actual evidence."""
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from uuid import UUID

import pytest
import yaml

from refracto import ports, runner
from refracto.declaration.loader import _load_document
from refracto.projection import backend, contract, e2e, frontend
from refracto.query import wire_query
from refracto.report import RunReport
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder, FakeUi
from tests.test_response_field_comparison import document, request, execute
from tests.ui_support import ScriptedUi, rendered, response, run as run_ui


TOKEN = "0123456789ab4def8123456789abcdef"


def composition(*parts):
    return {"concat": list(parts)}


def parameter(name):
    return {"from_parameter": name}


def observed(step, field="code"):
    return {"from_step": step, "response_field": field}


def unique_document(*, ui=False):
    item = request("create", checks=[{"check": "field_equals", "field": "name", "value": parameter("name")}], ui=ui)
    transport = item["expect"]["request"] if ui else item["do"]["request"]
    transport.update(method="POST", path=["records"], body={"name": parameter("name")})
    if ui:
        item["expect"]["ui"] = [{"check": "visible", "anchor": "rows"}]
    return document(item, parameters={"token": {"from_run": "unique"},
        "name": composition(parameter("token"), "-record-", parameter("token"))})


class EchoApi(FakeApi):
    def send(self, spec, session):
        self.responses[(spec.method, spec.path)] = {"status": 201,
            "json": response(copy.deepcopy(spec.body or {}))}
        return super().send(spec, session)


def adapters(api=None, ui=None, auth=None):
    return runner.Adapters(auth=auth or FakeAuth(), api=api or EchoApi(), state=None,
        ui=ui, recorder_factory=FakeRecorder, normalizer=FakeNormalizer(),
        resolve_request=lambda scenario, step, template: ports.RequestSpec(
            template.method, template.path, template.body, query=wire_query(template.query or {}),
            headers=dict(template.headers or {})))


def source_file(tmp_path, raw):
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def test_each_execution_projection_gets_a_unique_value_and_contract_reuses_backend(tmp_path, monkeypatch):
    from refracto.declaration import run_values
    calls = []
    tokens = [TOKEN, "1123456789ab4def8123456789abcdef", "2123456789ab4def8123456789abcdef"]
    def generate():
        value = tokens[len(calls)]
        calls.append("generate")
        return UUID(hex=value)
    monkeypatch.setattr(run_values, "uuid4", generate)
    names = [token + "-record-" + token for token in tokens]
    class CaptureUi(FakeUi):
        def __init__(self):
            super().__init__()
            self.sent = []
        def perform_step(self, scenario, step, context, permit):
            # Fixed test data by execution order, never values from assertions.
            name = names[len(self.sent) + 1]
            spec = ports.RequestSpec("POST", "records", {"name": name})
            self._rendered = rendered(name)
            self._outgoing = [spec]
            self._recorded = [ports.RecordedResponse(201, {}, response({"name": name}), "", None, spec)]
            self.sent.append(copy.deepcopy(step.request))
            return super().perform_step(scenario, step, context, permit)
    ui = CaptureUi()
    api = EchoApi()
    report = runner.run_scenario(source_file(tmp_path, unique_document(ui=True)), adapters(api, ui),
        mock_plan=[ports.MockResponse(fixture_id="create", source="fixed test fixture",
            method="POST", path="records", status=201, response=response({"name": names[1]}))])
    assert calls == ["generate"] * 3
    assert report.run_unique_values == {
        "backend": {"token": tokens[0]}, "frontend": {"token": tokens[1]},
        "e2e": {"token": tokens[2]}, "contract": {"token": tokens[0]}}
    assert report.status == "PASSED", report.localize()
    assert [domain.projection for domain in report.domains] == ["backend", "frontend", "e2e", "contract"]
    assert api.sent[0].body == {"name": names[0]}
    assert len(ui.permits) == 2
    assert [item.body for item in ui.sent] == [{"name": name} for name in names[1:]]
    assert all(token not in repr(report) for token in tokens)
    report.run_unique_values["backend"]["token"] = "modified"
    assert report.run_unique_values["contract"]["token"] == tokens[0]


def test_repeated_and_concurrent_runs_never_mutate_or_reuse_loaded_inputs(monkeypatch):
    loaded = _load_document(unique_document())
    before = copy.deepcopy(loaded)
    monkeypatch.setattr(runner, "load_scenario", lambda path: loaded)
    def run_one(_):
        api = EchoApi()
        report = runner.run_scenario("unused", adapters(api), projections=("backend", "contract"))
        assert report.status == "PASSED"
        token = report.run_unique_values["backend"]["token"]
        assert api.sent[0].body["name"] == token + "-record-" + token
        return token
    sequential = [run_one(None), run_one(None)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = sequential + list(pool.map(run_one, range(8)))
    assert len(set(tokens)) == len(tokens)
    assert all(UUID(hex=token).version == 4 and len(token) == 32 for token in tokens)
    assert loaded == before


def test_validation_filtering_and_plain_runs_do_not_generate(tmp_path, monkeypatch):
    from refracto.declaration import run_values
    from refracto.cli import main
    from refracto.declaration.expansion import expansion_view
    import json
    def forbidden():
        raise AssertionError("token generation not authorized")
    monkeypatch.setattr(run_values, "uuid4", forbidden)
    path = source_file(tmp_path, unique_document())
    assert main(["validate", str(path)]) == 0
    assert main(["validate", str(path), "--expand"]) == 0
    assert "from_run" in json.dumps(expansion_view(_load_document(unique_document())))
    skipped = runner.run_scenario(path, adapters(), projections=("backend", "contract"), module="other")
    assert skipped.status == "NOT_SELECTED" and skipped.run_unique_values == {}
    plain = document(request())
    plain_report = runner.run_scenario(source_file(tmp_path, plain), adapters(), projections=("backend",))
    assert plain_report.status == "PASSED" and plain_report.run_unique_values == {"backend": {}}


def test_run_token_metadata_is_keyword_only_and_hidden_without_exporting_parameters():
    field = next(item for item in fields(RunReport) if item.name == "run_unique_values")
    assert field.kw_only and not field.repr and not field.compare and field.metadata["sensitive"]
    assert "run_unique_values" not in RunReport.__match_args__
    report = RunReport("example", run_unique_values={"backend": {"token": TOKEN}})
    assert TOKEN not in repr(report)
    assert not hasattr(report, "parameters")


@pytest.mark.parametrize("projection", ["backend", "e2e", "frontend", "contract"])
def test_low_level_unbound_run_marker_fails_before_auth_even_when_unused(projection, monkeypatch):
    from refracto.declaration import run_values
    raw = document(request(ui=projection == "frontend"), parameters={"unused": {"from_run": "unique"}})
    scenario = _load_document(raw)
    def forbidden():
        raise AssertionError("low-level projection must not generate")
    monkeypatch.setattr(run_values, "uuid4", forbidden)
    class Auth(FakeAuth):
        calls = []
        def identify(self, user):
            self.calls.append("identify")
            return super().identify(user)
    scenario.users = ["reader"]
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
    assert "run" in result.steps[0].detail.lower()
    assert auth.calls == [] and api.sent == [] and ui.open_calls == 0


def test_explicit_binding_makes_low_level_execution_reusable_without_regeneration(monkeypatch):
    from refracto.declaration.run_values import bind_run_values
    from refracto.declaration import run_values
    original = _load_document(unique_document())
    bound, values = bind_run_values(original)
    token = values["token"]
    def forbidden():
        raise AssertionError("already bound projections must not regenerate")
    monkeypatch.setattr(run_values, "uuid4", forbidden)
    result, _ = execute(bound, api=EchoApi())
    replay = contract.run(bound, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert result.status == replay.status == "PASSED"
    assert bound.parameters["name"] == token + "-record-" + token
    assert original.parameters != bound.parameters


def test_poll_attempts_reuse_the_one_frozen_token(tmp_path, monkeypatch):
    from refracto.declaration import run_values
    calls = []
    monkeypatch.setattr(run_values, "uuid4", lambda: calls.append("generate") or UUID(hex=TOKEN))
    poll = request("ready", checks=[{"check": "field_equals", "field": "ready", "value": True},
        {"check": "field_equals", "field": "token", "value": parameter("token")}],
        poll={"on_timeout": "FAIL"})
    poll["do"]["request"]["query"] = {"token": parameter("token")}
    raw = document(poll, parameters={"token": {"from_run": "unique"}})
    class PollApi(FakeApi):
        def send(self, spec, session):
            self.responses[(spec.method, spec.path)] = {"json": response({
                "ready": bool(self.sent), "token": spec.query["token"]})}
            return super().send(spec, session)
    api, clock = PollApi(), [0.0]
    report = runner.run_scenario(source_file(tmp_path, raw), adapters(api),
        projections=("backend", "contract"), poll_config=runner.PollConfig(timeout=2, interval=1),
        now=lambda: clock[0], sleep=lambda delta: clock.__setitem__(0, clock[0] + delta))
    assert report.status == "PASSED" and calls == ["generate"]
    assert [item.query for item in api.sent] == [{"token": TOKEN}, {"token": TOKEN}]
    assert report.run_unique_values["backend"] == {"token": TOKEN}


def test_repeated_children_default_and_parent_override_keep_separate_sources(tmp_path, monkeypatch):
    from refracto.declaration import run_values
    from tests.test_scenario_named_results import bundle, child, include, named
    calls = []
    tokens = iter([TOKEN, "1123456789ab4def8123456789abcdef"])
    monkeypatch.setattr(run_values, "uuid4", lambda: calls.append("generate") or UUID(hex=next(tokens)))
    child_raw = child()
    child_raw["parameters"] = {"token": {"from_run": "unique"},
        "name": composition(parameter("token"), "-child")}
    child_raw["steps"][0]["expect"]["response"] = [
        {"check": "field_equals", "field": "name", "value": parameter("name")}]
    result_value = composition(named("record_name", "one"), "/", named("record_name", "two"))
    read = request("read", checks=[{"check": "field_equals", "field": "name", "value": result_value}])
    read["do"]["request"]["body"] = {"name": copy.deepcopy(result_value)}
    path, _ = bundle(tmp_path, child_raw=child_raw, parameters={"token": {"from_run": "unique"}},
        steps=[include("one"), include("two", **{"with": {"token": parameter("token")}}), read])
    api = EchoApi()
    report = runner.run_scenario(path, adapters(api), projections=("backend", "contract"))
    assert report.status == "PASSED", report.localize()
    assert calls == ["generate", "generate"]
    values = report.run_unique_values["backend"]
    assert values == {"token": TOKEN, "@include:one:0": "1123456789ab4def8123456789abcdef"}
    first, second = values["@include:one:0"] + "-child", TOKEN + "-child"
    assert [sent.body["name"] for sent in api.sent] == [first, second, first + "/" + second]
    assert [step.step_id for step in report.domains[0].steps] == ["one/create", "two/create", "read"]


def composed_scenario(*, ui=False):
    source = request("account", ui=ui)
    batch = request("batch", ui=ui)
    value = composition(observed("account"), "-document-", observed("batch"))
    consume = request("consume", checks=[{"check": "field_equals", "field": "name", "value": value}], ui=ui)
    transport = consume["expect"]["request"] if ui else consume["do"]["request"]
    transport["body"] = {"name": value}
    independent = request("independent", ui=ui)
    return _load_document(document(source, batch, consume, independent))


@pytest.mark.parametrize("bad", [None, 0, False, [], {}, "MISSING"])
@pytest.mark.parametrize("mode", ["backend", "e2e"])
def test_unusable_response_operand_blocks_only_consumer_atomically(bad, mode):
    scenario = composed_scenario()
    result, api = execute(scenario, {"account": {"code": "actual-account"},
        "batch": {} if bad == "MISSING" else {"code": bad}}, mode=mode)
    assert [step.status for step in result.steps] == ["PASSED", "PASSED", "BLOCKED", "PASSED"]
    assert result.steps[2].resolved_bindings == {} and result.steps[2].blocked_by == ["batch"]
    assert [sent.path for sent in api.sent] == ["account", "batch", "independent"]
    checked = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert checked.status == "DEGRADED"
    assert any(step.step_id == "consume" and step.status == "BLOCKED" for step in checked.steps)


@pytest.mark.parametrize("mode", ["mock", "live"])
@pytest.mark.parametrize("bad", [None, 0, False, [], {}, "MISSING"])
def test_ui_composition_failure_never_issues_consumer_permit(mode, bad):
    scenario = composed_scenario(ui=True)
    payloads = [response({"code": "actual-account"}), response({} if bad == "MISSING" else {"code": bad}), response()]
    requests = [[ports.RequestSpec("GET", path)] for path in ("account", "batch", "independent")]
    ui = ScriptedUi(count=3, payloads=payloads, requests=requests)
    result = run_ui(scenario, ui, mode=mode)
    assert [step.status for step in result.steps] == ["PASSED", "PASSED", "BLOCKED", "PASSED"]
    assert [permit.step_id for permit in ui.permits] == ["account", "batch", "independent"]
    assert result.steps[2].resolved_bindings == {}
    assert ui.close_calls == ui.open_calls == 1


@pytest.mark.parametrize("mode", ["mock", "live"])
def test_ui_composition_uses_both_actual_response_sources(mode):
    scenario = composed_scenario(ui=True)
    combined = "actual-account-document-actual-batch"
    payloads = [response({"code": "actual-account"}), response({"code": "actual-batch"}),
                response({"name": combined}), response()]
    requests = [[ports.RequestSpec("GET", path,
        {"name": combined} if path == "consume" else None)]
        for path in ("account", "batch", "consume", "independent")]
    ui = ScriptedUi(count=4, payloads=payloads, requests=requests)
    result = run_ui(scenario, ui, mode=mode)
    assert result.status == "PASSED"
    assert [permit.step_id for permit in ui.permits] == ["account", "batch", "consume", "independent"]
    sources = result.steps[2].binding_sources
    assert {item.origin.step_id for item in sources.values()} == {"account", "batch"}
    assert ui.close_calls == ui.open_calls == 1


@pytest.mark.parametrize("alteration", ["wrong-string", "missing", "null", "number", "bool", "list", "dict"])
def test_contract_composition_uses_actual_sources_not_downstream_expected_substitutes(alteration):
    scenario = composed_scenario()
    combined = "actual-account-document-actual-batch"
    result, _ = execute(scenario, {"account": {"code": "actual-account"},
        "batch": {"code": "actual-batch"}, "consume": {"name": combined}})
    assert result.status == "PASSED"
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"
    changed = copy.deepcopy(result.provider_recordings)
    if alteration == "missing":
        changed[1].json["data"].pop("code")
    else:
        changed[1].json["data"]["code"] = {"wrong-string": "other", "null": None,
            "number": 1, "bool": False, "list": [], "dict": {}}[alteration]
    for provenance in (None, result.steps):
        replay = contract.run(scenario, changed, FakeNormalizer(), execution_steps=provenance)
        assert replay.status == "FAILED"
        if alteration == "wrong-string":
            assert any(check.step == "consume" and not check.ok for check in replay.checks)
        else:
            assert any(step.step_id == "consume" and step.status == "ERROR" for step in replay.steps)
    assert changed[2].json["data"]["name"] == combined


def test_run_value_and_composed_response_sensitive_values_hidden_in_default_reports():
    scenario = composed_scenario()
    sentinel = "private-composition-sentinel"
    result, _ = execute(scenario, {"account": {"code": sentinel},
        "batch": {"code": "batch"}, "consume": {"name": sentinel + "-document-batch"}})
    report = RunReport(scenario.id, [result], run_unique_values={"backend": {"token": sentinel}})
    assert result.status == "PASSED"
    assert sentinel not in repr(report)
    sources = result.steps[2].binding_sources
    assert {item.origin.step_id for item in sources.values()} == {"account", "batch"}
