"""One-shot object observations shared by live execution projections.

Only selectors cross the probe boundary. Comparison and report ownership stay
in core; this is not an independent authentication of an adapter's claims.
"""
import copy
from dataclasses import fields
import secrets

from refracto import ports
from refracto.declaration import field_comparison, values
from refracto.declaration import object_state as declaration
from refracto.report import CheckResult


class ObservationError(ValueError):
    """Safe, value-free failure of object-state evidence acquisition."""


def assertions(step):
    return [a for a in step.expect.backend_state if a.check == declaration.CHECK]


def _name(value):
    return type(value) is str and bool(value.strip())


def _snapshot(facts, query):
    if type(facts) is not ports.ObjectStateFacts or type(facts.query) is not ports.ObjectStateQuery:
        raise ValueError()
    if (type(facts.query.fields) is not tuple
            or any(type(name) is not str for name in facts.query.fields)
            or not all(values.equal(getattr(facts.query, item.name), getattr(query, item.name))
                       for item in fields(ports.ObjectStateQuery))):
        raise ValueError()
    if not _name(facts.source) or type(facts.complete) is not bool or type(facts.objects) is not list:
        raise ValueError()
    for item in facts.objects:
        if type(item) is not ports.ObservedObject:
            raise ValueError()
        declaration.require_id(item.id)
        if not values.equal(item.id, query.id):
            raise ValueError()
        if (type(item.fields) is not dict or any(type(key) is not str for key in item.fields)
                or not set(item.fields).issubset(query.fields)):
            raise ValueError()
        field_comparison.require_data(item.fields)
    return copy.deepcopy(facts)


def observe(step, probe, trace_id, *, projection, user, session_generation,
            observations, bound_values=None, inputs=None):
    """Return checks/skips and retain snapshots in a core-owned evidence list."""
    selected = assertions(step)
    if not selected:
        return [], []
    if probe is None:
        return [], ["object_field_equals — no ObjectStateProbe (object-state evidence unavailable)"]
    if (projection not in {"backend", "e2e"} or not _name(trace_id)
            or not _name(step.id) or (user is not None and not _name(user))
            or type(session_generation) is not int
            or (session_generation != 0 if user is None else session_generation < 1)):
        raise ObservationError("Object state execution identity is unavailable")

    # Resolve the complete selection before the first query. Binding preparation
    # normally already did this before the action; retain a defensive boundary.
    groups = {}
    try:
        for assertion in selected:
            params = assertion.params
            identity, error = values.resolve(params["id"], bound_values=bound_values, inputs=inputs)
            expected, expected_error = values.resolve(params["value"], bound_values=bound_values, inputs=inputs)
            if error is not None or expected_error is not None:
                raise ValueError()
            declaration.require_id(identity)
            declaration.require_expected(expected)
            if not _name(params["object"]) or not _name(params["field"]):
                raise ValueError()
            key = (params["object"], type(identity), identity)
            groups.setdefault(key, []).append((params["field"], expected))
    except Exception:
        raise ObservationError("Object state selection or expected value is invalid") from None

    checks = []
    for (object_name, _, identity), comparisons in groups.items():
        query = ports.ObjectStateQuery(
            observation_id=secrets.token_hex(16), projection=projection,
            step_id=step.id, trace_id=trace_id, user=user,
            session_generation=session_generation, object=object_name, id=identity,
            fields=tuple(sorted({name for name, _ in comparisons})),
        )
        try:
            facts = probe.observe_object(copy.deepcopy(query))
        except Exception:
            raise ObservationError("Object state query failed") from None
        try:
            snapshot = _snapshot(facts, query)
        except Exception:
            raise ObservationError("Object state returned invalid evidence") from None
        observations.append(snapshot)
        if not snapshot.complete:
            raise ObservationError("Object state observation is incomplete")
        if len(snapshot.objects) > 1:
            raise ObservationError("Object state identity is ambiguous")
        observed = snapshot.objects[0].fields if snapshot.objects else {}
        for name, expected in comparisons:
            ok = bool(snapshot.objects) and name in observed and values.equal(observed[name], expected)
            detail = "" if ok else f"object field {name!r} absent or unequal"
            checks.append(CheckResult("backend_state", declaration.CHECK, ok, detail, step=step.id))
    return checks, []
