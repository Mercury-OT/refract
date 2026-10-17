"""Synthetic identity, declaration and authentication-provenance controls."""
import copy
import hashlib
import json
from dataclasses import fields, replace

import pytest
import yaml

from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.ports import NormalizedResponse, RecordedResponse, RequestSpec, UserSession
from refracto.projection import backend, contract
from refracto.projection.sessions import SessionError, SessionManager
from refracto.report import BLOCKED, ERROR, FAILED, PASSED, RunReport


def document(users=None, steps=None):
    return {"schema_version": 1, "scenario": "synthetic.users", "users": ["owner"] if users is None else users,
            "steps": steps or [request("read")]}


def request(sid, user=None, *, session=None, status=200, body=None):
    value = {"id": sid, "do": {"request": {"method": "POST" if body else "GET", "path": ["records"]}},
             "expect": {"response": [{"check": "status_equals", "value": status}]}}
    if body:
        value["do"]["request"]["body"] = body
    if user is not None:
        value["user"] = user
    if session is not None:
        value["session"] = session
    return value


class Auth:
    def __init__(self):
        self.identified = []
        self.authenticated = []

    def identify(self, user):
        self.identified.append(user)
        return "sensitive-principal:" + user

    def session(self, user):
        self.authenticated.append(user)
        return UserSession(principal_id="sensitive-principal:" + user,
            authentication_id="sensitive-auth:" + str(len(self.authenticated)),
            credentials={"user": user, "credential": "sensitive-credential"})


class Api:
    def __init__(self, statuses=None, data=None):
        self.calls = []
        self.statuses = iter(statuses or [])
        self.data = iter(data or [])

    def send(self, spec, session):
        self.calls.append((copy.deepcopy(spec), session))
        return RecordedResponse(next(self.statuses, 200), {}, next(self.data, {"id": "r1"}), "", None,
            copy.deepcopy(spec), user="untrusted", session_generation=999)


class Recorder:
    def __init__(self):
        self.items = []

    def record(self, response):
        self.items.append(response)

    def responses(self):
        return self.items


class Normalizer:
    def normalize(self, response):
        return NormalizedResponse(response.status < 400, response.json or {}, response.status, response)


def run(raw, *, auth=None, api=None, normalizer=None, poll_config=None, now=None, sleep=None, recorder=None):
    scenario = _load_document(raw)
    auth = Auth() if auth is None else auth
    api = api or Api()
    recorder = recorder or Recorder()
    result = backend.run(scenario, auth=auth, api=api, recorder=recorder, state=None,
        normalizer=normalizer or Normalizer(),
        resolve_request=lambda scenario, step, template: RequestSpec(template.method, template.path, template.body),
        poll_config=poll_config, now=now, sleep=sleep)
    return scenario, result, auth, api


@pytest.mark.parametrize("users", [None, "owner", {}, [""], [" "], [1], [False], [{}], ["owner", "owner"]])
def test_users_strict(users):
    raw = document()
    raw["users"] = users
    with pytest.raises(DeclarationError):
        _load_document(raw)


def test_users_required_actor_rejected_and_no_role_metadata():
    raw = document()
    del raw["users"]
    with pytest.raises(DeclarationError):
        _load_document(raw)
    raw["actor"] = "owner"
    with pytest.raises(DeclarationError):
        _load_document(raw)
    with pytest.raises(DeclarationError):
        _load_document(document([{"name": "owner", "role": "member"}]))


@pytest.mark.parametrize("step", [request("x"), {"id": "wait", "do": "wait", "duration": 0},
                                 {"id": "setup", "do": {"include": "shared"}}])
def test_multiuser_requires_user_on_every_step(step):
    with pytest.raises(DeclarationError, match="every step"):
        _load_document(document(["owner", "peer"], [step]))


@pytest.mark.parametrize("user", ["unknown", "", 0, False, {"from_parameter": "name"}])
def test_literal_declared_step_user(user):
    raw = document()
    raw["steps"][0]["user"] = user
    with pytest.raises(DeclarationError):
        _load_document(raw)


