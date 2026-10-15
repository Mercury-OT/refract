"""Current named-result declarations for the three frozen backend controls.

The original harness and measurements remain byte-for-byte historical evidence.
These include declarations are independently authored, not generated from the
expander. Fault injection and response normalization reuse the original service.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

from refracto import ports
from refracto.runner import Adapters, run_scenario
from tests import include_fault_controls as frozen


CHILD_CREATE = """schema_version: 1
scenario: control.create
actor: editor
parameters:
  record_name: default-name
steps:
  - id: create
    do:
      request:
        method: POST
        path: [records]
        body:
          name: {from_parameter: record_name}
    expect:
      response:
        - check: success
        - check: has
          field: id
        - check: field_equals
          field: name
          value: {from_parameter: record_name}
results:
  record_id:
    from_step: create
    response_field: id
"""

INCLUDE_COLLECTION = """schema_version: 1
scenario: control.collection
actor: editor
parameters:
  record_name: target-name
steps:
  - id: setup
    do: {include: control.create}
    with:
      record_name: {from_parameter: record_name}
  - id: list
    do:
      request:
        method: GET
        path: [records]
    expect:
      response:
        - check: success
        - check: collection_matching_count
          field: records
          matching:
            id: {from_step: setup, result: record_id}
            name: {from_parameter: record_name}
          count: 1
  - id: after
    do:
      request:
        method: GET
        path: [records, {from_step: setup, result: record_id}]
    expect:
      response:
        - check: success
"""

INCLUDE_WRONG_OBJECT = """schema_version: 1
scenario: control.wrong_object
actor: editor
parameters:
  record_name: target-name
steps:
  - id: setup
    do: {include: control.create}
    with:
      record_name: {from_parameter: record_name}
  - id: read
    do:
      request:
        method: GET
        path: [records, {from_step: setup, result: record_id}]
    expect:
      response:
        - check: success
        - check: field_equals
          field: id
          value: {from_step: setup, result: record_id}
        - check: field_equals
          field: name
          value: {from_parameter: record_name}
  - id: after
    do:
      request:
        method: GET
        path: [records]
    expect:
      response:
        - check: success
"""

# The rejection case has no response dependency, so its approved bytes need no
# migration. All flat declarations remain the original independent controls.
FIXTURES = {
    "accepted_rejection": (
        frozen.INCLUDE_REJECTION, frozen.CHILD_REJECTION, "control.reject"),
    "changed_collection_target": (
        INCLUDE_COLLECTION, CHILD_CREATE, "control.create"),
    "wrong_object_read": (
        INCLUDE_WRONG_OBJECT, CHILD_CREATE, "control.create"),
}


def write_control(directory, fault):
    parent, child, child_id = FIXTURES[fault]
    path = directory / "scenario.yaml"
    path.write_text(parent, encoding="utf-8")
    child_bytes = child.encode("utf-8")
    (directory / "child.yaml").write_bytes(child_bytes)
    (directory / "scenario.includes.json").write_text(json.dumps({
        "manifest_version": 1,
        "scenarios": {child_id: {
            "path": "child.yaml", "sha256": hashlib.sha256(child_bytes).hexdigest(),
        }},
    }), encoding="utf-8")
    return path


def run_control(fault, form="flat", *, inject=True):
    """Run unchanged flat controls or current-syntax include controls.

Only the declaration interface differs. The actual service, injected faults,
transport evidence, assertions, and classification rules stay the same.
"""
    if form == "flat":
        return frozen.run_control(fault, form, inject=inject)
    if form != "include":
        raise ValueError("unknown control form")
    api = frozen.ControlApi(fault if inject else None)
    adapters = Adapters(
        auth=frozen.ControlAuth(), api=api, state=None, ui=None,
        recorder_factory=frozen.ControlRecorder,
        resolve_request=lambda scenario, step, template: ports.RequestSpec(
            template.method, template.path, copy.deepcopy(template.body)),
        normalizer=frozen.ControlNormalizer(),
    )
    try:
        with tempfile.TemporaryDirectory(prefix="refract-named-results-control-") as directory:
            report = run_scenario(write_control(Path(directory), fault), adapters,
                                  projections=("backend",))
    except Exception as exc:
        return {"fault": fault, "form": form, "injected": inject,
                "classification": "invalid_control", "error_type": type(exc).__name__,
                "fault_reached": api.reached, "requests": api.sent}
    domain = report.domains[0]
    failures = [{"step": check.step.removeprefix("setup/"), "check": check.check}
                for check in domain.checks if not check.ok]
    statuses = [(step.step_id.removeprefix("setup/"), step.status) for step in domain.steps]
    expected_failure = {
        "accepted_rejection": {"step": "reject", "check": "failure"},
        "changed_collection_target": {"step": "list", "check": "collection_matching_count"},
        "wrong_object_read": {"step": "read", "check": "field_equals"},
    }[fault]
    valid = not any(status == "ERROR" for _, status in statuses)
    if inject:
        valid = valid and api.reached == 1
        detected = report.status == "FAILED" and failures == [expected_failure]
        outcome = "detected" if valid and detected else "missed" if valid else "invalid_control"
    else:
        outcome = "passing_neighbor" if valid and report.status == "PASSED" else "invalid_control"
    return {"fault": fault, "form": form, "injected": inject, "classification": outcome,
            "status": report.status, "fault_reached": api.reached,
            "failures": failures, "steps": statuses, "requests": api.sent,
            "observed": api.observed, "degradations": report.degradations()}
