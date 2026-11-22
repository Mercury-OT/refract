"""Run the four reviewed steps in one live browser and retain bounded local evidence."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import yaml

from refracto.declaration.loader import load_scenario
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario

from .adapters import MattermostHttp, MattermostNormalizer, single_header, strict_json
from .run import sha256, source_manifest, utc_now, write_json


CANONICAL = Path(__file__).with_suffix(".yaml")
CANONICAL_HASH = "144351dd991dd846caf2515292f362d8ad8a4a7e1bf72f37ce8c3640c1a2786f"
ROOT = Path(__file__).resolve().parents[2]
SLOTS = ("channel_path", "channel_id", "member_id")
STEPNAMES = ("enter_channel", "enter_message", "send", "reopen_channel")
UNKNOWN = "UNVERIFIED"


def reviewed_shape(document):
    shape = copy.deepcopy(document)
    del shape["description"]
    for key in SLOTS:
        label = shape["parameters"][key]
        if not isinstance(label, str) or not re.fullmatch(r"<[^<>]+>", label):
            raise ValueError("reviewed input must contain the three unbound slots")
        shape["parameters"][key] = key
    # Canonical JSON also distinguishes booleans and numbers in comparisons.
    return json.dumps(shape, sort_keys=True, allow_nan=False)


def bind_declaration(reviewed_path, fixture, directory):
    if sha256(CANONICAL) != CANONICAL_HASH:
        raise ValueError("public review template hash changed")
    reviewed_bytes = Path(reviewed_path).read_bytes()
    reviewed = directory / "reviewed.yaml"
    reviewed.write_bytes(reviewed_bytes)
    load_scenario(reviewed)
    declaration = yaml.safe_load(reviewed_bytes)
    if reviewed_shape(declaration) != reviewed_shape(yaml.safe_load(CANONICAL.read_bytes())):
        raise ValueError("reviewed declaration differs from the approved four steps")
    for name in SLOTS:
        declaration["parameters"][name] = fixture[name]
    bound = directory / "bound.yaml"
    bound.write_text(yaml.safe_dump(declaration, allow_unicode=True, sort_keys=False), encoding="utf-8")
    load_scenario(bound)
    return bound


def sources():
    return {**source_manifest(), **{
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted((ROOT / "refracto_browser").rglob("*.py"))
    }}


def native_steps(domain):
    return {s.step_id: {
        "status": s.status, "checks": [{"point": c.point, "check": c.check, "ok": c.ok} for c in s.checks],
        "blocked_by": s.blocked_by,
        "reason": s.detail if s.status == "ERROR" else None,
    } for s in domain.steps}


def safe_record(record):
    # A row comes only from the native e2e recorder, after action attribution.
    return {
        "step": record.step_id, "method": record.request.method, "actual_path": record.actual_path,
        "request_id": record.request_id, "user": record.user, "session_generation": record.session_generation,
        "status": record.status,
        "request": select_fields(record.request.body, ("channel_id", "message")),
        "response": select_fields(record.json, ("id", "user_id", "channel_id", "message")),
    }


def select_fields(value, names):
    return {name: value[name] for name in names if name in value} if isinstance(value, dict) else {}


def page_observations(events):
    # Bodies of unrelated messages can be present in a reused isolated fixture.
    # Persist text digests for page evidence, retaining every observation and its ID.
    output = {}
    for step, event in events.items():
        row = select_fields(event, ("action", "target", "action_id", "context_id", "new_document",
                                    "frame_id", "document_before", "document_after", "duration_seconds",
                                    "timeline_complete", "associated_count", "safe_reason"))
        row["rendered"] = {}
        for anchor, field in (("channel.view", "path"), ("channel.composer", "value"),
                              ("channel.posts", "message")):
            source = event.get("rendered", {}).get(anchor)
            if source is None:
                continue
            rows = []
            for kind in ("identified", "anonymous"):
                for obj in source.get(kind, []):
                    item = {"kind": kind, **select_fields(obj, ("id",))}
                    fields = obj["fields"]
                    if anchor == "channel.posts":
                        item.update(select_fields(fields, ("post_id",)))
                    if field in fields and isinstance(fields[field], str):
                        if field == "path":
                            item[field] = fields[field]
                        else:
                            item[field + "_sha256"] = hashlib.sha256(fields[field].encode()).hexdigest()
                    rows.append(item)
            row["rendered"][anchor] = rows
        output[step] = row
    return output


def classify(steps, observations, records):
    """Judge only complete observations and retain successes before any blocker."""
    facts = {}
    sent = [r for r in records if r["step"] == "send"]
    for name in STEPNAMES:
        step = steps.get(name, {})
        event = observations.get(name, {})
        rendered = event.get("rendered", {})
        usable = bool(rendered)
        if name in ("enter_channel", "reopen_channel"):
            usable = (usable and event.get("new_document") is True and
                      event.get("frame_id") and event.get("document_before") and event.get("document_after")
                      and event["document_before"] != event["document_after"] and
                      "channel.view" in rendered)
        if name in ("enter_channel", "enter_message"):
            usable = usable and "channel.composer" in rendered
        if name == "send":
            usable = len(sent) == 1 and sent[0]["method"] == "POST" and sent[0]["actual_path"] == "/api/v4/posts"
        if name == "reopen_channel":
            entered = observations.get("enter_channel", {})
            rows = rendered.get("channel.posts")
            usable = (usable and facts.get("send") == "PASS" and event.get("timeline_complete") is True
                      and entered.get("context_id") and event.get("context_id") == entered["context_id"]
                      and entered.get("frame_id") == event["frame_id"]
                      and entered.get("document_after") != event["document_after"]
                      and isinstance(rows, list) and all(row["kind"] == "identified" and row.get("id")
                      and row.get("post_id") == row["id"] and "message_sha256" in row for row in rows))
        facts[name] = {"PASSED": "PASS", "FAILED": "FAIL"}.get(step.get("status"), UNKNOWN) if usable else UNKNOWN
        if (name == "send" and facts[name] == "PASS"
                and (not isinstance(sent[0]["response"].get("id"), str) or not sent[0]["response"]["id"])):
            facts[name] = "FAIL"
        if name == "reopen_channel" and usable:
            post = sent[0]["response"]
            matches = [row for row in rows if row["post_id"] == post["id"]]
            text = post.get("message")
            if (len(matches) != 1 or not isinstance(text, str) or
                    matches[0]["message_sha256"] != hashlib.sha256(text.encode()).hexdigest()):
                if facts[name] == "PASS":
                    # Sidecar and native disagree. Do not replace the native result.
                    facts[name] = UNKNOWN
    return facts


def run(fixture_path, directory, reviewed_path=CANONICAL):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    started_at, start = utc_now(), time.monotonic()
    fixture = strict_json(fixture_path.read_text(encoding="utf-8"))
    if not all(isinstance(fixture.get(k), str) and fixture[k] for k in SLOTS):
        raise ValueError("fixture is missing an independent binding")
    if not re.fullmatch(r"/[a-z0-9_-]+/channels/[a-z0-9_-]+", fixture["channel_path"]):
        raise ValueError("invalid local channel route")
    bound = bind_declaration(reviewed_path, fixture, directory)
    frozen = {
        "public_template": CANONICAL_HASH, "reviewed": sha256(directory / "reviewed.yaml"),
        "bound": sha256(bound), "fixture": sha256(fixture_path), "sources": sources(),
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "projections": ["e2e"], "started_at": started_at,
    }
    write_json(directory / "freeze.json", frozen)
    result = {"status": UNKNOWN, "native_status": None, "steps": {}, "observations": {}, "recordings": [],
              "strict_pass": False, "obligations": dict.fromkeys(STEPNAMES, UNKNOWN)}
    try:
        from .channel_page import ChannelPageAuth, ChannelPageUi
        ping = MattermostHttp(fixture["base_url"]).exchange("GET", "/api/v4/system/ping")
        version = single_header(ping.headers, "X-Version-Id")
        if (ping.status != 200 or not (version == "11.11.4" or version.startswith("11.11.4.")) or
                fixture["server_version"] not in (version, "11.11.4")):
            raise ValueError("actual server release did not match the fixture")
        result["server_version"] = version
        ui = ChannelPageUi(fixture["base_url"], fixture["channel_path"])
        auth = ChannelPageAuth(fixture["member_id"], fixture["storage_state"])
        adapters = Adapters(auth, None, None, ui, InMemoryRecorder, None, MattermostNormalizer())
        report = run_scenario(bound, adapters, projections=("e2e",))
        domain, = report.domains
        steps = native_steps(domain)
        observations = page_observations(ui.observations)
        records = [safe_record(r) for r in domain.provider_recordings]
        facts = classify(steps, observations, records)
        passed = report.passed and all(v == "PASS" for v in facts.values())
        result.update(native_status=report.status, domain_status=domain.status, steps=steps,
                      observations=observations, recordings=records, obligations=facts, strict_pass=passed,
                      run_unique_values=report.run_unique_values,
                      diagnostic_posts=[select_fields(row, ("method", "path", "status")) for row in ui.diagnostic_posts],
                      status="FAIL" if "FAIL" in facts.values() else "PASS" if passed else UNKNOWN)
    except Exception as exc:
        result["runner_error_type"] = type(exc).__name__
    result["integrity"] = (sha256(directory / "reviewed.yaml") == sha256(reviewed_path) == frozen["reviewed"]
                           and sha256(bound) == frozen["bound"] and sha256(fixture_path) == frozen["fixture"]
                           and sources() == frozen["sources"] and sha256(CANONICAL) == frozen["public_template"])
    if not result["integrity"]:
        result.update(strict_pass=False, status=UNKNOWN)
    result.update(ended_at=utc_now(), elapsed_seconds=time.monotonic() - start)
    payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
    for cookie in fixture["storage_state"]["cookies"]:
        if cookie["name"] in ("MMAUTHTOKEN", "MMCSRF") and cookie["value"] and cookie["value"] in payload:
            result = {"strict_pass": False, "native_status": None, "status": UNKNOWN,
                      "obligations": dict.fromkeys(STEPNAMES, UNKNOWN), "export_error": "credential_reflection"}
            break
    write_json(directory / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--scenario", type=Path, default=CANONICAL)
    args = parser.parse_args()
    result = run(args.fixture, args.output_dir, args.scenario)
    print(json.dumps({"native": result["native_status"], "business": result["status"],
                      "obligations": result["obligations"]}))
    return 0 if result["strict_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
