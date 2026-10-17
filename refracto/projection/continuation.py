"""Shared projection-local continuation and value-free evidence provenance."""
from dataclasses import replace
from refracto.report import (BLOCKED, ERROR, FAILED, SKIPPED, NOT_APPLICABLE,
                            BindingSource, ResponseOrigin, StepResult)


class FlowState:
    def __init__(self):
        self.failures = []
        self.stopper = None
        self.origins = {}

    def blocked(self, step):
        if self.stopper is None:
            return None
        return StepResult(step.id, BLOCKED, detail="a prior step stopped the flow",
                          blocked_by=[self.stopper], user=step.user)

    def finish(self, step, result, norm=None):
        if result.status not in (BLOCKED, NOT_APPLICABLE):
            result.after_failures = list(self.failures)
        if result.resolved_bindings:
            result.binding_sources = {
                item.placeholder: BindingSource(item.field, self.origins[item.from_step])
                for item in step.bind if item.from_step in self.origins
            }
        if norm is not None:
            if result.response_origin is None:
                result.response_origin = ResponseOrigin(step.id, max(result.attempts - 1, 0), True,
                    user=result.user, session_generation=result.session_generation)
            else:
                result.response_origin = replace(result.response_origin,
                    user=result.user, session_generation=result.session_generation)
            self.origins[step.id] = result.response_origin
        if result.status == FAILED:
            self.failures.append(step.id)
        if result.status in (ERROR, SKIPPED) or (result.status == FAILED and step.on_failure == "stop"):
            self.stopper = step.id
