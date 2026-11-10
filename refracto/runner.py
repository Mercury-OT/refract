"""Scenario orchestrator.

Load a scenario, apply grid selection, run the requested projections through
adapter ports, and aggregate the results into a RunReport. The contract
projection consumes provider recordings produced by the backend projection, so
it may only be requested together with `backend`.
"""
from dataclasses import dataclass, field
import copy
import math
from uuid import uuid4
from collections.abc import Callable
from refracto.ports import RequestAction, RequestSpec
from refracto.declaration.loader import load_scenario
from refracto.declaration.run_values import bind_projection_values, _parse_run_time
from refracto import grid
from refracto.report import RunReport, FlowReport, FlowScenarioReport, BLOCKED
from refracto.projection import backend as backend_proj
from refracto.projection import frontend as frontend_proj
from refracto.projection import e2e as e2e_proj
from refracto.projection import contract as contract_proj


@dataclass
class PollConfig:
    """Polling timing for a single `run_scenario` call."""
    timeout: float = 30.0
    interval: float = 1.0

    def __post_init__(self):
        if any(type(value) not in (int, float) or not math.isfinite(value)
               for value in (self.timeout, self.interval)):
            raise ValueError("PollConfig timing must be finite numbers")
        if self.timeout <= 0:
            raise ValueError(f"PollConfig.timeout must be > 0, got {self.timeout!r}")
        if self.interval <= 0:
            raise ValueError(f"PollConfig.interval must be > 0, got {self.interval!r}")
        if self.interval > self.timeout:
            raise ValueError(
                f"PollConfig.interval ({self.interval!r}) must be <= timeout ({self.timeout!r})")


@dataclass
class Adapters:
    auth: object
    api: object
    state: object
    ui: object
    recorder_factory: object            # callable -> Recorder
    resolve_request: Callable[[RequestAction], RequestSpec]
    normalizer: object = None           # ResponseNormalizer
    object_state: object = field(default=None, kw_only=True)  # ObjectStateProbe


_VALID_PROJECTIONS = {"backend", "frontend", "e2e", "contract"}


def run_scenario(path, adapters, *, projections=("backend", "frontend", "e2e", "contract"),
                 level=None, module=None, poll_config=None, now=None, sleep=None,
                 mock_plan=None, run_time=None, file_config=None):
    _parse_run_time(run_time)
    poll_config = poll_config or PollConfig()
    scenario = load_scenario(path, file_config=file_config)
    report = RunReport(scenario_id=scenario.id,
                       source_lookup=copy.deepcopy(scenario.source_lookup))

    unknown = set(projections) - _VALID_PROJECTIONS
    if unknown:
        raise ValueError(f"unknown projection(s): {sorted(unknown)}; valid: {sorted(_VALID_PROJECTIONS)}")
    if adapters.normalizer is None:
        raise ValueError("adapters.normalizer is required (a ResponseNormalizer)")
    needs_ui = any(step.action in ("open", "click", "fill", "press", "hover") or step.expect.frontend
                   for step in scenario.steps)
    if adapters.ui is None and ("frontend" in projections or ("e2e" in projections and needs_ui)):
        raise ValueError(
            "frontend/e2e projection requested but no UiDriver was provided")
    # The contract projection diffs the declaration against recordings the backend
    # projection produces. Refuse the combination up front rather than quietly
    # running a real backend to manufacture them: a caller who asked for contract
    # alone is expecting an offline check, and would not expect real requests with
    # real side effects.
    if "contract" in projections and "backend" not in projections:
        raise ValueError(
            "the contract projection consumes provider recordings produced by the "
            "backend projection and cannot run on its own; add 'backend' to projections")

    if not grid.select(scenario, level=level, module=module):
        # A filtered-out scenario is not a silent pass.
        report.selected = False
        return report

    # Complete all preparation before any port call. Execution projections own
    # unique values, while one clock base and backend/contract evidence are shared.
    executions = bind_projection_values(scenario, projections, run_time=run_time)
    report.run_unique_values = {name: copy.deepcopy(bound.run_unique_values)
                                for name, bound in executions.items()}
    if executions:
        first = next(iter(executions.values()))
        report.run_time = first.run_time
        report.run_time_source = first.run_time_source
        report.run_time_values = copy.deepcopy(first.run_time_values)

    provider_recordings = []
    provider_steps = []
    if "backend" in projections:
        rec = adapters.recorder_factory()
        d = backend_proj.run(executions["backend"], auth=adapters.auth, api=adapters.api,
                             state=adapters.state, recorder=rec,
                             resolve_request=adapters.resolve_request,
                             normalizer=adapters.normalizer, poll_config=poll_config,
                             now=now, sleep=sleep, object_state=adapters.object_state)
        provider_recordings = d.provider_recordings
        provider_steps = d.steps
        report.domains.append(d)
    if "frontend" in projections:
        report.domains.append(frontend_proj.run(executions["frontend"], ui=adapters.ui, auth=adapters.auth,
                                                 normalizer=adapters.normalizer,
                                                 mock_plan=mock_plan, now=now, sleep=sleep))
    if "e2e" in projections:
        rec = adapters.recorder_factory()
        report.domains.append(e2e_proj.run(executions["e2e"], auth=adapters.auth, ui=adapters.ui,
                                            api=adapters.api, resolve_request=adapters.resolve_request,
                                            state=adapters.state, recorder=rec,
                                            normalizer=adapters.normalizer, poll_config=poll_config,
                                            now=now, sleep=sleep, object_state=adapters.object_state))
    if "contract" in projections:
        report.domains.append(contract_proj.run(executions["contract"], provider_recordings, adapters.normalizer,
                                               execution_steps=provider_steps))
    return report


