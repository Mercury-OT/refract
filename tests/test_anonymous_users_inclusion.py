"""Neutral controls for mixed participants and pinned per-leaf user mappings."""
import hashlib
import json
from dataclasses import fields, replace

import pytest
import yaml

from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import inspect_impact, render_text
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.model import Scenario
from refracto.ports import RequestSpec
from refracto.projection import backend, contract, e2e
from refracto.projection.sessions import SessionError, SessionManager
from refracto.report import BLOCKED, ERROR, FAILED, PASSED, RunReport
from refracto.runner import PollConfig
from refracto.query import wire_query
from tests.test_users_sessions_core import Auth, Api, Normalizer, Recorder, document, request


def execute(scenario, *, auth=None, api=None, projection="backend", **kwargs):
    api = api or Api()
    auth = auth if auth is not None else Auth()
    options = dict(auth=auth, api=api, state=None, recorder=Recorder(), normalizer=Normalizer(),
        resolve_request=lambda template: RequestSpec(
            template.method, template.path, template.body, query=wire_query(template.query or {})), **kwargs)
    result = backend.run(scenario, **options) if projection == "backend" else e2e.run(scenario, ui=None, **options)
    return result, auth, api


def write_bundle(tmp_path, *, child=None, users=None, calls=None):
    if child is None:
        child = document(["creator", "reader"], [request("create", "creator"),
            request("read", "reader", body={"id": {"from_step": "create", "response_field": "id"}})])
        child["scenario"] = "shared.access"
        child["results"] = {"record_id": {"from_step": "create", "response_field": "id"}}
    parent = document(["owner", "anonymous"] if users is None else users,
        calls or [{"id": "access", "do": {"include": child["scenario"]},
                   "with_users": {"creator": "owner", "reader": "anonymous"}}])
    child_path = tmp_path / "child.yaml"
    child_path.write_text(yaml.safe_dump(child, sort_keys=False))
    path = tmp_path / "parent.yaml"
    path.write_text(yaml.safe_dump(parent, sort_keys=False))
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {child["scenario"]: {"path": "child.yaml",
            "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}))
    return path, child_path


def call(mapping=None, **extra):
    result = {"id": "access", "do": {"include": "shared.access"}, **extra}
    if mapping is not None:
        result["with_users"] = mapping
    return result


@pytest.mark.parametrize("users,choice,selected,runtime", [
    ([], "omitted", None, None), (["anonymous"], "omitted", "anonymous", None),
    (["anonymous"], "anonymous", "anonymous", None), (["owner"], "omitted", "owner", "owner"),
    (["Anonymous"], "omitted", "Anonymous", "Anonymous"),
    (["owner", "anonymous"], "owner", "owner", "owner"),
    (["owner", "anonymous"], "anonymous", "anonymous", None)])
def test_cardinality_and_anonymous_runtime_translation(users, choice, selected, runtime):
    step = request("read")
    if choice != "omitted":
        step["user"] = choice
    scenario = _load_document(document(users, [step]))
    assert scenario.steps[0].user == selected
    assert scenario.selected_user(scenario.steps[0]) == selected
    assert scenario.effective_user(scenario.steps[0]) == runtime
    result, auth, api = execute(scenario)
    assert result.status == PASSED
    assert result.steps[0].user == runtime
    assert result.steps[0].session_generation == (0 if runtime is None else 1)
    assert auth.identified == [user for user in users if user != "anonymous"]
    assert auth.authenticated == ([] if runtime is None else [runtime])
    assert (api.calls[0][1] is None) == (runtime is None)
    assert expansion_view(scenario)["steps"][0]["user"] == (selected or "anonymous")


@pytest.mark.parametrize("users,extra", [
    (["owner"], {"user": "anonymous"}), (["owner", "anonymous"], {}),
    (["anonymous"], {"user": None}), (["anonymous"], {"user": ""}),
    (["anonymous"], {"user": False}), (["anonymous"], {"user": {"from_parameter": "who"}}),
    ([], {"user": "anonymous"}), (["anonymous"], {"session": "new"}),
    (["owner", "anonymous"], {"user": "anonymous", "session": "new"}),
    (["owner"], {"with_users": {"owner": "owner"}})])
def test_invalid_leaf_choices_rejected_before_execution(users, extra):
    step = request("read")
    step.update(extra)
    with pytest.raises(DeclarationError):
        _load_document(document(users, [step]))


@pytest.mark.parametrize("users", [[], ["anonymous"]])
def test_anonymous_only_needs_no_authenticator(users):
    result, _, api = execute(_load_document(document(users)), auth=object())
    assert result.status == PASSED and api.calls[0][1] is None


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_named_anonymous_named_retains_session_and_sensitive_provenance(projection):
    raw = document(["owner", "anonymous"], [request("first", "owner"),
        request("guest", "anonymous", body={"id": {"from_step": "first", "response_field": "id"}}),
        request("last", "owner", body={"id": {"from_step": "guest", "response_field": "id"}})])
    scenario = _load_document(raw)
    result, auth, api = execute(scenario, projection=projection,
        api=Api(data=[{"id": "sensitive-value"}, {"id": "guest-id"}, {}]))
    assert result.status == PASSED
    assert auth.identified == auth.authenticated == ["owner"]
    assert api.calls[0][1] is api.calls[2][1] and api.calls[1][1] is None
    assert [(s.user, s.session_generation) for s in result.steps] == [("owner", 1), (None, 0), ("owner", 1)]
    assert [(r.user, r.session_generation) for r in result.provider_recordings] == [("owner", 1), (None, 0), ("owner", 1)]
    guest_source = next(iter(result.steps[1].binding_sources.values())).origin
    named_source = next(iter(result.steps[2].binding_sources.values())).origin
    assert (guest_source.user, guest_source.session_generation) == ("owner", 1)
    assert (named_source.user, named_source.session_generation) == (None, 0)
    assert contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=result.steps).status == PASSED
    for secret in ("sensitive-value", "sensitive-principal", "sensitive-auth", "sensitive-credential"):
        assert secret not in repr(RunReport(scenario.id, [result]))


@pytest.mark.parametrize("changes", [{"user": "anonymous"}, {"user": "owner"},
    {"session_generation": 1}, {"session_generation": False}, {"session_generation": None}])
def test_contract_rejects_tampered_anonymous_recording(changes):
    scenario = _load_document(document(["owner", "anonymous"], [request("guest", "anonymous")]))
    result, _, _ = execute(scenario)
    bad = replace(result.provider_recordings[0], **changes)
    assert contract.run(scenario, [bad], Normalizer(), execution_steps=result.steps).steps[0].status == ERROR


def test_anonymous_poll_has_no_credentials_and_one_lease():
    raw = document(["owner", "anonymous"], [request("poll", "anonymous")])
    raw["steps"][0]["poll"] = {"on_timeout": "FAIL"}
    clock = [0]
    def sleep(duration):
        clock[0] += duration
    result, auth, api = execute(_load_document(raw), api=Api([202, 200]),
        poll_config=PollConfig(timeout=2, interval=1), now=lambda: clock[0], sleep=sleep)
    assert result.status == PASSED and len(api.calls) == 2
    assert auth.authenticated == []
    assert all(session is None for _, session in api.calls)
    assert [(r.user, r.session_generation) for r in result.provider_recordings] == [(None, 0), (None, 0)]


def test_dependency_blocked_anonymous_step_has_no_acquired_generation():
    raw = document(["owner", "anonymous"], [request("first", "owner"),
        request("guest", "anonymous", body={"id": {"from_step": "first", "response_field": "missing"}}),
        request("last", "owner")])
    result, auth, api = execute(_load_document(raw))
    assert [s.status for s in result.steps] == [PASSED, BLOCKED, PASSED]
    assert result.steps[1].user is None and result.steps[1].session_generation is None
    assert len(api.calls) == 2 and auth.authenticated == ["owner"]


@pytest.mark.parametrize("change", ["new", "undeclared", "empty-users", "missing-multi"])
def test_python_declarations_cannot_bypass_anonymous_preflight(change):
    scenario = _load_document(document(["owner", "anonymous"], [request("guest", "anonymous")]))
    if change == "new":
        scenario.steps[0].session = "new"
    elif change == "undeclared":
        scenario.users = ["owner"]
    elif change == "empty-users":
        scenario.users = []
    else:
        scenario.steps[0].user = None
    auth, api = Auth(), Api()
    result, _, _ = execute(scenario, auth=auth, api=api)
    assert result.steps[0].status == ERROR and not api.calls and not auth.identified


def test_actual_named_principals_stay_distinct_with_anonymous_present():
    class Duplicate(Auth):
        def identify(self, user):
            assert user != "anonymous"
            return "same-principal"
    scenario = _load_document(document(["owner", "peer", "anonymous"], [request("guest", "anonymous")]))
    result, _, api = execute(scenario, auth=Duplicate())
    assert result.steps[0].status == ERROR and not api.calls


class StringSubclass(str):
    pass


class EqualToAnyValue:
    def __eq__(self, other):
        return True


@pytest.mark.parametrize("field,value", [
    ("user", StringSubclass("anonymous")), ("user", EqualToAnyValue()),
    ("user", False), ("user", 0), ("user", {}),
    ("session", StringSubclass("new")), ("session", EqualToAnyValue()),
    ("session", False), ("session", 0)])
def test_python_user_and_session_protocol_values_are_type_strict(field, value):
    scenario = _load_document(document(["owner", "anonymous"], [request("read", "owner")]))
    setattr(scenario.steps[0], field, value)
    auth = Auth()
    with pytest.raises(SessionError):
        SessionManager(scenario, auth).preflight()
    assert not auth.identified and not auth.authenticated


def test_multi_user_child_two_callers_keep_identical_bytes_and_flat_runtime(tmp_path):
    path, child = write_bundle(tmp_path)
    original = child.read_bytes()
    scenario = load_scenario(path)
    assert [s.user for s in scenario.steps] == ["owner", "anonymous"]
    assert scenario.include_user_mappings == {"access": {"creator": "owner", "reader": "anonymous"}}
    assert scenario.source_lookup["access/read"]["source_user"] == "reader"
    assert scenario.source_lookup["access/read"]["effective_user"] == "anonymous"
    flat = document(["owner", "anonymous"], [request("access/create", "owner"),
        request("access/read", "anonymous", body={"id": {"from_step": "access/create", "response_field": "id"}})])
    flat_scenario = _load_document(flat)
    assert scenario.steps == flat_scenario.steps
    composed, _, _ = execute(scenario)
    handwritten, _, _ = execute(flat_scenario)
    assert [(s.status, s.user, s.session_generation) for s in composed.steps] == [
        (s.status, s.user, s.session_generation) for s in handwritten.steps]
    assert contract.run(scenario, composed.provider_recordings, Normalizer(), execution_steps=composed.steps).status == PASSED
    parent = yaml.safe_load(path.read_text())
    parent["users"] = ["owner", "peer"]
    parent["steps"][0]["with_users"]["reader"] = "peer"
    second = path.with_name("second.yaml")
    second.write_text(yaml.safe_dump(parent))
    second.with_suffix(".includes.json").write_bytes(path.with_suffix(".includes.json").read_bytes())
    assert [s.user for s in load_scenario(second).steps] == ["owner", "peer"]
    assert child.read_bytes() == original


@pytest.mark.parametrize("mapping", [
    {}, {"creator": "owner"}, {"creator": "owner", "reader": "anonymous", "extra": "owner"},
    {"creator": "owner", "reader": "unknown"}, {"creator": "owner", "reader": None},
    {"creator": "owner", "reader": ""}, {"creator": "owner", "reader": False},
    {"creator": "owner", "reader": {"from_parameter": "who"}},
    {"creator": "owner", "reader": "owner"}, {"creator": "anonymous", "reader": "anonymous"},
    {1: "owner", "reader": "anonymous"}, ["owner", "anonymous"], "anonymous"])
def test_malformed_or_colliding_user_mappings_rejected(tmp_path, mapping):
    path, _ = write_bundle(tmp_path, calls=[call(mapping)])
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("extra", [
    {"user": "owner"}, {"session": "new"}, {"on_failure": "stop"},
    {"expect": {}}, {"poll": {}}, {"target": "records"}, {"repeat": 2}])
def test_mapping_cannot_override_call_behavior(tmp_path, extra):
    path, _ = write_bundle(tmp_path, calls=[call({"creator": "owner", "reader": "anonymous"}, **extra)])
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_multi_child_requires_mapping_even_when_names_match(tmp_path):
    path, _ = write_bundle(tmp_path, users=["creator", "reader"], calls=[call(user="creator")])
    with pytest.raises(DeclarationError, match="requires with_users"):
        load_scenario(path)


@pytest.mark.parametrize("users", [[], ["anonymous"]])
def test_anonymous_child_never_upgraded(tmp_path, users):
    child = document(users)
    child["scenario"] = "shared.access"
    path, _ = write_bundle(tmp_path, child=child, users=["owner"], calls=[call(user="owner")])
    with pytest.raises(DeclarationError, match="must remain anonymous"):
        load_scenario(path)


@pytest.mark.parametrize("child_users,parent_users,mapping", [
    (["operator"], [], {"operator": "anonymous"}),
    (["operator"], ["anonymous"], {"operator": "anonymous"}),
    (["anonymous"], [], {"anonymous": "anonymous"}),
    (["operator"], ["owner"], {"operator": "owner"}),
    (["anonymous"], ["owner", "anonymous"], {"anonymous": "anonymous"})])
def test_single_child_explicit_mapping_and_implicit_parent_anonymous(tmp_path, child_users, parent_users, mapping):
    child = document(child_users)
    child["scenario"] = "shared.access"
    path, _ = write_bundle(tmp_path, child=child, users=parent_users, calls=[call(mapping)])
    scenario = load_scenario(path)
    result, auth, _ = execute(scenario)
    assert result.status == PASSED
    target = next(iter(mapping.values()))
    assert result.steps[0].user == (None if target == "anonymous" else target)
    assert "anonymous" not in auth.identified and "anonymous" not in auth.authenticated
    assert scenario.source_lookup["access/read"]["effective_user"] == target
    assert expansion_view(scenario)["steps"][0]["user"] == target
    assert contract.run(scenario, result.provider_recordings, Normalizer(), execution_steps=result.steps).status == PASSED


def test_empty_child_uses_only_anonymous_shorthand(tmp_path):
    child = document([])
    child["scenario"] = "shared.access"
    path, _ = write_bundle(tmp_path, child=child, users=["owner", "anonymous"], calls=[call(user="anonymous")])
    scenario = load_scenario(path)
    assert execute(scenario)[0].status == PASSED
    parent = yaml.safe_load(path.read_text())
    parent["steps"][0] = call({"anonymous": "anonymous"})
    path.write_text(yaml.safe_dump(parent))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_explicit_child_anonymous_cannot_be_upgraded_in_full_mapping(tmp_path):
    child = document(["creator", "anonymous"], [request("first", "creator"), request("guest", "anonymous")])
    child["scenario"] = "shared.access"
    path, _ = write_bundle(tmp_path, child=child, users=["owner", "peer"],
        calls=[call({"creator": "owner", "anonymous": "peer"})])
    with pytest.raises(DeclarationError, match="must remain anonymous"):
        load_scenario(path)


def test_mapped_anonymous_cannot_silently_drop_new_session(tmp_path):
    child = document(["operator"], [request("read", session="new")])
    child["scenario"] = "shared.access"
    path, _ = write_bundle(tmp_path, child=child, users=["anonymous"], calls=[call({"operator": "anonymous"})])
    with pytest.raises(DeclarationError, match="cannot replace a session"):
        load_scenario(path)


def test_complete_mapping_and_named_results_preserve_query_and_stop(tmp_path):
    path, child_path = write_bundle(tmp_path)
    child = yaml.safe_load(child_path.read_text())
    child["steps"][0]["on_failure"] = "stop"
    parent = yaml.safe_load(path.read_text())
    parent["steps"].append({"id": "query", "user": "owner", "do": {"request": {
        "method": "GET", "path": ["records"], "query": {"id": {"from_step": "access", "result": "record_id"}}}},
        "expect": {"response": [{"check": "status_equals", "value": 200}]}})
    path, _ = write_bundle(tmp_path, child=child, calls=parent["steps"])
    scenario = load_scenario(path)
    passed, _, api = execute(scenario)
    assert passed.status == PASSED and api.calls[-1][0].query == {"id": "r1"}
    assert next(iter(passed.steps[-1].binding_sources.values())).origin.user == "owner"
    failed, auth, api = execute(scenario, api=Api([500]))
    assert [s.status for s in failed.steps] == [FAILED, BLOCKED, BLOCKED]
    assert auth.authenticated == ["owner"] and len(api.calls) == 1
    assert all(s.session_generation is None for s in failed.steps[1:])


def test_stale_pin_and_nested_includes_still_rejected(tmp_path):
    path, child_path = write_bundle(tmp_path)
    child_path.write_text(child_path.read_text() + "\n# changed\n")
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_scenario(path)
    child = document(["operator"], [call()])
    child["scenario"] = "shared.access"
    path, _ = write_bundle(tmp_path, child=child)
    with pytest.raises(DeclarationError, match="must not include"):
        load_scenario(path)


def test_duplicate_mapping_keys_and_null_mapping_rejected(tmp_path):
    path, _ = write_bundle(tmp_path)
    text = path.read_text().replace("    reader: anonymous", "    reader: anonymous\n    reader: owner")
    assert text != path.read_text()
    path.write_text(text)
    with pytest.raises(DeclarationError, match="duplicate"):
        load_scenario(path)
    path, _ = write_bundle(tmp_path)
    raw = yaml.safe_load(path.read_text())
    raw["steps"][0]["with_users"] = None
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_review_and_impact_show_complete_mapping_and_local_participants(tmp_path):
    path, child = write_bundle(tmp_path)
    scenario = load_scenario(path)
    expanded = expansion_view(scenario)
    assert expanded["include_user_mappings"] == {"access": {"creator": "owner", "reader": "anonymous"}}
    assert [s["user"] for s in expanded["steps"]] == ["owner", "anonymous"]
    assert expanded["steps"][1]["source"]["source_user"] == "reader"
    report = inspect_impact(child, child, tmp_path)
    binding = report["parents"][0]["includes"][0]["user_binding"]
    assert binding["effective_user"] is None
    assert binding["with_users"] == {"creator": "owner", "reader": "anonymous"}
    assert binding["before"]["effective_bindings"] == binding["with_users"]
    assert binding["after"]["steps"]["read"] == {"local_user": "reader", "effective_user": "anonymous", "session": "reuse"}
    assert "anonymous" in render_text(report) and report["parents"][0]["validity"]["actual"] == "valid"
    parent = yaml.safe_load(path.read_text())
    parent["steps"][0]["with_users"]["reader"] = "owner"
    path.write_text(yaml.safe_dump(parent))
    invalid = inspect_impact(child, child, tmp_path)
    assert invalid["parents"][0]["validity"]["actual"] == "invalid"
    assert invalid["parents"][0]["includes"][0]["user_binding"]["after"]["effective_bindings"] is None


def test_impact_shows_changed_child_users_and_session_policy(tmp_path):
    path, child_path = write_bundle(tmp_path)
    before = tmp_path / "before.yaml"
    before.write_bytes(child_path.read_bytes())
    changed = yaml.safe_load(child_path.read_text())
    changed["steps"][1]["session"] = "new"
    child_path.write_text(yaml.safe_dump(changed))
    report = inspect_impact(before, child_path, tmp_path)
    parent = next(row for row in report["parents"] if row["path"] == path.name)
    binding = parent["includes"][0]["user_binding"]
    assert binding["before"]["steps"]["read"]["session"] == "reuse"
    assert binding["after"]["steps"]["read"]["session"] == "new"
    assert parent["validity"]["hypothetical_before"] == "valid"
    assert parent["validity"]["hypothetical_after"] == "invalid"
    changed["users"][1] = "reviewer"
    changed["steps"][1]["user"] = "reviewer"
    child_path.write_text(yaml.safe_dump(changed))
    report = inspect_impact(before, child_path, tmp_path)
    binding = next(row for row in report["parents"] if row["path"] == path.name)["includes"][0]["user_binding"]
    assert binding["before"]["local_users"] == ["creator", "reader"]
    assert binding["after"]["local_users"] == ["creator", "reviewer"]
    assert binding["after"]["effective_bindings"] is None


@pytest.mark.parametrize("users", [
    {"owner": "not-a-list"}, {}, None, False, 1, "owner", ["owner", "owner"], [""], [{}], ["owner", False], ...])
@pytest.mark.parametrize("explicit_mapping", [False, True])
def test_impact_invalid_current_parent_users_are_diagnostics_not_exceptions(tmp_path, users, explicit_mapping):
    child = document(["operator"])
    child["scenario"] = "shared.access"
    path, child_path = write_bundle(tmp_path, child=child, users=["owner"],
        calls=[call({"operator": "owner"}) if explicit_mapping else call()])
    parent = yaml.safe_load(path.read_text())
    if users is ...:
        del parent["users"]
    else:
        parent["users"] = users
    path.write_text(yaml.safe_dump(parent))
    with pytest.raises(DeclarationError):
        load_scenario(path)
    report = inspect_impact(child_path, child_path, tmp_path)
    parent_record = next(row for row in report["parents"] if row["path"] == path.name)
    assert parent_record["validity"] == {"actual": "invalid", "hypothetical_before": "invalid", "hypothetical_after": "invalid"}
    binding = parent_record["includes"][0]["user_binding"]
    assert binding["effective_user"] is None
    for version in ("before", "after"):
        assert binding[version]["effective_bindings"] is None
        assert binding[version]["steps"]["read"]["effective_user"] is None
    assert report["status"] == "INCOMPLETE" and report["review_required"] is True


def test_cli_expand_maps_all_users_and_invalid_mapping_never_produces_plan(tmp_path, capsys):
    from refracto.cli import main
    path, _ = write_bundle(tmp_path)
    assert main(["validate", str(path), "--expand"]) == 0
    expanded = json.loads(capsys.readouterr().out)
    assert expanded["include_user_mappings"] == {"access": {"creator": "owner", "reader": "anonymous"}}
    assert [s["user"] for s in expanded["steps"]] == ["owner", "anonymous"]
    parent = yaml.safe_load(path.read_text())
    parent["steps"][0]["with_users"].pop("reader")
    path.write_text(yaml.safe_dump(parent))
    assert main(["validate", str(path), "--expand"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "INVALID" in output.err


def test_mapping_review_metadata_is_keyword_only_independent_and_noncomparing():
    descriptor = next(f for f in fields(Scenario) if f.name == "include_user_mappings")
    assert descriptor.kw_only and not descriptor.compare and not descriptor.repr
    first, second = _load_document(document()), _load_document(document())
    first.include_user_mappings["access"] = {"local": "owner"}
    assert second.include_user_mappings == {} and first == second