@pytest.mark.parametrize("session", ["reuse", "old", 1, False, None, {}, ""])
def test_only_explicit_new_session(session):
    raw = document()
    raw["steps"][0]["session"] = session
    with pytest.raises(DeclarationError):
        _load_document(raw)


@pytest.mark.parametrize("extra", [{"user": None}, {"user": "owner"}, {"session": "new"}])
def test_anonymous_rejects_identity_fields(extra):
    raw = document([])
    raw["steps"][0].update(extra)
    with pytest.raises(DeclarationError):
        _load_document(raw)


def test_single_omission_and_anonymous_no_authentication():
    assert _load_document(document()).steps[0].user == "owner"
    class NoAuthentication:
        def identify(self, user):
            raise AssertionError("anonymous must not identify")
        def session(self, user):
            raise AssertionError("anonymous must not authenticate")
    scenario, result, _, api = run(document([]), auth=NoAuthentication())
    assert result.status == PASSED
    assert api.calls[0][1] is None
    assert result.steps[0].user is None and result.steps[0].session_generation == 0
    assert contract.run(scenario, result.provider_recordings, Normalizer()).status == PASSED


@pytest.mark.parametrize("auth", [object(), type("Legacy", (), {"session": lambda self, user: {}})(),
    type("Duplicate", (Auth,), {"identify": lambda self, user: "same"})(),
    type("Invalid", (Auth,), {"identify": lambda self, user: False})()])
def test_preflight_identity_errors_have_zero_business_actions(auth):
    raw = document(["owner", "peer"], [request("owner", "owner"), request("peer", "peer")])
    _, result, _, api = run(raw, auth=auth)
    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert not api.calls
    assert all(step.session_generation is None for step in result.steps)


def test_fixed_users_lazy_sessions_reuse_and_explicit_new():
    raw = document(["owner", "peer"], [request("a", "owner"), request("b", "peer"),
        request("c", "owner"), request("d", "owner", session="new"), request("e", "peer")])
    _, result, auth, api = run(raw)
    assert result.status == PASSED
    assert auth.identified == ["owner", "peer"]
    assert auth.authenticated == ["owner", "peer", "owner"]
    assert [s.session_generation for s in result.steps] == [1, 1, 1, 2, 1]
    assert api.calls[0][1] is api.calls[2][1]
    assert api.calls[0][1] is not api.calls[3][1]
    assert [r.user for r in result.provider_recordings] == ["owner", "peer", "owner", "owner", "peer"]
    assert [r.session_generation for r in result.provider_recordings] == [1, 1, 1, 2, 1]


@pytest.mark.parametrize("bad", ["principal", "reused", "malformed", "throws"])
def test_reauthentication_protocol_failures_stop_without_send(bad):
    class Broken(Auth):
        def session(self, user):
            result = super().session(user)
            if len(self.authenticated) == 1:
                return result
            if bad == "principal":
                return replace(result, principal_id="another-principal")
            if bad == "reused":
                return replace(result, authentication_id="sensitive-auth:1")
            if bad == "throws":
                raise ValueError("secret-auth-exception")
            return {"credentials": "secret-auth-exception"}
    _, result, _, api = run(document(steps=[request("a"), request("b", session="new"), request("c")]), auth=Broken())
    assert [s.status for s in result.steps] == [PASSED, ERROR, BLOCKED]
    assert len(api.calls) == 1
    assert "secret-auth-exception" not in result.steps[1].detail


def test_failed_check_does_not_refresh_and_new_comparison_runs():
    _, result, auth, _ = run(document(steps=[request("old", status=403),
        request("new", session="new", status=403)]), api=Api([200, 403]))
    assert [s.status for s in result.steps] == [FAILED, PASSED]
    assert result.steps[1].after_failures == ["old"]
    assert auth.authenticated == ["owner", "owner"]