def run_flow(path, adapters, *, projections=("backend", "frontend", "e2e", "contract"),
             poll_config=None, now=None, sleep=None, mock_plan=None, run_time=None,
             file_config=None):
    """Execute pinned Scenario invocations with projection-local shared state.

    A projection enters its action engine once, retaining its user sessions and
    browser contexts through every invocation. Contract is offline and replays
    each backend invocation's own frozen inputs and provider evidence.
    """
    from refracto.declaration.flows import load_flow
    from refracto.flow import FlowExecution

    _parse_run_time(run_time)
    declaration = load_flow(path, file_config=file_config)
    scenario = declaration.scenario
    unknown = set(projections) - _VALID_PROJECTIONS
    if unknown:
        raise ValueError(f"unknown projection(s): {sorted(unknown)}; valid: {sorted(_VALID_PROJECTIONS)}")
    if adapters.normalizer is None:
        raise ValueError("adapters.normalizer is required (a ResponseNormalizer)")
    needs_ui = any(step.action in ("open", "click", "fill", "press", "hover") or step.expect.frontend
                   for step in scenario.steps)
    if adapters.ui is None and ("frontend" in projections or ("e2e" in projections and needs_ui)):
        raise ValueError("frontend/e2e projection requested but no UiDriver was provided")
    if "contract" in projections and "backend" not in projections:
        raise ValueError("the contract projection consumes provider recordings produced by the "
                         "backend projection and cannot run on its own; add 'backend' to projections")
    poll_config = poll_config or PollConfig()
    executions = bind_projection_values(scenario, projections, run_time=run_time)
    report = FlowReport(declaration.id, uuid4().hex,
        source_lookup=copy.deepcopy(scenario.source_lookup),
        source_pins=copy.deepcopy(getattr(declaration, "source_pins", declaration.dependencies)),
        scenarios=[FlowScenarioReport(node.scenario_id, node_id=node.id,
            source_lookup={key: copy.deepcopy(value) for key, value in scenario.source_lookup.items()
                           if key in node.step_ids}) for node in declaration.nodes])
    report.run_unique_values = {name: copy.deepcopy(bound.run_unique_values)
                                for name, bound in executions.items()}
    if executions:
        first = next(iter(executions.values()))
        report.run_time = first.run_time
        report.run_time_source = first.run_time_source
        report.run_time_values = copy.deepcopy(first.run_time_values)
    boundaries, domains = {}, {}
    for projection in ("backend", "frontend", "e2e"):
        if projection not in projections:
            continue
        execution = executions[projection]
        boundary = FlowExecution(declaration, projection)
        common = dict(normalizer=adapters.normalizer, now=now, sleep=sleep,
                      flow_execution=boundary)
        if projection == "frontend":
            domain = frontend_proj.run(execution, ui=adapters.ui, auth=adapters.auth,
                                       mock_plan=mock_plan, **common)
        else:
            run = backend_proj.run if projection == "backend" else e2e_proj.run
            extra = {} if projection == "backend" else {"ui": adapters.ui}
            domain = run(execution, auth=adapters.auth, api=adapters.api, state=adapters.state,
                recorder=adapters.recorder_factory(), resolve_request=adapters.resolve_request,
                poll_config=poll_config, object_state=adapters.object_state, **common, **extra)
        boundary.complete(domain, execution)
        boundaries[projection] = boundary
        report.parameter_history[projection] = boundary.history
        domains[projection] = boundary.domains(domain)
        for node_report, node_domain in zip(report.scenarios, domains[projection]):
            node_report.domains.append(node_domain)
    if "contract" in projections:
        report.parameter_history["contract"] = copy.deepcopy(report.parameter_history["backend"])
        for node_report, outcome, backend_domain in zip(
                report.scenarios, boundaries["backend"].outcomes, domains["backend"]):
            node_ids = set(outcome.node.step_ids)
            executed = [item for item in outcome.steps if item.step_id in node_ids]
            flow_blocks = {item.step_id: tuple(item.blocked_by) for item in executed
                           if item.status == BLOCKED and (outcome.stopped or
                               any(cause.startswith("flow:") for cause in item.blocked_by))}
            domain = contract_proj.run(copy.deepcopy(outcome.scenario),
                copy.deepcopy(backend_domain.provider_recordings), adapters.normalizer,
                execution_steps=copy.deepcopy(executed), flow_blocks=flow_blocks)
            # Boundary and recorder failures are evidence failures, not authored
            # leaves. Keep them visible without inventing contract provenance.
            domain.steps.extend(copy.deepcopy(item) for item in outcome.steps if item.step_id not in node_ids)
            if outcome.stopped and not domain.steps:
                domain.steps = copy.deepcopy(executed)
            domain.flow_reads = copy.deepcopy(outcome.reads)
            domain.flow_writes = copy.deepcopy(outcome.writes)
            domain.flow_after_failures = list(backend_domain.flow_after_failures)
            node_report.domains.append(domain)
    return report
