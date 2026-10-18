"""Fourteen frozen backend controls; no target receives an expected value."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario
from tests.test_documents_failure_continuation import ChangedCreation
from tests.test_field_comparison_consumers import DocumentsFaults as ComparisonFaults
from tests.test_header_documents import DuplicateCreationWithOldIdentifier
from tests.test_member_reference_consumers import DocumentsFaults as MemberFaults
from tests.test_rejection_evidence import ChangedPeerReason


ROOT = Path(__import__("refracto").__file__).resolve().parents[1]
SCENARIOS = "examples/documents/scenarios/"
ROWS = {
    "F01": ("continue_after_failure.yaml", "assertion", 1, 3, [("create", "status_equals")]),
    "F02": ("continue_after_failure.yaml", "assertion", 1, 3,
             [("create", "field_equals"), ("read", "collection_matching_count")]),
    "F03": ("permission_sessions.yaml", "assertion", 1, 6,
             [("old_session", "status_equals"), ("old_session", "failure")]),
    "G01": ("owner_peer.yaml", "guard", 2, 0, []),
    "F04": ("owner_access.yaml", "assertion", 1, 4, [("peer_reads", "field_equals")]),
    "F05": ("filter_and_next_page.yaml", "assertion", 2, 5,
             [("next_page", "collection_matching_count"), ("next_page", "field_equals")]),
    "F06": ("mapped_anonymous_access.yaml", "assertion", 2, 5,
             [("access/reader_denied", "status_in"), ("access/reader_denied", "failure"),
              ("access/reader_denied", "has"), ("exact_refusal", "status_equals"),
              ("exact_refusal", "failure"), ("exact_refusal", "field_equals")]),
    "F07": ("idempotent_create.yaml", "assertion", 1, 3,
             [("find_document", "collection_matching_count")]),
    "F08": ("continue_after_failure.yaml", "assertion", 1, 1, [("create", "header_equals")]),
    "F09": ("rejected_update_preserves_content.yaml", "assertion", 1, 4,
             [("read_after", "field_equals"), ("read_after", "field_not_equals")]),
    "G02": ("locate_update_read.yaml", "guard", 1, 3, []),
    "F10": ("check_page_limits.yaml", "assertion", 1, 4,
             [("first_page", "field_compare"), ("first_page", "collection_length"),
              ("first_page", "field_not_equals")]),
    "C01": ("continue_after_failure.yaml", "engine", 1, 3,
             [("create", "field_equals"), ("read", "collection_matching_count")]),
    "C02": ("continue_after_failure.yaml", "engine", 1, 3,
             [("create", "field_equals"), ("read", "collection_matching_count")]),
}


def declaration(row):
    """Only two declared test variants; all maintained source YAML stays intact."""
    path = ROOT / SCENARIOS / ROWS[row][0]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if row == "F08":
        raw["steps"] = raw["steps"][:1]
        raw["steps"][0]["expect"]["response"].append({"check": "header_equals",
            "header": "Location", "value": "/v3/documents/document-1"})
    elif row == "G02":
        step = next(item for item in raw["steps"] if item["id"] == "locate")
        step.pop("on_failure")
        step["expect"]["response"] = [{"check": "status_equals", "value": 200}, {"check": "success"}]
    return raw


def declaration_bytes(row):
    return yaml.safe_dump(declaration(row), sort_keys=False).encode("utf-8")


def neighbor_expectation(row):
    ids = [step.id for step in load_scenario(ROOT / SCENARIOS / ROWS[row][0]).steps]
    if row == "F08":
        ids = ids[:1]
    engine = row.startswith("C")
    return {"action_count": len(ids), "reach_count": int(engine),
            "status": "FAILED" if engine else "PASSED",
            "steps": [[step, status] for step, status in zip(ids,
                ["FAILED", "FAILED", "PASSED"] if engine else ["PASSED"] * len(ids), strict=True)]}


def neighbor_valid(row, result):
    expected = neighbor_expectation(row)
    return (result.get("status") == expected["status"] and result.get("degradation_count") == 0
            and result.get("action_count") == expected["action_count"]
            and result.get("reach_count") == expected["reach_count"]
            and [[step["id"], step["status"]] for step in result.get("steps", [])] == expected["steps"])


class ChangedStatus(DocumentRestApp):
    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        return RestResponse(202, response.body, response.headers) if method == "POST" and response.status == 201 else response


class AdmittedAnonymous(DocumentRestApp):
    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if method == "GET" and response.status == 401 and path.startswith("/v3/documents/"):
            return self._accepted("document", deepcopy(self._documents[path.split("/")[-1]]))
        return response


class LocationTarget(DocumentRestApp):
    """Explicit synthetic baseline extension: Location uses the actual new id."""
    def __init__(self, remove=False):
        super().__init__()
        self.remove = remove

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if method == "POST" and response.status == 201:
            values = dict(response.headers)
            values["Location"] = "/v3/documents/" + response.body["resource"]["document"]["identifier"]
            if self.remove:
                del values["Location"]
            return RestResponse(response.status, response.body, values)
        return response


class QueryFault(DocumentRestApp):
    """Record the real query change immediately before the service list handler."""
    def __init__(self, fault):
        super().__init__()
        self.fault = fault
        self.boundary_evidence = []

    def _list(self, query, principal):
        changed = deepcopy(query)
        if self.fault == "ignored_filter" and "category" in changed:
            del changed["category"]
        elif self.fault == "oversized" and "limit" in changed:
            changed["limit"] = [str(int(changed["limit"][0]) + 1)]
        response = super()._list(changed, principal)
        if changed != query:
            self.reach += 1
            self.boundary_evidence.append({"query_before": deepcopy(query), "query_used": changed,
                "returned_members": len(response.body["result_set"]["nodes"])})
        return response


def target(row, inject):
    if row == "F08":
        return LocationTarget(remove=inject)
    if not inject:
        return DocumentRestApp()
    factories = {
        "F01": ChangedStatus, "F02": lambda: ChangedCreation("stored-title"),
        "F03": lambda: DocumentRestApp(permission_policy="session"),
        "G01": DocumentRestApp, "F04": lambda: ChangedPeerReason("validation_failed"),
        "F05": lambda: QueryFault("ignored_filter"), "F06": AdmittedAnonymous,
        "F07": DuplicateCreationWithOldIdentifier,
        "F09": lambda: ComparisonFaults("mutate_on_denial"),
        "G02": lambda: MemberFaults("duplicate"), "F10": lambda: QueryFault("oversized"),
        "C01": lambda: ChangedCreation("stored-title"), "C02": lambda: ChangedCreation("stored-title"),
    }
    return factories[row]()


def _instrument(app, row, inject):
    """Count actual specified mutation boundaries, not just wrapper construction."""
    original = app.handle
    app.reach = 0
    def handle(method, path, body=None, headers=None):
        before_documents = deepcopy(app._documents)
        before_permission = {key: value["read_documents"] for key, value in app._accounts.items()}
        response = original(method, path, body, headers)
        if not inject:
            return response
        reached = False
        if row == "F01":
            reached = method == "POST" and response.status == 202
        elif row in {"F02", "C01", "C02"}:
            reached = method == "POST" and response.status == 201 and any(
                value["properties"]["title"] == "wrong-title" for value in app._documents.values())
        elif row == "F03":
            session = app._sessions.get((headers or {}).get("x-session-key"), {})
            reached = (method == "GET" and response.status == 200 and
                       session.get("user") in before_permission and not before_permission[session["user"]])
        elif row == "F04":
            reached = response.status == 403 and response.body.get("fault", {}).get("code") == "validation_failed"
        elif row == "F06":
            reached = method == "GET" and not (headers or {}).get("x-session-key") and response.status == 200
        elif row == "F07":
            reached = method == "POST" and response.status == 200 and len(app._documents) > len(before_documents)
        elif row == "F08":
            reached = method == "POST" and response.status == 201 and "Location" not in response.headers
        elif row == "F09":
            reached = method == "PATCH" and response.status == 403 and app._documents != before_documents
        elif row == "G02":
            nodes = (response.body or {}).get("result_set", {}).get("nodes", [])
            reached = method == "GET" and len(nodes) > 1 and nodes[-1] == nodes[-2]
        app.reach += int(reached)
        return response
    app.handle = handle


def observe(row, inject):
    app = target(row, inject)
    _instrument(app, row, inject)
    adapters = build_adapters(app)
    if row == "G01" and inject:
        original = adapters.auth.identify
        def identify(user):
            app.reach += 1
            return original("creator")
        adapters.auth.identify = identify
    path = ROOT / SCENARIOS / ROWS[row][0]
    with tempfile.TemporaryDirectory(prefix="refract-stabilization-control-") as directory:
        if row in {"F08", "G02"}:
            path = Path(directory) / "scenario.yaml"
            path.write_bytes(declaration_bytes(row))
        report = run_scenario(path, adapters, projections=("backend",))
    domain = report.domains[0]
    # Deliberately do not serialize credentials, principal ids, or arbitrary report repr.
    return {
        "row": row, "injected": inject, "status": report.status,
        "reach_count": app.reach, "action_count": app.request_count,
        "authentication_count": len(app.authentications),
        "checks": [{"step": c.step, "point": c.point, "check": c.check, "ok": c.ok} for c in domain.checks],
        "steps": [{"id": s.step_id, "status": s.status, "after_failures": s.after_failures,
                   "blocked_by": s.blocked_by, "detail": s.detail if s.status in {"ERROR", "BLOCKED"} else ""}
                  for s in domain.steps],
        "actions": [{"method": method, "path": path, "body": body} for method, path, body, _ in app.requests],
        "responses": [{"step": r.step_id, "status": r.status,
                       "fields": {k: v for k, v in adapters.normalizer.normalize(r).fields.items() if k != "user_id"},
                       "headers": [[k, v] for k, v in (r.header_items or []) if k.lower() != "set-cookie"]}
                      for r in domain.provider_recordings],
        "degradation_count": len(report.degradations()),
        "remaining_documents": len(app._documents),
        "boundary_evidence": getattr(app, "boundary_evidence", []),
    }


def classify(row, result, neighbor):
    _, lane, reach, actions, failures = ROWS[row]
    if not neighbor_valid(row, neighbor):
        return "invalid_control"
    if lane != "guard" and any(step["status"] == "ERROR" for step in result.get("steps", [])):
        return "invalid_control"
    if result["reach_count"] != reach:
        return "not_reached"
    if lane == "guard":
        steps = result["steps"]
        if row == "G01":
            valid = (steps[0]["status"] == "ERROR" and "declared users must identify distinct accounts" in steps[0]["detail"]
                     and all(step["status"] == "BLOCKED" for step in steps[1:])
                     and result["action_count"] == result["authentication_count"] == 0)
        else:
            valid = ([step["status"] for step in steps] == ["PASSED"] * 3 + ["BLOCKED"] * 2
                     and "exactly one" in steps[-2]["detail"] and result["action_count"] == actions
                     and all(action["method"] != "PATCH" for action in result["actions"]))
        return "guard_conformant" if valid else "guard_missed"
    actual = [(check["step"], check["check"]) for check in result["checks"] if not check["ok"]]
    detected = result["status"] == "FAILED" and actual == failures and result["action_count"] == actions
    if row == "F02":
        detected = detected and result["remaining_documents"] == 0 and result["steps"][-1]["after_failures"] == ["create", "read"]
    return "detected" if detected else "missed"


def engine_assertion(result, row):
    """Designated exact assertions; a FAILED business result is the clean outcome."""
    if row == "C01":
        assert result["action_count"] == 3, "C01: later read and delete must execute"
        assert [step["status"] for step in result["steps"]] == ["FAILED", "FAILED", "PASSED"]
    else:
        assert result["action_count"] == 3, "C02 prerequisite: all actions reached"
        assert result["status"] == "FAILED", "C02: later success must not erase earlier failure"
    assert result["reach_count"] == 1


def fixture_hash(row):
    return hashlib.sha256(declaration_bytes(row)).hexdigest()
