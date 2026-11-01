"""Projection-local Scenario boundaries and atomic Flow parameter publication."""
import copy
from dataclasses import dataclass, field

from refracto.declaration.model import Input, ResultSource, ValueRef
from refracto.declaration import values
from refracto.declaration.field_comparison import require_data
from refracto.report import (BLOCKED, ERROR, PASSED, DomainResult,
                             FlowValueProvenance, FlowValueSnapshot, StepResult)


@dataclass
class _Slot:
    provenance: FlowValueProvenance
    value: object = field(default=None, repr=False, metadata={"sensitive": True})


@dataclass
class NodeExecution:
    node: object
    scenario: object = field(repr=False, metadata={"sensitive": True})
    reads: dict = field(default_factory=dict)
    writes: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    stopped: bool = False


class FlowExecution:
    """One store per projection; hooks preserve the projection's session lifetime.

    Only the input slots belonging to the newly entered invocation are replaced.
    Their copies remain frozen for its entire execution and for contract replay.
    """

    def __init__(self, declaration, projection):
        self.declaration = declaration
        self.projection = projection
        self.outcomes = []
        self.changed = False
        self._nodes = {step_id: node for node in declaration.nodes for step_id in node.step_ids}
        self._store = {name: _Slot(FlowValueProvenance(0, item.initialized),
                                   copy.deepcopy(item.initial))
                       for name, item in declaration.parameters.items()}
        self._history = {name: [] for name in self._store}
        self._active = None
        self._start = 0
        self._stopped_by = None
        self._snapshot = {}

    def before(self, step, scenario, results, prior_norms):
        node = self._nodes[step.id]
        self.changed = self._active is None or self._active.node.id != node.id
        if self.changed:
            self.finish(results, prior_norms)
            self._snapshot = copy.deepcopy(self._store)
            reads = {name: self._snapshot[name].provenance
                     for name in dict.fromkeys(node.read_inputs.values())}
            scenario.flow_input_sources.update(node.read_inputs)
            scenario.inputs = [Input(item.kind, copy.deepcopy(self._snapshot[node.read_inputs[item.kind]].value)
                                     if self._snapshot[node.read_inputs[item.kind]].provenance.available
                                     else ValueRef("flow", node.read_inputs[item.kind]))
                               if item.kind in node.read_inputs else item for item in scenario.inputs]
            frozen = copy.deepcopy(scenario)
            frozen.steps = [item for item in frozen.steps if item.id in node.step_ids]
            self._active = NodeExecution(node, frozen, reads=reads, stopped=self._stopped_by is not None)
            self._start = len(results)
        if self._stopped_by is not None:
            return StepResult(step.id, BLOCKED, detail="a prior Scenario stopped this Flow projection",
                              blocked_by=[self._stopped_by], user=scenario.effective_user(step))
        return None

    def _value(self, source, prior_norms):
        if isinstance(source, ResultSource):
            if source.from_step not in self._active.node.step_ids:
                raise ValueError("Flow write response is outside its Scenario")
            norm = prior_norms.get(source.from_step)
            if norm is None or type(norm.fields) is not dict or source.response_field not in norm.fields:
                raise ValueError("Flow write response source is unavailable")
            value = norm.fields[source.response_field]
        elif source.source == "flow":
            slot = self._snapshot[source.key]
            if not slot.provenance.available:
                raise ValueError("Flow write snapshot source is unavailable")
            value = slot.value
        else:
            value, error = values.resolve(source, inputs=self._active.scenario.inputs)
            if error is not None:
                raise ValueError("Flow write parameter source is unavailable")
        require_data(value)
        return copy.deepcopy(value)

    def _provenance(self, name, source, available):
        version = self._store[name].provenance.version + 1
        if isinstance(source, ResultSource):
            result = next((item for item in self._active.steps if item.step_id == source.from_step), None)
            return FlowValueProvenance(version, available, self._active.node.id,
                "response", source.from_step, source.response_field,
                copy.deepcopy(result.response_origin) if result is not None else None)
        previous = self._snapshot.get(source.key) if source.source == "flow" else None
        return FlowValueProvenance(version, available, self._active.node.id,
            source.source, source.key, source_version=(previous.provenance.version if previous else None))

    def finish(self, results, prior_norms):
        if self._active is None:
            return
        self._active.steps = list(results[self._start:])
        publish = DomainResult(self.projection, steps=self._active.steps).status == PASSED
        writes = self._active.node.write_flow
        resolved = {}
        if publish:
            try:
                # Resolve every value before changing any destination, including
                # sources that name one of this same invocation's destinations.
                resolved = {name: self._value(source, prior_norms) for name, source in writes.items()}
            except Exception:
                error = StepResult("@flow-write:" + self._active.node.id, ERROR,
                                   detail="Flow publication source is unavailable or invalid")
                results.append(error)
                self._active.steps.append(error)
                publish = False
        for name, source in writes.items():
            provenance = self._provenance(name, source, publish)
            self._history[name].append(self._store[name])
            self._store[name] = _Slot(provenance, resolved[name] if publish else None)
            self._active.writes[name] = provenance
        if not publish and self.declaration.on_failure == "stop" and self._stopped_by is None:
            failed = [item.step_id for item in self._active.steps
                      if item.status in (ERROR, "FAILED", BLOCKED, "SKIPPED") or item.skipped]
            self._stopped_by = (failed[-1] if failed else self._active.node.step_ids[-1])
        self.outcomes.append(self._active)
        self._active = None

    @property
    def history(self):
        return {name: [FlowValueSnapshot(copy.deepcopy(slot.provenance), copy.deepcopy(slot.value))
                       for slot in [*self._history[name], current]]
                for name, current in self._store.items()}

    def complete(self, domain, scenario):
        """Represent an engine's preflight failure that preceded its step loop."""
        if len(self.outcomes) == len(self.declaration.nodes):
            return
        if self.outcomes or self._active is not None:
            raise RuntimeError("Flow engine did not finish its Scenario boundaries")
        original = {item.step_id: item for item in domain.steps}
        failures = [item.step_id for item in domain.steps if item.status == ERROR]
        self._stopped_by = failures[0] if failures else "@flow-preflight"
        results = []
        for node in self.declaration.nodes:
            for step in (item for item in scenario.steps if item.id in node.step_ids):
                blocked = self.before(step, scenario, results, {})
                results.append(original.pop(step.id, blocked))
        results.extend(original.values())
        self.finish(results, {})
        domain.steps = results

    def domains(self, domain):
        """Split engine evidence without losing out-of-band final failures."""
        result = []
        prior_failures = []
        for outcome in self.outcomes:
            ids = set(outcome.node.step_ids)
            result.append(DomainResult(self.projection, steps=list(outcome.steps),
                skipped=list(domain.skipped),
                not_checked=[item for item in domain.not_checked
                             if any(item.startswith(step_id + ":") for step_id in ids)
                             or not any(item.startswith(step_id + ":") for step_id in self._nodes)],
                mock_consumption=[item for item in domain.mock_consumption if item.get("step_id") in ids],
                provider_recordings=[item for item in domain.provider_recordings if item.step_id in ids],
                flow_reads=copy.deepcopy(outcome.reads), flow_writes=copy.deepcopy(outcome.writes),
                flow_after_failures=list(prior_failures)))
            if result[-1].status != PASSED:
                prior_failures.append(outcome.node.id)
        return result
