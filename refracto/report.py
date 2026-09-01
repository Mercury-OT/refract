"""Run-result models and status semantics.

This module makes execution outcomes explicit:

* nothing that did not run may read as a silent pass
* graceful degradation remains visible
* control-flow outcomes are modeled as first-class step results

Hierarchy:

RunReport -> DomainResult -> StepResult -> CheckResult
"""
from dataclasses import dataclass, field

PASSED = "PASSED"            # ran >=1 check, all ok, nothing skipped
FAILED = "FAILED"            # >=1 failing check
DEGRADED = "DEGRADED"        # no failures, but a declared point was skipped
EMPTY = "EMPTY"              # selected/ran but asserted nothing
NOT_SELECTED = "NOT_SELECTED"  # grid filtered this scenario out — it did not run
SKIPPED = "SKIPPED"          # a step did not run as a tolerated outcome
BLOCKED = "BLOCKED"          # a step could not run because a prior step stopped the flow
ERROR = "ERROR"              # a step raised/errored rather than failing a check


@dataclass
class CheckResult:
    point: str
    check: str
    ok: bool
    detail: str = ""
    step: str = ""


@dataclass
class StepResult:
    step_id: str
    status: str
    checks: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    attempts: int = 1
    trace_id: object = None
    detail: str = ""
    resolved_bindings: dict[str, object] = field(
        default_factory=dict,
        repr=False,
        compare=False,
        kw_only=True,
        metadata={"sensitive": True},
    )


@dataclass
class DomainResult:
    projection: str
    steps: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    provider_recordings: list = field(default_factory=list)

    @property
    def checks(self):
        return [c for s in self.steps for c in s.checks]

    @property
    def status(self):
        sts = [s.status for s in self.steps]
        if ERROR in sts or FAILED in sts:
            return FAILED
        if SKIPPED in sts or any(s.skipped for s in self.steps) or self.skipped:
            return DEGRADED
        if any(s.checks for s in self.steps):
            return PASSED
        return EMPTY

    @property
    def passed(self):
        return self.status in (PASSED, DEGRADED)


@dataclass
class RunReport:
    scenario_id: str
    domains: list = field(default_factory=list)
    selected: bool = True

    @property
    def status(self):
        if not self.selected:
            return NOT_SELECTED
        if not self.domains:
            return EMPTY
        ds = [d.status for d in self.domains]
        if FAILED in ds:
            return FAILED
        if all(s == EMPTY for s in ds):
            return EMPTY
        if any(s in (EMPTY, DEGRADED) for s in ds):
            return DEGRADED
        return PASSED

    @property
    def passed(self):
        return self.status in (PASSED, DEGRADED)

    def degradations(self):
        """Return ``(projection, step_id, reason)`` for every skipped item.

        Domain-level reasons have no owning step and therefore use ``None`` as
        their step id.
        """
        out = []
        for domain in self.domains:
            out.extend(
                (domain.projection, None, reason)
                for reason in domain.skipped
            )
            for step in domain.steps:
                out.extend(
                    (domain.projection, step.step_id, reason)
                    for reason in step.skipped
                )
        return out

    def localize(self):
        out = []
        for d in self.domains:
            for c in d.checks:
                if not c.ok:
                    out.append((d.projection, c.step, c.point, c.check, c.detail))
        return out


# BLOCKED steps always co-occur with the prior FAILED/SKIPPED cause that
# stopped the flow, so DomainResult.status does not need a separate BLOCKED
# branch.
