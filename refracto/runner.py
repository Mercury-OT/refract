"""Scenario orchestrator.

Load a scenario, apply grid selection, run the requested projections through
adapter ports, and aggregate the results into a RunReport. The contract
projection consumes provider recordings produced by the backend projection.
"""
from dataclasses import dataclass
from refracto.declaration.loader import load_scenario
from refracto import grid
from refracto.report import RunReport
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
    resolve_request: object             # callable(scenario, step, template) -> RequestSpec
    resolve_precondition: object = None
    normalizer: object = None           # ResponseNormalizer


_VALID_PROJECTIONS = {"backend", "frontend", "e2e", "contract"}


def run_scenario(path, adapters, *, projections=("backend", "frontend", "e2e", "contract"),
                 level=None, module=None, poll_config=None, now=None, sleep=None):
    poll_config = poll_config or PollConfig()
    scenario = load_scenario(path)
    report = RunReport(scenario_id=scenario.id)

    unknown = set(projections) - _VALID_PROJECTIONS
    if unknown:
        raise ValueError(f"unknown projection(s): {sorted(unknown)}; valid: {sorted(_VALID_PROJECTIONS)}")
    if adapters.normalizer is None:
        raise ValueError("adapters.normalizer is required (a ResponseNormalizer)")

    if not grid.select(scenario, level=level, module=module):
        # A filtered-out scenario is not a silent pass.
        report.selected = False
        return report

    provider_recordings = []
    if "backend" in projections:
        rec = adapters.recorder_factory()
        d = backend_proj.run(scenario, auth=adapters.auth, api=adapters.api,
                             state=adapters.state, recorder=rec,
                             resolve_request=adapters.resolve_request,
                             resolve_precondition=adapters.resolve_precondition,
                             normalizer=adapters.normalizer, poll_config=poll_config,
                             now=now, sleep=sleep)
        provider_recordings = d.provider_recordings
        report.domains.append(d)
    if "frontend" in projections:
        report.domains.append(frontend_proj.run(scenario, ui=adapters.ui, auth=adapters.auth,
                                                 normalizer=adapters.normalizer))
    if "e2e" in projections:
        rec = adapters.recorder_factory()
        report.domains.append(e2e_proj.run(scenario, auth=adapters.auth, ui=adapters.ui,
                                            state=adapters.state, recorder=rec,
                                            resolve_precondition=adapters.resolve_precondition,
                                            normalizer=adapters.normalizer, poll_config=poll_config,
                                            now=now, sleep=sleep))
    if "contract" in projections:
        # A scenario with any templated step path degrades the contract
        # projection. In that case, avoid a real backend run solely to gather
        # recordings that the contract projection will not consume.
        templated = any(step.request is not None and "{" in step.request.path
                        for step in scenario.steps)
        if templated:
            report.domains.append(contract_proj.run(scenario, [], adapters.normalizer))
        else:
            if not provider_recordings:
                rec = adapters.recorder_factory()
                b = backend_proj.run(scenario, auth=adapters.auth, api=adapters.api,
                                     state=adapters.state, recorder=rec,
                                     resolve_request=adapters.resolve_request,
                                     resolve_precondition=adapters.resolve_precondition,
                                     normalizer=adapters.normalizer, poll_config=poll_config,
                                     now=now, sleep=sleep)
                provider_recordings = b.provider_recordings
            report.domains.append(contract_proj.run(scenario, provider_recordings, adapters.normalizer))
    return report
