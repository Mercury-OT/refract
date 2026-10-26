"""Pinned one-level composition keeps time scope and runtime response evidence."""
import copy
import json
from datetime import datetime, timezone

import pytest

from refracto import ports, runner
from refracto.declaration import run_values
from refracto.declaration.binding import DependencyUnavailable, prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.run_values import bind_run_values
from tests.test_run_values_declaration import declaration
from tests.test_run_values_runtime import adapters
from tests.test_scenario_include import include, leaf, parent, write_bundle


BASE = "2026-10-24T08:00:00.000Z"


def observed(**values):
    return ports.NormalizedResponse(True, values, 200, None)


def timed_child():
    return leaf(parameters={"name": {"concat": ["child-", {"from_parameter": "time"}]},
                            "time": {"from_run": "time", "offset": {"days": 7}}})


def test_repeated_child_defaults_and_overrides_share_base_not_parameter_scope(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run_values, "_utc_now", lambda: calls.append("clock") or datetime(2026, 10, 24, 8, tzinfo=timezone.utc))
    root = parent([include("default"), include("override", **{"with": {"time": {"from_parameter": "time"}}})],
                  parameters={"time": {"from_run": "time", "offset": {"hours": -24}}})
    path, _ = write_bundle(tmp_path, root, timed_child())
    original = load_scenario(path)
    before = copy.deepcopy(expansion_view(original))
    bound, _ = bind_run_values(original)
    assert calls == ["clock"]
    names = [prepare_step(step, bound, {})[0].request.body["name"] for step in bound.steps]
    assert names == ["child-2026-10-31T08:00:00.000Z", "child-2026-10-23T08:00:00.000Z"]
    assert bound.run_time == BASE
    assert sorted(bound.run_time_values.values()) == [
        "2026-10-23T08:00:00.000Z", "2026-10-31T08:00:00.000Z"]
    assert expansion_view(original) == before
    assert expansion_view(load_scenario(path)) == before


def test_parent_override_removes_unused_child_clock_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("overridden marker read clock"))
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"time": "literal-time"}})]), timed_child())
    bound, _ = bind_run_values(load_scenario(path))
    assert bound.run_time is None and bound.run_time_values == {}
    assert prepare_step(bound.steps[0], bound, {})[0].request.body["name"] == "child-literal-time"


def test_response_override_is_not_frozen_or_added_to_time_metadata(tmp_path):
    source = declaration(value="source")["steps"][0]
    source["id"] = "source"
    override = {"from_step": "source", "response_field": "time"}
    root = parent([source, include(**{"with": {"time": override}})],
                  parameters={"base": {"from_run": "time"}})
    path, _ = write_bundle(tmp_path, root, timed_child())
    bound, _ = bind_run_values(load_scenario(path), run_time=BASE)
    assert bound.run_time_values == {"base": BASE}
    step, bindings = prepare_step(bound.steps[1], bound, {"source": observed(time="actual-response-time")})
    assert step.request.body["name"] == "child-actual-response-time"
    assert list(bindings.values()) == ["actual-response-time"]
    with pytest.raises(DependencyUnavailable):
        prepare_step(bound.steps[1], bound, {"source": observed(time=None)})


def test_named_result_references_actual_response_not_child_time_expectation(tmp_path):
    child = timed_child()
    child["results"] = {"returned_name": {"from_step": "create", "response_field": "name"}}
    consume = declaration(value={"from_step": "setup", "result": "returned_name"})["steps"][0]
    consume["id"] = "consume"
    path, _ = write_bundle(tmp_path, parent([include(), consume]), child)
    report = runner.run_scenario(path, adapters(), projections=("backend", "contract"), run_time=BASE)
    assert report.status == "PASSED"
    assert [row.request.body["name"] for row in report.domains[0].provider_recordings] == [
        "child-2026-10-31T08:00:00.000Z", "child-2026-10-31T08:00:00.000Z"]
    bound, _ = bind_run_values(load_scenario(path), run_time=BASE)
    selected, bindings = prepare_step(bound.steps[1], bound, {"setup/create": observed(name="actual-other-value")})
    assert selected.request.body["name"] == "actual-other-value"
    assert list(bindings.values()) == ["actual-other-value"]


def test_literal_time_looking_override_is_not_reinterpreted(tmp_path, monkeypatch):
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("literal override read clock"))
    literal = {"from_run": "time", "offset": {"days": 7}}
    root = parent([include(**{"with": {"name": {"from_parameter": "payload"}}})],
                  parameters={"payload": {"literal": {"nested": literal}}})
    path, _ = write_bundle(tmp_path, root, leaf())
    bound, _ = bind_run_values(load_scenario(path))
    assert prepare_step(bound.steps[0], bound, {})[0].request.body["name"] == {"nested": literal}
    assert bound.run_time is None


def test_impact_and_cli_expansion_do_not_sample_time(tmp_path, monkeypatch):
    from refracto.cli import main
    from tests.test_scenario_impact import bundle, child, inspect
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("authoring read clock"))
    parameters = {"name": {"concat": ["at-", {"from_parameter": "time"}]},
                  "time": {"from_run": "time", "offset": {"days": 7}},
                  "payload": {"literal": {"nested": {"from_run": "time"}}}}
    paths = bundle(tmp_path, old=child(parameters=parameters))
    report = inspect(paths, show_values=True)
    assert report["status"] == "COMPLETE"
    defaults = report["parents"][0]["includes"][0]["defaults"]["before"]
    assert defaults["time"] == {"kind": "run-value", "from_run": "time", "offset": {"days": 7}}
    assert defaults["payload"]["value"] == {"nested": {"from_run": "time"}}
    assert main(["validate", str(paths[3]), "--expand"]) == 0
    assert "from_run" in json.dumps(expansion_view(load_scenario(paths[3])))


def test_time_does_not_relax_include_pin_or_depth(tmp_path):
    path, child_path = write_bundle(tmp_path, child=timed_child())
    child_path.write_text(child_path.read_text() + "\n# pin change\n")
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_scenario(path)
    child = timed_child()
    child["steps"].append(include(target="another.child"))
    path, _ = write_bundle(tmp_path, child=child)
    with pytest.raises(DeclarationError, match="must not include"):
        load_scenario(path)