def test_blocked_reference_does_not_authenticate_or_replace():
    raw = document(["owner", "peer"], [request("a", "owner"),
        request("b", "peer", session="new", body={"id": {"from_step": "a", "response_field": "missing"}}),
        request("c", "owner")])
    _, result, auth, _ = run(raw)
    assert [s.status for s in result.steps] == [PASSED, BLOCKED, PASSED]
    assert result.steps[1].session_generation is None
    assert auth.authenticated == ["owner"]


def test_dependency_blocked_wait_does_not_replace_session_or_sleep():
    raw = document(steps=[request("source"), {"id": "wait", "do": "wait", "duration": 1,
        "session": "new", "expect": {"ui": [{"check": "objects_matching_count", "anchor": "records",
        "field": "id", "value": {"from_step": "source", "response_field": "missing"}, "count": 1}]}}])
    sleeps = []
    _, result, auth, _ = run(raw, sleep=sleeps.append)
    assert result.steps[1].status == BLOCKED
    assert auth.authenticated == ["owner"]
    assert not sleeps


def test_cross_user_response_provenance_and_sensitive_repr():
    raw = document(["owner", "peer"], [request("a", "owner"),
        request("b", "peer", body={"id": {"from_step": "a", "response_field": "id"}})])
    scenario, result, auth, _ = run(raw, api=Api(data=[{"id": "sensitive-value"}, {}]))
    source = next(iter(result.steps[1].binding_sources.values()))
    assert source.origin.user == "owner" and source.origin.session_generation == 1
    assert result.steps[1].user == "peer"
    report = RunReport(scenario.id, [result])
    for text in [repr(report), repr(auth.session("owner"))]:
        assert "sensitive-principal" not in text
        assert "sensitive-auth" not in text
        assert "sensitive-credential" not in text
        assert "sensitive-value" not in text
    assert all(not f.repr and f.metadata["sensitive"] for f in fields(UserSession))


def test_normalizer_cannot_rewrite_recording_user_or_generation():
    class Mutation(Normalizer):
        def normalize(self, response):
            response.user = "peer"
            response.session_generation = 900
            return super().normalize(response)
    _, result, _, _ = run(document(), normalizer=Mutation())
    assert [(r.user, r.session_generation) for r in result.provider_recordings] == [("owner", 1)]


@pytest.mark.parametrize("changes", [{"user": "peer"}, {"session_generation": None},
                                    {"session_generation": False}, {"session_generation": 0}])
def test_contract_rejects_wrong_or_missing_user_attribution(changes):
    scenario, result, auth, _ = run(document())
    recording = replace(result.provider_recordings[0], **changes)
    before = list(auth.authenticated)
    assert contract.run(scenario, [recording], Normalizer()).steps[0].status == ERROR
    assert auth.authenticated == before


def test_contract_rejects_stale_generation_for_same_user_after_new():
    scenario, result, _, _ = run(document(steps=[request("old"), request("new", session="new")]))
    assert contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=result.steps).status == PASSED
    assert contract.run(scenario, result.provider_recordings, Normalizer()).steps[0].status == ERROR
    recordings = list(result.provider_recordings)
    recordings[-1] = replace(recordings[-1], session_generation=1)
    assert contract.run(scenario, recordings, Normalizer(), execution_steps=result.steps).steps[0].status == ERROR


def test_contract_rejects_duplicate_or_type_confused_execution_provenance():
    scenario, result, _, _ = run(document())
    duplicate = result.steps + [replace(result.steps[0], session_generation=2)]
    assert contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=duplicate).steps[0].status == ERROR
    invalid = [replace(result.steps[0], session_generation=True)]
    assert contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=invalid).steps[0].status == ERROR


