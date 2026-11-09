"""Read-only object observations shared by live execution projections.

Only selectors cross the probe boundary. Comparison and report ownership stay
in core; this is not an independent authentication of an adapter's claims.
"""
import copy
from dataclasses import fields
import math
import secrets
import time

from refracto import ports
from refracto.declaration import field_comparison, values
from refracto.declaration import object_state as declaration
from refracto.report import CheckResult, ObjectPollResult


class ObservationError(ValueError):
    """Safe, value-free failure of object-state evidence acquisition."""


def assertions(step):
    return [a for a in step.expect.backend_state if a.check in declaration.CHECKS]


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


def _selection(selected, bound_values, inputs):
    # Resolve the complete selection before the first query. Binding preparation
    # normally already did this before the action; retain a defensive boundary.
    groups = {}
    try:
        for assertion in selected:
            params = assertion.params
            identity, error = values.resolve(params["id"], bound_values=bound_values, inputs=inputs)
            if error is not None:
                raise ValueError()
            declaration.require_id(identity)
            if not _name(params["object"]):
                raise ValueError()
            name, expected = None, None
            if assertion.check == declaration.CHECK:
                expected, error = values.resolve(params["value"], bound_values=bound_values, inputs=inputs)
                if error is not None or not _name(params["field"]):
                    raise ValueError()
                declaration.require_expected(expected)
                name = params["field"]
            key = (params["object"], type(identity), identity)
            groups.setdefault(key, []).append((assertion.check, name, expected))
    except Exception:
        raise ObservationError("Object state selection or expected value is invalid") from None

    return groups


def _read(probe, query, observations):
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
    return snapshot


def _compare(snapshot, comparisons, step_id):
    observed = snapshot.objects[0].fields if snapshot.objects else {}
    checks = []
    for check, name, expected in comparisons:
        if check == declaration.ABSENT_CHECK:
            ok = not snapshot.objects
            detail = "" if ok else "object is present"
        else:
            ok = bool(snapshot.objects) and name in observed and values.equal(observed[name], expected)
            detail = "" if ok else f"object field {name!r} absent or unequal"
        checks.append(CheckResult("backend_state", check, ok, detail, step=step_id))
    return checks


def poll_metadata(step, config):
    if step.object_poll is None:
        return None
    timeout, interval = (config.timeout, config.interval) if config is not None else (30.0, 1.0)
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (timeout, interval))
            or not 0 < interval <= timeout):
        raise ObservationError("Object state polling timing is invalid")
    return ObjectPollResult(timeout, interval)


def _poll(read, metadata, now, sleep):
    """Bound new reads and late success, without pretending to cancel a sync port."""
    clock, pause = now or time.monotonic, sleep or time.sleep
    previous = None

    def instant():
        nonlocal previous
        try:
            current = clock()
            if (type(current) not in (int, float) or not math.isfinite(current)
                    or previous is not None and current < previous):
                raise ValueError()
        except Exception:
            raise ObservationError("Object state polling clock is invalid") from None
        previous = current
        return current

    start = instant()
    checks = []
    try:
        while True:
            metadata.elapsed = instant() - start
            if metadata.elapsed >= metadata.timeout:
                metadata.outcome = "timeout"
                return checks
            metadata.attempts += 1
            # Invalid evidence remains ERROR even if the read returns late.
            checks = read()
            metadata.elapsed = instant() - start
            if metadata.elapsed >= metadata.timeout:
                metadata.outcome = "timeout"
                return checks
            if all(check.ok for check in checks):
                metadata.outcome = "matched"
                return checks
            try:
                pause(min(metadata.interval, metadata.timeout - metadata.elapsed))
            except Exception:
                raise ObservationError("Object state polling wait failed") from None
    except ObservationError:
        metadata.outcome = "error"
        metadata.elapsed = instant() - start
        raise


def observe(step, probe, trace_id, *, projection, user, session_generation,
            observations, bound_values=None, inputs=None, poll_result=None,
            now=None, sleep=None):
    """Return terminal checks/skips and retain every valid core-owned snapshot."""
    selected = assertions(step)
    if not selected:
        return [], []
    if probe is None:
        if poll_result is not None:
            poll_result.outcome = "unavailable"
        return [], [f"{check} — no ObjectStateProbe (object-state evidence unavailable)"
                    for check in dict.fromkeys(a.check for a in selected)]
    if (projection not in {"backend", "e2e"} or not _name(trace_id)
            or not _name(step.id) or (user is not None and not _name(user))
            or type(session_generation) is not int
            or (session_generation != 0 if user is None else session_generation < 1)):
        raise ObservationError("Object state execution identity is unavailable")
    groups = _selection(selected, bound_values, inputs)
    if poll_result is not None and len(groups) != 1:
        raise ObservationError("Object state polling requires one exact selection")

    def read():
        checks = []
        for (object_name, _, identity), comparisons in groups.items():
            query = ports.ObjectStateQuery(
                observation_id=secrets.token_hex(16), projection=projection,
                step_id=step.id, trace_id=trace_id, user=user,
                session_generation=session_generation, object=object_name, id=identity,
                fields=tuple(sorted({name for check, name, _ in comparisons if check == declaration.CHECK})),
            )
            snapshot = _read(probe, query, observations)
            checks.extend(_compare(snapshot, comparisons, step.id))
        return checks

    return (read() if poll_result is None else _poll(read, poll_result, now, sleep)), []
