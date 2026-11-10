"""Synthetic local upload inputs, ownership, composition and offline evidence."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os

import pytest
import yaml

from refracto import ports
from refracto.declaration.expansion import expansion_view, flow_expansion_view
from refracto.declaration.loader import DeclarationError, load_scenario, load_flow
from refracto.declaration.impact import inspect_impact
from refracto.files import FileConfig
from refracto.projection import backend, contract
from refracto.report import BLOCKED, ERROR, PASSED
from refracto.runner import Adapters, run_scenario, run_flow
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.test_action_port_boundary import inspect_operation_data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def declaration(data=b"local\x00\xffdata", *, asset="asset.bin", body=None):
    request = {"method": "POST", "path": ["uploads"],
               "files": {"attachment": {"path": asset, "sha256": digest(data)}}}
    if body is not None:
        request["body"] = body
    return {"schema_version": 1, "scenario": "uploads.fixed", "users": [],
            "steps": [{"id": "upload", "do": {"request": request},
                       "expect": {"response": [{"check": "status_equals", "value": 200}]}}]}


def write(tmp_path, raw=None, *, data=b"local\x00\xffdata", name="scenario.yaml"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw = declaration(data) if raw is None else raw
    (tmp_path / "asset.bin").write_bytes(data)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def resolve(action):
    return ports.RequestSpec(action.method, action.path, deepcopy(action.body),
        query=deepcopy(action.query or {}), headers=deepcopy(action.headers or {}),
        files=deepcopy(action.files))


class UploadApi(FakeApi):
    def supports_file_upload(self):
        return True


def adapters(api=None, *, resolver=resolve, auth=None, normalizer=None, recorder=None):
    return Adapters(auth or FakeAuth(), api or UploadApi(), None, None,
                    recorder or FakeRecorder, resolver, normalizer or FakeNormalizer())


@pytest.mark.parametrize("data", [b"", b"plain\n", b"\x00\xff\x80\x01", bytes(range(256))])
def test_binary_and_empty_snapshots_are_immutable_owned_values(tmp_path, data):
    scenario = load_scenario(write(tmp_path, data=data))
    request = scenario.steps[0].request
    asset = request.files["attachment"]
    assert (asset.filename, asset.data, asset.sha256) == ("asset.bin", data, digest(data))
    assert request._file_base is None
    with pytest.raises(FrozenInstanceError):
        asset.data = b"replacement"
    assert "asset.bin" not in repr(asset)
    assert repr(data) not in repr(asset)


@pytest.mark.parametrize("files", [None, {}, [], {"one": {}, "two": {}},
    {"bad field": {}}, {"attachment": None},
    {"attachment": {"path": "asset.bin"}},
    {"attachment": {"path": "asset.bin", "sha256": "0" * 64, "mime": "text/plain"}},
    {"attachment": {"path": {"from_parameter": "asset"}, "sha256": "0" * 64}},
    {"attachment": {"path": "asset.bin", "sha256": "A" * 64}},
    {"attachment": {"path": "asset.bin", "sha256": 1}},
    {"attachment": {"path": "asset.bin", "sha256": "a" * 63}},
    {"attachment": {"path": "asset.bin", "sha256": {"from_parameter": "hash"}}}])
def test_invalid_file_shapes_fail_without_opening_assets(tmp_path, files, monkeypatch):
    raw = declaration()
    raw["steps"][0]["do"]["request"]["files"] = files
    path = write(tmp_path, raw)
    monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("asset opened before syntax validation"))
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("path", ["/asset.bin", "../asset.bin", "a/../asset.bin", "a//b",
    "./asset.bin", "a/./b", "*.bin", "[a].bin", "a?b", "https://example.com/a",
    "a\\b", "~a", "$asset", "asset\x00.bin", "asset\n.bin", ""])
def test_unsafe_file_paths_fail(tmp_path, path):
    raw = declaration(asset=path)
    with pytest.raises(DeclarationError):
        load_scenario(write(tmp_path, raw))


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo", "missing", "parent-symlink"])
def test_only_regular_non_symlink_assets_can_be_read(tmp_path, kind):
    path = write(tmp_path)
    asset = tmp_path / "asset.bin"
    asset.unlink()
    if kind == "symlink":
        (tmp_path / "real.bin").write_bytes(b"local\x00\xffdata")
        asset.symlink_to("real.bin")
    elif kind == "directory":
        asset.mkdir()
    elif kind == "fifo":
        os.mkfifo(asset)
    elif kind == "parent-symlink":
        (tmp_path / "actual").mkdir()
        (tmp_path / "actual/asset.bin").write_bytes(b"local\x00\xffdata")
        (tmp_path / "linked").symlink_to("actual", target_is_directory=True)
        raw = declaration(asset="linked/asset.bin")
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("value", [0, -1, True, False, 1.0, "1", None])
@pytest.mark.parametrize("field", ["max_file_bytes", "max_total_bytes"])
def test_strict_host_budgets(field, value):
    with pytest.raises(ValueError):
        FileConfig(**{field: value})


def test_exact_budget_reuse_and_before_read_size_bound(tmp_path, monkeypatch):
    data = b"1234"
    raw = declaration(data)
    raw["steps"].append({**deepcopy(raw["steps"][0]), "id": "again"})
    path = write(tmp_path, raw, data=data)
    scenario = load_scenario(path, file_config=FileConfig(max_file_bytes=4, max_total_bytes=4))
    assert scenario.steps[0].request.files["attachment"] is scenario.steps[1].request.files["attachment"]
    monkeypatch.setattr(os, "read", lambda *a, **k: pytest.fail("oversized file read"))
    for config in (FileConfig(max_file_bytes=3), FileConfig(max_total_bytes=3)):
        with pytest.raises(DeclarationError, match="budget"):
            load_scenario(path, file_config=config)


def test_changed_file_is_rejected_on_reload_but_loaded_snapshot_survives(tmp_path):
    path = write(tmp_path)
    scenario = load_scenario(path)
    (tmp_path / "asset.bin").write_bytes(b"substituted")
    api = UploadApi()
    result = backend.run(scenario, auth=FakeAuth(), api=api, state=None,
                         recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert result.status == PASSED
    assert api.sent[0].files["attachment"].data == b"local\x00\xffdata"
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_scenario(path)


@pytest.mark.parametrize("body", [{"title": 1}, {"title": False}, {"title": None},
    {"title": ["x"]}, {"title": {"x": "y"}}, {"attachment": "collision"}])
def test_upload_text_fields_are_flat_strings(tmp_path, body):
    with pytest.raises(DeclarationError):
        load_scenario(write(tmp_path, declaration(body=body)))


def test_invalid_later_ui_files_rejected_before_any_asset_open(tmp_path, monkeypatch):
    raw = declaration()
    raw["steps"].append({"id": "ui", "do": "click", "target": "upload",
        "expect": {"request": deepcopy(raw["steps"][0]["do"]["request"])}})
    path = write(tmp_path, raw)
    monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("asset opened before UI rejection"))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_upload_cannot_be_polled(tmp_path):
    raw = declaration()
    raw["steps"][0]["do"]["request"]["method"] = "GET"
    raw["steps"][0]["poll"] = {"on_timeout": "FAIL"}
    with pytest.raises(DeclarationError):
        load_scenario(write(tmp_path, raw))


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("support", [False, 1, "yes", None, "raise"])
def test_capability_preflight_precedes_auth_and_all_actions(tmp_path, projection, support):
    raw = declaration()
    raw["users"] = ["editor"]
    raw["steps"].insert(0, {"id": "earlier", "do": {"request": {"method": "GET", "path": ["earlier"]}}})

    class Api(UploadApi):
        def supports_file_upload(self):
            if support == "raise":
                raise ValueError("PRIVATE FILE CONTENT")
            return support

    class Auth(FakeAuth):
        def session(self, user):
            pytest.fail("authentication before capability preflight")

    api = Api()
    result = run_scenario(write(tmp_path, raw), adapters(api, auth=Auth()), projections=(projection,))
    assert any(step.status == ERROR for domain in result.domains for step in domain.steps)
    assert not api.sent
    assert "PRIVATE FILE CONTENT" not in str(result)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("value", [0, False, [], {}, None, "valid"])
def test_runtime_text_reference_blocks_only_invalid_consumer(tmp_path, projection, value):
    raw = declaration(body={"title": {"from_step": "source", "response_field": "title"}})
    raw["steps"].insert(0, {"id": "source", "do": {"request": {"method": "GET", "path": ["source"]}},
                           "expect": {"response": [{"check": "status_equals", "value": 200}]}})
    api = UploadApi({("GET", "source"): {"json": {"title": value}}})
    result = run_scenario(write(tmp_path, raw), adapters(api), projections=(projection,))
    steps = result.domains[0].steps
    assert steps[0].status == PASSED
    assert steps[1].status == (PASSED if value == "valid" else BLOCKED)
    assert len(api.sent) == (2 if value == "valid" else 1)


@pytest.mark.parametrize("mutation", ["omit", "add", "bytes", "filename", "digest", "nested"])
def test_resolver_cannot_change_file_mapping_or_nested_asset(tmp_path, mutation):
    def mapping(action):
        inspect_operation_data(action)
        assert not hasattr(action, "expect")
        if mutation == "omit":
            return replace(resolve(action), files=None)
        asset = action.files["attachment"]
        if mutation == "add":
            action.files["extra"] = asset
        elif mutation == "nested":
            object.__setattr__(asset, "data", b"substitution")
        else:
            changes = {"bytes": {"data": b"substitution", "sha256": digest(b"substitution")},
                       "filename": {"filename": "different.bin"}, "digest": {"sha256": "0" * 64}}[mutation]
            action.files["attachment"] = replace(asset, **changes)
        return resolve(action)

    api = UploadApi()
    result = run_scenario(write(tmp_path), adapters(api, resolver=mapping), projections=("backend",))
    assert any(step.status == ERROR for domain in result.domains for step in domain.steps)
    assert not api.sent


@pytest.mark.parametrize("boundary", ["driver", "normalizer", "recorder"])
def test_recording_file_tampering_is_an_error(tmp_path, boundary):
    def tamper(response):
        object.__setattr__(response.request.files["attachment"], "data", b"changed")

    class Api(UploadApi):
        def send(self, spec, session):
            result = super().send(spec, session)
            if boundary == "driver":
                tamper(result)
            return result

    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            if boundary == "normalizer":
                tamper(response)
            return super().normalize(response)

    class Recorder(FakeRecorder):
        def record(self, response):
            if boundary == "recorder":
                tamper(response)
            super().record(response)

    result = run_scenario(write(tmp_path), adapters(Api(), normalizer=Normalizer(), recorder=Recorder),
                          projections=("backend", "contract"))
    assert any(step.status == ERROR for domain in result.domains for step in domain.steps)


@pytest.mark.parametrize("boundary", ["resolver", "driver", "normalizer", "recorder"])
def test_sensitive_upload_port_errors_are_sanitized(tmp_path, boundary):
    secret = "private-filename.bin PRIVATE BYTES"

    def mapping(action):
        if boundary == "resolver":
            raise ValueError(secret)
        return resolve(action)

    class Api(UploadApi):
        def send(self, spec, session):
            if boundary == "driver":
                raise ValueError(secret)
            return super().send(spec, session)

    class Normalizer(FakeNormalizer):
        def normalize(self, response):
            if boundary == "normalizer":
                raise ValueError(secret)
            return super().normalize(response)

    class Recorder(FakeRecorder):
        def record(self, response):
            if boundary == "recorder":
                raise ValueError(secret)
            super().record(response)

    result = run_scenario(write(tmp_path), adapters(Api(), resolver=mapping, normalizer=Normalizer(), recorder=Recorder),
                          projections=("backend",))
    assert any(step.status == ERROR for domain in result.domains for step in domain.steps)
    assert secret not in str(result)


def test_offline_contract_checks_bytes_filename_and_digest(tmp_path):
    path = write(tmp_path)
    scenario = load_scenario(path)
    api = UploadApi()
    result = backend.run(scenario, auth=FakeAuth(), api=api, state=None,
                         recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert contract.run(scenario, result.provider_recordings, FakeNormalizer()).status == PASSED
    for changes in ({"data": b"wrong"}, {"filename": "wrong.bin"}, {"sha256": "0" * 64}):
        recordings = deepcopy(result.provider_recordings)
        asset = recordings[0].request.files["attachment"]
        recordings[0].request.files["attachment"] = replace(asset, **changes)
        assert contract.run(scenario, recordings, FakeNormalizer()).steps[0].status == ERROR
    assert len(api.sent) == 1


def include_parent(tmp_path, child, *, count=2):
    raw = {"schema_version": 1, "scenario": "parent", "users": [],
           "steps": [{"id": f"use{i}", "do": {"include": "uploads.fixed"}} for i in range(count)]}
    path = tmp_path / "parent.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {"uploads.fixed": {"path": str(child.relative_to(tmp_path)),
                                        "sha256": digest(child.read_bytes())}}}), encoding="utf-8")
    return path


def test_child_relative_files_and_reuse_budget_expansion_and_pins(tmp_path):
    data = b"child"
    child = write(tmp_path / "child", data=data)
    (tmp_path / "asset.bin").write_bytes(b"parent")
    parent = include_parent(tmp_path, child)
    scenario = load_scenario(parent, file_config=FileConfig(max_total_bytes=len(data)))
    assert [step.request.files["attachment"].data for step in scenario.steps] == [data, data]
    view = expansion_view(scenario)
    assert view["steps"][0]["do"]["request"]["files"] == {
        "attachment": {"path": "asset.bin", "sha256": digest(data)}}
    encoded = json.dumps(view)
    assert str(tmp_path) not in encoded
    assert "data" not in view["steps"][0]["do"]["request"]["files"]["attachment"]
    (child.parent / "asset.bin").write_bytes(b"wrong")
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_scenario(parent)
    child.write_text(child.read_text() + "\n", encoding="utf-8")
    with pytest.raises(DeclarationError, match="dependency fingerprint"):
        load_scenario(parent)


def test_total_budget_spans_parent_and_child(tmp_path):
    child = write(tmp_path / "child", data=b"child")
    parent = include_parent(tmp_path, child, count=1)
    raw = yaml.safe_load(parent.read_text())
    raw["steps"] += declaration(b"parent")["steps"]
    parent.write_text(yaml.safe_dump(raw), encoding="utf-8")
    (tmp_path / "asset.bin").write_bytes(b"parent")
    with pytest.raises(DeclarationError, match="budget"):
        load_scenario(parent, file_config=FileConfig(max_total_bytes=10))
    assert len(load_scenario(parent, file_config=FileConfig(max_total_bytes=11)).steps) == 2


def test_flow_reuses_child_snapshot_and_total_budget(tmp_path):
    child = write(tmp_path / "child", data=b"child")
    flow = tmp_path / "flow.yaml"
    flow.write_text(yaml.safe_dump({"schema_version": 1, "flow": "uploads.flow", "users": [],
        "scenarios": [{"id": "first", "scenario": "uploads.fixed"},
                      {"id": "second", "scenario": "uploads.fixed"}]}), encoding="utf-8")
    flow.with_suffix(".scenarios.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {"uploads.fixed": {"path": "child/scenario.yaml", "sha256": digest(child.read_bytes())}}}),
        encoding="utf-8")
    loaded = load_flow(flow, file_config=FileConfig(max_total_bytes=5))
    assert all(step.request.files["attachment"].data == b"child" for step in loaded.scenario.steps)
    assert "asset.bin" in json.dumps(flow_expansion_view(loaded))
    api = UploadApi()
    result = run_flow(flow, adapters(api), projections=("backend", "contract"),
                      file_config=FileConfig(max_total_bytes=5))
    assert result.status == PASSED
    assert len(api.sent) == 2
    with pytest.raises(DeclarationError, match="budget"):
        load_flow(flow, file_config=FileConfig(max_total_bytes=4))


def test_impact_checks_source_relative_uploads_without_serializing_bytes(tmp_path):
    before = write(tmp_path / "before", data=b"before secret")
    after = write(tmp_path / "after", data=b"after secret")
    parent = include_parent(tmp_path, after, count=1)
    report = inspect_impact(before, after, tmp_path, show_values=True)
    assert report["status"] == "COMPLETE"
    assert report["parents"][0]["validity"]["actual"] == "valid"
    rendered = json.dumps(report)
    assert "before secret" not in rendered and "after secret" not in rendered
    assert any("/files/attachment/sha256" in change["location"] for change in report["changes"])
    assert parent.exists()


def test_action_transport_inventory_and_repr_contains_no_source_or_sensitive_data(tmp_path):
    raw = declaration(body={"title": "PRIVATE TITLE"})
    seen = []

    def mapping(action):
        seen.append(action)
        data = inspect_operation_data(action)
        assert set(data["files"]["attachment"]) == {"filename", "data", "sha256"}
        assert "path" not in data["files"]["attachment"]
        return resolve(action)

    path = write(tmp_path, raw)
    api = UploadApi()
    assert run_scenario(path, adapters(api, resolver=mapping), projections=("backend",)).status == PASSED
    for value in [seen[0], api.sent[0], load_scenario(path).steps[0].request]:
        assert "PRIVATE TITLE" not in repr(value)
        assert "asset.bin" not in repr(value)
        assert str(tmp_path) not in repr(value)


def test_file_free_legacy_driver_does_not_need_capability(tmp_path):
    raw = declaration()
    del raw["steps"][0]["do"]["request"]["files"]
    assert run_scenario(write(tmp_path, raw), adapters(FakeApi()), projections=("backend", "contract")).status == PASSED


def test_method_ownership_error_does_not_repeat_adapter_filename(tmp_path):
    def mapping(action):
        return replace(resolve(action), method=action.files["attachment"].filename)

    api = UploadApi()
    result = run_scenario(write(tmp_path), adapters(api, resolver=mapping), projections=("backend",))
    assert result.domains[0].steps[0].status == ERROR
    assert "asset.bin" not in result.domains[0].steps[0].detail
    assert not api.sent


def test_unsupported_secure_snapshot_platform_fails_closed_only_for_files(tmp_path, monkeypatch):
    path = write(tmp_path)
    monkeypatch.delattr(os, "O_NOFOLLOW")
    with pytest.raises(DeclarationError, match="unsupported on this platform"):
        load_scenario(path)
    raw = declaration()
    del raw["steps"][0]["do"]["request"]["files"]
    assert load_scenario(write(tmp_path, raw)).steps[0].request.files is None


def test_direct_api_helper_validates_actual_supplied_step_before_auth(tmp_path):
    scenario = load_scenario(write(tmp_path))
    wrong = deepcopy(scenario.steps[0])
    wrong.request.body = {"title": 12}

    class Auth(FakeAuth):
        def session(self, user):
            pytest.fail("authentication before supplied upload validation")

    scenario.users = ["editor"]
    with pytest.raises(ValueError, match="strings"):
        backend.execute_api_step(scenario, wrong, auth=Auth(), api=UploadApi(), state=None,
            recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
