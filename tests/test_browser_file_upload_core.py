"""Fixed browser-file declarations and core evidence boundaries, without a browser."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import json
import os

import pytest
import yaml

from refracto import ports
from refracto.declaration.expansion import expansion_view, flow_expansion_view
from refracto.declaration.impact import inspect_impact
from refracto.declaration.loader import DeclarationError, load_scenario, load_flow
from refracto.declaration.model import Expect, RequestTemplate
from refracto.files import FileConfig
from refracto.projection import backend, contract
from refracto.report import StepResult
from refracto.runner import run_scenario, run_flow
from tests.fakes import FakeApi, FakeNormalizer, FakeRecorder
from tests.test_action_port_boundary import inspect_operation_data
from tests.test_file_upload_core import adapters, digest, include_parent, resolve, UploadApi, write
from tests.test_users_sessions_core import Auth
from tests.ui_support import ScriptedUi, run


DATA = b"local\x00\xffdata"


def descriptor(data=DATA):
    return {"path": "asset.bin", "sha256": digest(data)}


def select(**extra):
    return {"id": "select", "do": "select_file", "target": "documents.attachment_input",
            "file": descriptor(), "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}, **extra}


def submit(**extra):
    return {"id": "submit", "do": "click", "target": "documents.submit", "expect": {
        "request": {"method": "POST", "path": ["uploads"], "body": {"title": "example"},
                    "files": {"attachment": descriptor()}},
        "response": [{"check": "status_equals", "value": 200}]}, **extra}


def document(*steps, data=DATA):
    result = {"schema_version": 1, "scenario": "uploads.fixed", "users": ["editor"],
              "steps": list(steps) or [select(), submit()]}
    for step in result["steps"]:
        if "file" in step:
            step["file"] = descriptor(data)
        if "files" in step.get("expect", {}).get("request", {}):
            step["expect"]["request"]["files"] = {"attachment": descriptor(data)}
    return result


def load(tmp_path, *steps, data=DATA):
    return load_scenario(write(tmp_path, document(*steps, data=data), data=data))


class UploadUi(ScriptedUi):
    def __init__(self, scenario, *, observed=None):
        self.selection_mutate = None
        requests = [[] if step.request is None else [ports.RequestSpec(
            step.request.method, step.request.path, deepcopy(step.request.body),
            files=deepcopy(step.request.files))] for step in scenario.steps]
        if observed is not None:
            requests[-1][0].files = observed
        super().__init__(count=len(scenario.steps), requests=requests)

    def supports_file_selection(self, mode):
        return mode in {"live", "mock"}

    def supports_file_requests(self, mode):
        return mode in {"live", "mock"}

    def perform_step(self, context, permit, **kwargs):
        result = super().perform_step(context, permit, **kwargs)
        if permit.action == "select_file" and result.evidence is not None:
            result = replace(result, evidence=replace(result.evidence,
                file_selection=ports.UiFileSelection(target_matches=1, file=deepcopy(permit.file))))
        if self.selection_mutate:
            result = self.selection_mutate(result, permit)
        self.evidence[-1] = result
        return result


@pytest.mark.parametrize("data", [b"", b"text\n", DATA, bytes(range(256))])
def test_selection_and_submission_share_one_frozen_budgeted_asset(tmp_path, data):
    path = write(tmp_path, document(data=data), data=data)
    scenario = load_scenario(path, file_config=FileConfig(max_file_bytes=max(1, len(data)),
                                                       max_total_bytes=max(1, len(data))))
    chosen, submitted = scenario.steps
    assert chosen.file is submitted.request.files["attachment"]
    assert chosen.file.data == data and chosen._file_base is None
    view = expansion_view(scenario)
    assert view["steps"][0]["file"] == descriptor(data)
    assert view["steps"][1]["expect"]["request"]["files"] == {"attachment": descriptor(data)}
    assert "data" not in view["steps"][0]["file"]
    (tmp_path / "asset.bin").unlink()
    assert run(scenario, UploadUi(scenario)).status == "PASSED"


@pytest.mark.parametrize("change", [
    {"file": None}, {"file": {}}, {"file": []}, {"file": {"from_parameter": "asset"}},
    {"file": {"path": "asset.bin"}}, {"file": {"path": "../asset.bin", "sha256": "0" * 64}},
    {"file": {"path": "asset.bin", "sha256": "0" * 64, "mime": "text/plain"}},
    {"target": None}, {"target": ""}, {"target": {"from_parameter": "asset"}},
    {"value": None}, {"key": None}, {"duration": None}, {"object_id": None},
    {"poll": {}}, {"object_poll": {"on_timeout": "FAIL"}},
    {"expect": {"request": {"method": "POST", "path": ["uploads"]}}},
    {"expect": {"response": []}}, {"expect": {"backend_state": []}},
])
def test_invalid_selection_syntax_is_rejected_before_asset_reads(tmp_path, monkeypatch, change):
    raw = document(select(), submit())
    raw["steps"][0].update(change)
    path = write(tmp_path, raw)
    monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("asset read before syntax validation"))
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("missing", ["target", "file"])
def test_selection_requires_literal_target_and_file(tmp_path, missing):
    raw = document()
    del raw["steps"][0][missing]
    with pytest.raises(DeclarationError):
        load_scenario(write(tmp_path, raw))


@pytest.mark.parametrize("action,extra", [("open", {}), ("fill", {"value": "x"}),
    ("press", {"key": "Enter"}), ("hover", {}), ("wait", {"duration": 0})])
def test_files_are_only_supported_on_click_requests(tmp_path, action, extra):
    step = submit(do=action, **extra)
    if action == "wait":
        step.pop("target")
    with pytest.raises(DeclarationError):
        load_scenario(write(tmp_path, document(step)))


@pytest.mark.parametrize("action", ["open", "click", "fill", "press", "hover", "wait"])
def test_selection_file_cannot_be_placed_on_other_actions(tmp_path, action):
    raw = document()
    raw["steps"][0]["do"] = action
    with pytest.raises(DeclarationError):
        load_scenario(write(tmp_path, raw))


@pytest.mark.parametrize("capability", ["supports_file_selection", "supports_file_requests"])
@pytest.mark.parametrize("answer", [False, 1, "yes", None, "raise"])
@pytest.mark.parametrize("mode", ["live", "mock"])
def test_later_file_capability_failure_precedes_all_effects(tmp_path, capability, answer, mode):
    scenario = load(tmp_path, {"id": "open", "do": "open", "target": "documents.page"}, select(), submit())
    ui, auth = UploadUi(scenario), Auth()
    def support(_mode):
        if answer == "raise":
            raise ValueError("private filename or content")
        return answer
    setattr(ui, capability, support)
    result = run(scenario, ui, mode=mode, auth=auth)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED", "BLOCKED"]
    assert ui.open_calls == 0 and not ui.permits and not auth.identified and not auth.authenticated
    assert "private filename or content" not in str(result)


def test_new_capabilities_are_false_by_default():
    ui = ScriptedUi()
    assert ui.supports_file_selection("live") is False
    assert ui.supports_file_requests("mock") is False


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_browser_files_never_require_or_use_api_upload_capability(tmp_path, mode):
    scenario = load(tmp_path)
    api = FakeApi()
    kwargs = {"api": api, "resolve_request": resolve} if mode == "live" else {}
    result = run(scenario, UploadUi(scenario), mode=mode, **kwargs)
    assert result.status == "PASSED" and api.sent == []


@pytest.mark.parametrize("change", [{"target_matches": 0}, {"target_matches": 2},
    {"target_matches": True}, {"target_matches": 1.0}, {"file": None}, {"file": "asset.bin"},
    {"file": ports.UploadFile(filename="asset.bin", data=b"wrong", sha256="0" * 64)},
    {"file": ports.UploadFile(filename="wrong.bin", data=DATA, sha256=digest(DATA))},
    {"file": ports.UploadFile(filename="asset.bin", data=b"wrong", sha256=digest(b"wrong"))}])
def test_malformed_or_wrong_selection_receipt_errors_and_blocks(tmp_path, change):
    scenario = load(tmp_path)
    ui = UploadUi(scenario)
    ui.selection_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        file_selection=replace(result.evidence.file_selection, **change)))
    result = run(scenario, ui)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert result.steps[0].file_selection is None


@pytest.mark.parametrize("replacement", [None, {}, "selection"])
def test_missing_selection_receipt_is_error(tmp_path, replacement):
    scenario = load(tmp_path, select())
    ui = UploadUi(scenario)
    ui.selection_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, file_selection=replacement))
    assert run(scenario, ui).steps[0].status == "ERROR"


def test_selection_cannot_skip(tmp_path):
    scenario = load(tmp_path)
    ui = UploadUi(scenario)
    ui.selection_mutate = lambda result, permit: ports.UiActionResult(skip_reason="unavailable")
    assert [step.status for step in run(scenario, ui).steps] == ["ERROR", "BLOCKED"]


@pytest.mark.parametrize("field,value", [("user", "other"), ("context_id", "other"),
    ("session_generation", 7), ("action_id", "other"), ("step_id", "other"), ("execution_id", "other")])
def test_selection_receipts_cannot_override_origin(tmp_path, field, value):
    scenario = load(tmp_path, select())
    ui = UploadUi(scenario)
    ui.selection_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, **{field: value}))
    assert run(scenario, ui).steps[0].status == "ERROR"


@pytest.mark.parametrize("change", ["replace", "bytes", "digest", "filename"])
def test_permit_signature_binds_actual_frozen_file(tmp_path, change):
    scenario = load(tmp_path, select())
    ui = UploadUi(scenario)
    def mutate(result, permit):
        if change == "replace":
            object.__setattr__(permit, "file", ports.UploadFile(filename="asset.bin", data=b"new", sha256=digest(b"new")))
        else:
            field, value = {"bytes": ("data", b"new"), "digest": ("sha256", "0" * 64),
                            "filename": ("filename", "new.bin")}[change]
            object.__setattr__(permit.file, field, value)
        return result
    ui.selection_mutate = mutate
    assert run(scenario, ui).steps[0].status == "ERROR"
    assert scenario.steps[0].file.data == DATA


@pytest.mark.parametrize("kind", ["missing", "bytes", "name", "field", "empty"])
@pytest.mark.parametrize("mode", ["live", "mock"])
def test_complete_wrong_or_missing_observed_file_is_failed_request_check(tmp_path, kind, mode):
    scenario = load(tmp_path, submit())
    ui = UploadUi(scenario)
    original = ui.requests[0][0].files["attachment"]
    observed = None if kind == "missing" else {"wrong" if kind == "field" else "attachment": replace(
        original, **({"filename": "other.bin"} if kind == "name" else
                    {"data": b"", "sha256": digest(b"")} if kind == "empty" else
                    {"data": b"wrong", "sha256": digest(b"wrong")} if kind == "bytes" else {}))}
    ui.requests[0][0].files = observed
    result = run(scenario, ui, mode=mode)
    assert result.steps[0].status == "FAILED"
    assert [check.ok for check in result.steps[0].checks if check.point == "request"] == [False]


@pytest.mark.parametrize("observed", [{}, {"attachment": "file"},
    {"attachment": ports.UploadFile(filename="asset.bin", data=DATA, sha256="0" * 64)},
    {"attachment": ports.UploadFile(filename="../asset.bin", data=DATA, sha256=digest(DATA))},
    {"attachment": ports.UploadFile(filename="asset.bin", data=bytearray(DATA), sha256=digest(DATA))}])
def test_malformed_observed_file_is_error(tmp_path, observed):
    scenario = load(tmp_path, submit())
    ui = UploadUi(scenario, observed=observed)
    assert run(scenario, ui).steps[0].status == "ERROR"


def test_other_actions_cannot_claim_file_selection(tmp_path):
    scenario = load(tmp_path, submit())
    ui = UploadUi(scenario)
    ui.selection_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        file_selection=ports.UiFileSelection(target_matches=1, file=scenario.steps[0].request.files["attachment"])))
    assert run(scenario, ui).steps[0].status == "ERROR"


def test_selection_associated_traffic_is_error_not_later_click_evidence(tmp_path):
    scenario = load(tmp_path)
    ui = UploadUi(scenario)
    ui.requests[0] = deepcopy(ui.requests[1])
    assert [step.status for step in run(scenario, ui).steps] == ["ERROR", "BLOCKED"]


def test_selection_action_port_is_safe_and_contains_no_submission_expectation(tmp_path):
    scenario = load(tmp_path)
    ui = UploadUi(scenario)
    def inspect(result, permit):
        operation = inspect_operation_data(permit)
        assert not {"expect", "request", "parameters", "steps", "file_descriptor", "_file_base"} & set(operation)
        if permit.action == "select_file":
            assert set(operation["file"]) == {"filename", "data", "sha256"}
        else:
            assert operation["file"] is None
        assert "asset.bin" not in repr(permit) + repr(result)
        return result
    ui.selection_mutate = inspect
    result = run(scenario, ui)
    receipt = result.steps[0].file_selection
    assert result.status == "PASSED" and "asset.bin" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        receipt.file = None
    assert ports.UiFileSelection.__match_args__ == ()
    assert "file_selection" not in StepResult.__match_args__
    assert StepResult("s", "PASSED", file_selection=receipt) == StepResult("s", "PASSED")
    for cls in (ports.UiActionEvidence, StepResult):
        field = next(item for item in fields(cls) if item.name == "file_selection")
        assert not field.repr and field.metadata["sensitive"]


def test_retained_selection_receipt_cannot_mutate_report_or_next_permit(tmp_path):
    scenario = load(tmp_path)
    ui = UploadUi(scenario)
    def mutate(result, permit):
        if permit.action == "click":
            object.__setattr__(ui.evidence[0].evidence.file_selection.file, "data", b"late mutation")
        return result
    ui.selection_mutate = mutate
    result = run(scenario, ui)
    assert result.status == "PASSED"
    assert result.steps[0].file_selection.file.data == DATA
    assert scenario.steps[0].file.data == DATA
    assert result.provider_recordings[0].request.files["attachment"].data == DATA


def test_backend_projects_only_explicit_click_request_and_contract_reuses_it(tmp_path):
    scenario = load(tmp_path)
    adapter = adapters()
    result = backend.run(scenario, auth=adapter.auth, api=adapter.api, state=None,
        recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert [step.status for step in result.steps] == ["NOT_APPLICABLE", "PASSED"]
    assert len(adapter.api.sent) == 1 and adapter.api.sent[0].files["attachment"].data == DATA
    assert result.steps[0].not_checked and result.steps[0].file_selection is None
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps).status == "PASSED"


def test_projected_click_requires_api_capability_before_auth(tmp_path):
    scenario = load(tmp_path)
    auth, api = Auth(), FakeApi()
    result = backend.run(scenario, auth=auth, api=api, state=None,
        recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert not auth.identified and not auth.authenticated and not api.sent


def test_selection_only_backend_and_contract_are_empty(tmp_path):
    path = write(tmp_path, document(select()))
    report = run_scenario(path, adapters(), projections=("backend", "contract"))
    assert report.status == "EMPTY"
    assert [domain.status for domain in report.domains] == ["EMPTY", "EMPTY"]
    assert report.domains[0].steps[0].not_checked
    assert report.domains[1].not_checked


def test_include_and_flow_share_asset_budget_and_preserve_declaring_directory(tmp_path):
    raw = document()
    raw["users"] = []
    child = write(tmp_path / "child", raw)
    (tmp_path / "asset.bin").write_bytes(b"wrong parent")
    parent = include_parent(tmp_path, child)
    scenario = load_scenario(parent, file_config=FileConfig(max_total_bytes=len(DATA)))
    assert [step.file.data for step in scenario.steps if step.action == "select_file"] == [DATA, DATA]
    flow = tmp_path / "flow.yaml"
    flow.write_text(yaml.safe_dump({"schema_version": 1, "flow": "upload.flow", "users": [],
        "scenarios": [{"id": "first", "scenario": "parent"}, {"id": "second", "scenario": "parent"}]}))
    flow.with_suffix(".scenarios.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {"parent": {"path": "parent.yaml", "sha256": digest(parent.read_bytes()),
            "includes_sha256": digest(parent.with_suffix(".includes.json").read_bytes())}}}))
    loaded = load_flow(flow, file_config=FileConfig(max_total_bytes=len(DATA)))
    selections = [step for step in loaded.scenario.steps if step.action == "select_file"]
    assert len(selections) == 4 and all(step.file.data == DATA for step in selections)
    assert str(tmp_path) not in json.dumps(flow_expansion_view(loaded))
    with pytest.raises(DeclarationError, match="budget"):
        load_flow(flow, file_config=FileConfig(max_total_bytes=len(DATA) - 1))


def test_impact_review_snapshots_selection_asset_without_exposing_bytes(tmp_path):
    raw = document(select())
    raw["users"] = []
    before = write(tmp_path / "before", raw)
    after_raw = document(select(), data=b"after secret")
    after_raw["users"] = []
    after = write(tmp_path / "after", after_raw, data=b"after secret")
    include_parent(tmp_path, after, count=1)
    report = inspect_impact(before, after, tmp_path, show_values=True)
    assert report["status"] == "COMPLETE"
    assert report["parents"][0]["validity"]["actual"] == "valid"
    assert "after secret" not in json.dumps(report)
    assert any("/file/sha256" in change["location"] for change in report["changes"])


@pytest.mark.parametrize("mutator", ["recorder", "normalizer", "paired-response"])
@pytest.mark.parametrize("change", ["drop", "bytes", "name", "field", "digest"])
def test_browser_request_file_evidence_is_owned_across_ports(tmp_path, mutator, change):
    scenario = load(tmp_path, submit())
    ui = UploadUi(scenario)
    def corrupt(request):
        original = request.files["attachment"]
        if change == "drop":
            request.files = None
        elif change == "field":
            request.files = {"other": original}
        else:
            replacement = {"bytes": {"data": b"wrong", "sha256": digest(b"wrong")},
                           "name": {"filename": "wrong.bin"}, "digest": {"sha256": "0" * 64}}[change]
            request.files = {"attachment": replace(original, **replacement)}
    class Recorder(FakeRecorder):
        def record(self, response):
            corrupt(response.request)
            return super().record(response)
    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            corrupt(response.request)
            return super().normalize(response)
    kwargs = {}
    if mutator == "recorder":
        kwargs["recorder"] = Recorder()
    elif mutator == "normalizer":
        kwargs["normalizer"] = Normalizer()
    else:
        def mutate(result, permit):
            copied = deepcopy(result)
            # Break only the response copy, not the separately observed request.
            traffic = copied.evidence.traffic[0]
            response = replace(traffic.response, request=deepcopy(traffic.response.request))
            corrupt(response.request)
            return replace(copied, evidence=replace(copied.evidence,
                traffic=[replace(traffic, response=response)]))
        ui.selection_mutate = mutate
    result = run(scenario, ui, **kwargs)
    assert result.steps[0].status == "ERROR"
    assert scenario.steps[0].request.files["attachment"].data == DATA


@pytest.mark.parametrize("seam", ["normalizer", "record", "responses", "action", "close", "snapshot"])
def test_file_data_from_adapter_exceptions_never_enters_diagnostics(tmp_path, seam):
    steps = [select(), submit()]
    if seam == "snapshot":
        steps.append({"id": "wait", "do": "wait", "duration": 0,
                      "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}})
    scenario = load(tmp_path, *steps)
    ui = UploadUi(scenario)
    secret = "private-file-content"
    def fail(*args, **kwargs):
        raise ValueError(secret)
    normalizer, recorder = FakeNormalizer(), FakeRecorder()
    if seam == "normalizer":
        normalizer.normalize = fail
    elif seam in {"record", "responses"}:
        setattr(recorder, seam, fail)
    else:
        setattr(ui, {"action": "perform_step", "close": "close_stepwise", "snapshot": "snapshot"}[seam], fail)
    result = run(scenario, ui, normalizer=normalizer, recorder=recorder)
    assert any(step.status == "ERROR" for step in result.steps)
    assert secret not in str(result) + " ".join(step.detail for step in result.steps)


@pytest.mark.parametrize("field,value", [("value", "wrong"), ("key", "Enter"), ("duration", 1),
    ("object_id", "one"), ("request", RequestTemplate("POST", "uploads")),
    ("request_asserted", True), ("file", None), ("file", "private content")])
def test_invalid_python_selection_is_rejected_before_auth_or_context(tmp_path, field, value):
    scenario = load(tmp_path)
    scenario.steps[0] = replace(scenario.steps[0], **{field: value})
    ui, auth = UploadUi(scenario), Auth()
    result = run(scenario, ui, auth=auth)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert not ui.permits and ui.open_calls == 0 and not auth.identified


@pytest.mark.parametrize("stop", [False, True])
def test_observed_wrong_file_uses_existing_failure_continuation(tmp_path, stop):
    step = submit()
    if stop:
        step["on_failure"] = "stop"
    scenario = load(tmp_path, step, {"id": "later", "do": "click", "target": "next",
        "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}})
    ui = UploadUi(scenario)
    ui.requests[0][0].files = None
    assert [step.status for step in run(scenario, ui).steps] == ["FAILED", "BLOCKED" if stop else "PASSED"]


def test_selection_and_click_survive_flow_boundary_in_same_browser_context(tmp_path):
    first = write(tmp_path / "first", document(select()))
    second_raw = document(submit())
    second_raw["scenario"] = "uploads.submit"
    second = write(tmp_path / "second", second_raw)
    path = tmp_path / "flow.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "flow": "uploads.flow", "users": ["editor"],
        "scenarios": [{"id": "choose", "scenario": "uploads.fixed", "with_users": {"editor": "editor"}},
                      {"id": "submit", "scenario": "uploads.submit", "with_users": {"editor": "editor"}}]}))
    path.with_suffix(".scenarios.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {"uploads.fixed": {"path": "first/scenario.yaml", "sha256": digest(first.read_bytes())},
                      "uploads.submit": {"path": "second/scenario.yaml", "sha256": digest(second.read_bytes())}}}))
    ui = UploadUi(load_flow(path).scenario)
    adapter = replace(adapters(), ui=ui)
    result = run_flow(path, adapter, projections=("e2e",))
    assert result.status == "PASSED"
    assert ui.open_calls == ui.close_calls == 1
    assert len({permit.context_id for permit in ui.permits}) == 1
    assert result.scenarios[0].domains[0].steps[0].file_selection.file.data == DATA


@pytest.mark.parametrize("filename", ['quoted"name.bin', 'literal%22.bin', 'literal%0a.bin', 'literal%0D.bin'])
@pytest.mark.parametrize("selection", [False, True])
def test_ambiguous_browser_filename_is_rejected_before_effects_but_api_stays_supported(tmp_path, filename, selection):
    scenario = load(tmp_path, select() if selection else submit())
    step = scenario.steps[0]
    if selection:
        step.file = replace(step.file, filename=filename)
    else:
        step.request.files = {"attachment": replace(step.request.files["attachment"], filename=filename)}
    ui, auth = UploadUi(scenario), Auth()
    result = run(scenario, ui, auth=auth)
    assert result.steps[0].status == "ERROR"
    assert ui.open_calls == 0 and not auth.identified and not auth.authenticated
    if not selection:
        api = UploadApi()
        backend_result = backend.run(scenario, auth=Auth(), api=api, state=None,
            recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
        assert backend_result.status == "PASSED"
        assert api.sent[0].files["attachment"].filename == filename


def test_unambiguous_literal_percent_filename_keeps_exact_spelling(tmp_path):
    scenario = load(tmp_path)
    scenario.steps[0].file = replace(scenario.steps[0].file, filename="report%20.bin")
    scenario.steps[1].request.files = {"attachment": replace(
        scenario.steps[1].request.files["attachment"], filename="report%20.bin")}
    assert run(scenario, UploadUi(scenario)).status == "PASSED"