def test_polling_reuses_one_session_and_keeps_generation_on_all_attempts():
    from refracto.runner import PollConfig
    raw = document()
    raw["steps"][0]["poll"] = {"on_timeout": "FAIL"}
    clock = [0]
    def sleep(duration):
        clock[0] += duration
    _, result, auth, api = run(raw, api=Api([202, 200]), poll_config=PollConfig(timeout=2, interval=1),
        now=lambda: clock[0], sleep=sleep)
    assert result.status == PASSED
    assert auth.authenticated == ["owner"]
    assert len(api.calls) == 2
    assert [(r.user, r.session_generation) for r in result.provider_recordings] == [("owner", 1), ("owner", 1)]
    assert result.steps[0].response_origin.session_generation == 1


def include_files(tmp_path, *, child_users=None, parent_users=None):
    child = document(["operator"] if child_users is None else child_users)
    child["scenario"] = "shared.create"
    child["steps"][0]["session"] = "new" if child["users"] else None
    if not child["users"]:
        del child["steps"][0]["session"]
    if len(child["users"]) > 1:
        child["steps"][0]["user"] = child["users"][0]
    child["results"] = {"record_id": {"from_step": "read", "response_field": "id"}}
    child_path = tmp_path / "child.yaml"
    child_path.write_text(yaml.safe_dump(child))
    parent = document(["owner", "peer"] if parent_users is None else parent_users)
    parent["steps"] = [{"id": "first", "do": {"include": "shared.create"}},
                       {"id": "second", "do": {"include": "shared.create"}}]
    if parent["users"]:
        parent["steps"][0]["user"] = parent["users"][0]
        parent["steps"][1]["user"] = parent["users"][-1]
    path = tmp_path / "parent.yaml"
    path.write_text(yaml.safe_dump(parent))
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {"shared.create": {"path": "child.yaml",
        "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}))
    return path, child_path


def test_single_child_alias_maps_to_two_users_without_editing_child(tmp_path):
    path, child_path = include_files(tmp_path)
    original = child_path.read_bytes()
    scenario = load_scenario(str(path))
    assert [s.user for s in scenario.steps] == ["owner", "peer"]
    assert [s.session for s in scenario.steps] == ["new", "new"]
    assert scenario.included_results["first"]["record_id"].from_step == "first/read"
    assert scenario.source_lookup["first/read"]["source_user"] == "operator"
    assert scenario.source_lookup["second/read"]["effective_user"] == "peer"
    assert expansion_view(scenario)["steps"][1]["user"] == "peer"
    assert child_path.read_bytes() == original


@pytest.mark.parametrize("child,parent", [(["one", "two"], ["owner"]), ([], ["owner"]), (["operator"], [])])
def test_include_rejects_unsupported_user_mapping(tmp_path, child, parent):
    path, _ = include_files(tmp_path, child_users=child, parent_users=parent)
    with pytest.raises(DeclarationError):
        load_scenario(str(path))


def test_anonymous_child_and_parent_and_include_override_rejection(tmp_path):
    path, _ = include_files(tmp_path, child_users=[], parent_users=[])
    assert load_scenario(str(path)).users == []
    raw = yaml.safe_load(path.read_text())
    raw["steps"][0]["session"] = "new"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(DeclarationError):
        load_scenario(str(path))


def test_python_constructor_does_not_bypass_identity_preflight():
    scenario = _load_document(document())
    scenario.steps[0].user = "undeclared"
    with pytest.raises(SessionError):
        SessionManager(scenario, Auth()).preflight()


@pytest.mark.parametrize("mutation", ["user", "generation", "boolean-generation", "body"])
def test_recorder_cannot_mutate_recorded_values_during_append(mutation):
    class TamperingRecorder(Recorder):
        def record(self, response):
            if mutation == "user":
                response.user = "peer"
            elif mutation == "generation":
                response.session_generation = 44
            elif mutation == "boolean-generation":
                response.session_generation = True
            else:
                response.json["id"] = "forged"
            super().record(response)
    _, result, _, api = run(document(steps=[request("first"), request("next")]), recorder=TamperingRecorder())
    assert [s.status for s in result.steps] == [ERROR, BLOCKED]
    assert len(api.calls) == 1
    assert result.provider_recordings == []


@pytest.mark.parametrize("mutation", ["user", "generation", "reorder", "drop", "duplicate"])
def test_recorder_final_read_cannot_spoof_or_change_evidence_order(mutation):
    class TamperingRecorder(Recorder):
        reads = 0
        def responses(self):
            self.reads += 1
            result = copy.deepcopy(self.items)
            if self.reads <= 2:
                return result
            if mutation == "user":
                result[-1].user = "peer"
            elif mutation == "generation":
                result[-1].session_generation = 44
            elif mutation == "reorder":
                result.reverse()
            elif mutation == "drop":
                result.pop()
            else:
                result.append(copy.deepcopy(result[-1]))
            return result
    _, result, _, _ = run(document(steps=[request("first"), request("next")]), recorder=TamperingRecorder())
    assert result.steps[-1].step_id == "_recorder" and result.steps[-1].status == ERROR
    assert result.status == FAILED
    assert not result.provider_recordings


def test_recorder_poll_order_tampering_fails_before_following_step():
    from refracto.runner import PollConfig
    class ReorderingRecorder(Recorder):
        def responses(self):
            return list(reversed(self.items))
    raw = document(steps=[request("poll"), request("later")])
    raw["steps"][0]["poll"] = {"on_timeout": "FAIL"}
    clock = [0]
    def sleep(duration):
        clock[0] += duration
    _, result, _, api = run(raw, api=Api([202, 200]), recorder=ReorderingRecorder(),
        poll_config=PollConfig(timeout=2, interval=1), now=lambda: clock[0], sleep=sleep)
    assert [s.status for s in result.steps] == [ERROR, BLOCKED]
    assert len(api.calls) == 2
    assert [(r.step_id, r.attempt_index, r.is_final) for r in result.provider_recordings] == [("poll", 0, False)]


def test_recorder_returns_copies_of_core_snapshots():
    recorder = Recorder()
    _, result, _, _ = run(document(), recorder=recorder)
    recorder.items[0].user = "peer"
    recorder.items[0].json["id"] = "changed-after-run"
    assert result.provider_recordings[0].user == "owner"
    assert result.provider_recordings[0].json["id"] == "r1"


def test_recorder_preserves_observed_nan_without_weakening_value_rules():
    import math
    import struct
    from refracto.declaration.values import equal
    from refracto.projection.recording import _evidence_equal
    nan = struct.unpack("!d", bytes.fromhex("7ff8000000000001"))[0]
    other = struct.unpack("!d", bytes.fromhex("7ff8000000000002"))[0]
    _, result, _, _ = run(document(), api=Api(data=[{"nested": [nan]}]))
    assert result.status == PASSED
    assert math.isnan(result.provider_recordings[0].json["nested"][0])
    assert _evidence_equal({"value": [nan]}, {"value": [nan]})
    assert not _evidence_equal({"value": [other]}, {"value": [nan]})
    assert not _evidence_equal({"value": False}, {"value": 0})
    assert not equal(nan, nan)


@pytest.mark.parametrize("invalid", [None, 1, "owner"])
def test_invalid_mutated_python_users_returns_structured_error(invalid):
    scenario = _load_document(document())
    scenario.users = invalid
    scenario.steps[0].user = None
    result = backend.run(scenario, auth=Auth(), api=Api(), state=None, recorder=Recorder(),
        resolve_request=lambda *args: None, normalizer=Normalizer())
    assert result.steps[0].status == ERROR


def test_impact_review_exposes_current_caller_mapping_and_child_session_policy(tmp_path):
    from refracto.declaration.impact import inspect_impact, render_text
    path, child_path = include_files(tmp_path)
    report = inspect_impact(child_path, child_path, tmp_path)
    sites = report["parents"][0]["includes"]
    assert [site["user_binding"]["effective_user"] for site in sites] == ["owner", "peer"]
    assert sites[0]["user_binding"]["before"] == {
        "local_users": ["operator"], "session_policies": {"read": "new"}}
    assert "User binding" in render_text(report)
    assert "Inspection is not approval" in render_text(report)
