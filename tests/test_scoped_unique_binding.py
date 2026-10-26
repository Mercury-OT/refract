"""Run-value preparation isolates sources without changing time or evidence."""
import copy
from dataclasses import fields
from datetime import datetime, timezone
from uuid import UUID

import pytest

from refracto import runner
from refracto.declaration import run_values
from refracto.declaration.loader import _load_document
from refracto.declaration.model import Scenario
from refracto.declaration.run_values import bind_projection_values, bind_run_values
from refracto.report import RunReport
from tests.test_run_values_declaration import declaration
from tests.test_run_values_runtime import adapters, EchoApi, source_file


BASE = "2026-10-24T08:00:00.123Z"


def values_document():
    return declaration({
        "name": {"concat": [{"from_parameter": "first"}, "-", {"from_parameter": "first"}]},
        "second": {"from_run": "unique"},
        "first": {"from_run": "unique"},
        "time": {"from_run": "time"},
    })


def test_all_projection_copies_share_one_clock_but_have_independent_source_maps(monkeypatch):
    reads, generated = [], []
    def clock():
        reads.append("clock")
        return datetime(2026, 10, 24, 8, 0, 0, 123999, tzinfo=timezone.utc)
    def generate():
        token = UUID(int=len(generated) + 1, version=4)
        generated.append(token.hex)
        return token
    monkeypatch.setattr(run_values, "_utc_now", clock)
    monkeypatch.setattr(run_values, "uuid4", generate)
    original = _load_document(values_document())
    before = copy.deepcopy(original)
    executions = bind_projection_values(original, ("backend", "frontend", "e2e", "contract"))
    assert reads == ["clock"] and len(generated) == 6
    assert len(set(generated)) == 6
    for name, bound in executions.items():
        assert bound.run_time == BASE and bound.run_time_source == "actual"
        assert bound.run_time_values == {"time": BASE}
        assert set(bound.run_unique_values) == {"first", "second"}
        assert bound.parameters["name"] == bound.parameters["first"] + "-" + bound.parameters["first"]
        assert bound.parameters["first"] != bound.parameters["second"]
        assert bound.run_unique_values["first"] == bound.parameters["first"]
    assert executions["backend"] is not executions["contract"]
    assert executions["backend"].parameters == executions["contract"].parameters
    executions["backend"].run_unique_values["first"] = "changed"
    executions["backend"].run_time_values["time"] = "changed"
    assert executions["contract"].run_unique_values["first"] != "changed"
    assert executions["contract"].run_time_values == {"time": BASE}
    assert original == before and original.run_unique_values == {}
    assert original.run_time_values == {} and not original.run_values_bound


def test_fixed_base_across_scopes_never_reads_clock(monkeypatch):
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("fixed base read clock"))
    executions = bind_projection_values(_load_document(values_document()),
                                       ("backend", "e2e", "contract"), run_time=BASE)
    assert all(bound.run_time == BASE and bound.run_time_source == "fixed"
               for bound in executions.values())
    assert executions["backend"].run_unique_values != executions["e2e"].run_unique_values
    assert executions["contract"].run_unique_values == executions["backend"].run_unique_values


def test_later_scope_binding_failure_precedes_every_adapter_call(tmp_path, monkeypatch):
    calls = []
    def generate():
        calls.append("generate")
        if len(calls) == 2:
            raise ValueError("generation failed")
        return UUID(int=1, version=4)
    monkeypatch.setattr(run_values, "uuid4", generate)
    class Untouched:
        def __getattr__(self, name):
            pytest.fail("binding failure reached an adapter")
    def forbidden(*args):
        pytest.fail("binding failure reached a factory or resolver")
    configured = runner.Adapters(Untouched(), Untouched(), Untouched(), None,
                                  forbidden, forbidden, Untouched())
    raw = declaration({"name": {"from_run": "unique"}})
    with pytest.raises(ValueError, match="generation failed"):
        runner.run_scenario(source_file(tmp_path, raw), configured,
                            projections=("backend", "e2e", "contract"))
    assert len(calls) == 2


@pytest.mark.parametrize("model", [Scenario, RunReport])
def test_unique_values_metadata_remains_sensitive_keyword_only_and_hidden(model):
    field = next(field for field in fields(model) if field.name == "run_unique_values")
    assert field.kw_only and not field.repr and not field.compare
    assert field.metadata["sensitive"] is True
    assert field.name not in model.__match_args__


def test_binding_result_map_does_not_alias_bound_declaration_metadata():
    original = _load_document(declaration({"name": {"from_run": "unique"}}))
    bound, values = bind_run_values(original)
    assert values == bound.run_unique_values == {"name": bound.parameters["name"]}
    values["name"] = "caller-mutated"
    assert bound.run_unique_values["name"] == bound.parameters["name"] != "caller-mutated"
    assert original.run_unique_values == {}


@pytest.mark.parametrize("prepare", [bind_run_values,
    lambda scenario: bind_projection_values(scenario, ("backend", "contract"))])
def test_rebinding_is_rejected_without_randomness_or_clock(prepare, monkeypatch):
    bound, _ = bind_run_values(_load_document(values_document()), run_time=BASE)
    before = copy.deepcopy(bound)
    monkeypatch.setattr(run_values, "uuid4", lambda: pytest.fail("rebound source regenerated"))
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("rebound source read clock"))
    with pytest.raises(ValueError, match="already bound"):
        prepare(bound)
    assert bound == before and bound.run_unique_values == before.run_unique_values


def test_reused_source_in_two_request_steps_is_not_regenerated(tmp_path):
    raw = declaration({"name": {"from_run": "unique"}})
    second = copy.deepcopy(raw["steps"][0])
    second["id"] = "retry"
    raw["steps"].append(second)
    api = EchoApi()
    report = runner.run_scenario(source_file(tmp_path, raw), adapters(api),
                                projections=("backend", "contract"))
    assert report.status == "PASSED"
    assert len(api.sent) == 2
    assert api.sent[0].body == api.sent[1].body == {
        "name": report.run_unique_values["backend"]["name"]}
