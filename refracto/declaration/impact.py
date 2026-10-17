"""Bounded, read-only review of one changed include dependency.

This module never executes a Scenario, rewrites a pin, or grants approval.
Hypothetical loads use current callers and current non-target dependencies.
"""
import copy
import hashlib
import json
import math
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

from refracto.declaration.includes import _safe_file, _unique, is_include
from refracto.declaration.loader import DeclarationError, _decode_document, _load_document


@dataclass(frozen=True)
class Limits:
    entries: int = 4096
    yaml_files: int = 512
    files: int = 1024
    file_bytes: int = 2 * 1024 * 1024
    total_bytes: int = 32 * 1024 * 1024


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _pointer(part):
    return str(part).replace("~", "~0").replace("/", "~1")


def _same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


_ABSENT = object()


def _describe(value, show_values):
    if value is _ABSENT:
        return {"type": "absent"}
    names = {type(None): "null", bool: "boolean", int: "integer", float: "number",
             str: "string", list: "array", dict: "object"}
    supported = not (type(value) is float and not math.isfinite(value))
    result = {"type": names.get(type(value), "unsupported") if supported else "unsupported"}
    if show_values and result["type"] != "unsupported":
        result["value"] = copy.deepcopy(value)
    return result


def _changes(before, after, show_values):
    records = []

    def emit(path, left, right, kind=None):
        records.append({"location": path, "kind": kind or (
            "added" if left is _ABSENT else "removed" if right is _ABSENT else "changed"),
            "before": _describe(left, show_values), "after": _describe(right, show_values)})

    def visit(path, left, right):
        if left is _ABSENT or right is _ABSENT or type(left) is not type(right):
            emit(path, left, right)
        elif isinstance(left, dict):
            for key in sorted(left.keys() | right.keys()):
                visit(path + "/" + _pointer(key), left.get(key, _ABSENT), right.get(key, _ABSENT))
        elif isinstance(left, list):
            for i in range(max(len(left), len(right))):
                visit(path + "/" + str(i), left[i] if i < len(left) else _ABSENT,
                      right[i] if i < len(right) else _ABSENT)
        elif not _same(left, right):
            emit(path, left, right)

    for key in sorted(before.keys() | after.keys()):
        if key != "steps":
            visit("/" + _pointer(key), before.get(key, _ABSENT), after.get(key, _ABSENT))
    old_steps = {step["id"]: step for step in before["steps"]}
    new_steps = {step["id"]: step for step in after["steps"]}
    old_order, new_order = list(old_steps), list(new_steps)
    if old_order != new_order:
        emit("/steps", old_order, new_order, "order-changed")
    for sid in sorted(old_steps.keys() | new_steps.keys()):
        # The synthetic by-id segment makes stable review locations explicit.
        visit("/steps/by-id/" + _pointer(sid), old_steps.get(sid, _ABSENT),
              new_steps.get(sid, _ABSENT))
    return sorted(records, key=lambda row: (row["location"], row["kind"]))


class _Snapshot:
    def __init__(self, root, limits):
        self.root = root
        self.limits = limits
        self.cache = {}
        self.failed = set()
        self.gaps = []
        self.entries = 0
        self.discovered = 0
        self.bytes = 0
        self.stopped = False

    def label(self, path):
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return "before:" + path.name

    def gap(self, code, path):
        location = path if isinstance(path, str) else self.label(path)
        item = {"code": code, "location": location}
        if item not in self.gaps:
            self.gaps.append(item)

    def safe(self, path, *, directory=False):
        try:
            for component in (path, *path.parents):
                if component.is_symlink():
                    self.gap("symlink", path)
                    return False
            mode = path.stat().st_mode
            if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
                self.gap("non-regular-input", path)
                return False
            return True
        except FileNotFoundError:
            self.gap("missing-input", path)
        except (OSError, ValueError):
            self.gap("unreadable-input", path)
        return False

    def capture(self, path):
        # Absolute paths are normalized without following a symlink first.
        path = Path(os.path.abspath(path))
        if path in self.cache:
            return self.cache[path]
        if path in self.failed:
            return None
        self.failed.add(path)
        if not self.safe(path):
            return None
        if len(self.cache) >= self.limits.files:
            self.gap("file-count-limit", path)
            return None
        try:
            size = path.stat().st_size
            if size > self.limits.file_bytes:
                self.gap("file-size-limit", path)
                return None
            if self.bytes + size > self.limits.total_bytes:
                self.gap("total-byte-limit", path)
                return None
            allowance = min(self.limits.file_bytes, self.limits.total_bytes - self.bytes)
            with path.open("rb") as stream:
                data = stream.read(allowance + 1)
            if len(data) > self.limits.file_bytes:
                self.gap("file-size-limit", path)
                return None
            if self.bytes + len(data) > self.limits.total_bytes:
                self.gap("total-byte-limit", path)
                return None
        except (OSError, ValueError):
            self.gap("unreadable-input", path)
            return None
        self.bytes += len(data)
        self.cache[path] = data
        self.failed.remove(path)
        return data

    def walk(self):
        paths = []
        if not self.safe(self.root, directory=True):
            return paths
        pending = [self.root]
        while pending and not self.stopped:
            directory = pending.pop()
            entries = []
            try:
                with os.scandir(directory) as scan:
                    for entry in scan:
                        self.entries += 1
                        if self.entries > self.limits.entries:
                            self.gap("directory-entry-limit", directory)
                            self.stopped = True
                            break
                        entries.append(entry)
            except OSError:
                self.gap("unreadable-directory", directory)
                continue
            if self.stopped:
                break
            directories = []
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                try:
                    if entry.is_symlink():
                        self.gap("symlink", path)
                    elif entry.is_dir(follow_symlinks=False):
                        directories.append(path)
                    elif not entry.is_file(follow_symlinks=False):
                        self.gap("non-regular-input", path)
                    elif path.suffix.lower() in (".yaml", ".yml"):
                        self.discovered += 1
                        if self.discovered > self.limits.yaml_files:
                            self.gap("yaml-count-limit", path)
                            self.stopped = True
                            break
                        paths.append(path)
                except OSError:
                    self.gap("unreadable-input", path)
            pending.extend(reversed(directories))
        return sorted(paths)


def _decode(snapshot, path):
    data = snapshot.capture(path)
    if data is None:
        return None
    try:
        raw = _decode_document(data)
        if raw is None:
            snapshot.gap("invalid-declaration", path)
        return raw
    except (DeclarationError, ValueError, RecursionError, TypeError):
        snapshot.gap("invalid-yaml", path)
        return None


def _leaf(raw):
    if isinstance(raw, dict) and isinstance(raw.get("steps"), list):
        if any(is_include(step) for step in raw["steps"]):
            raise DeclarationError("child must be a leaf")
    child = _load_document(copy.deepcopy(raw))
    if any("/" in step.id for step in child.steps):
        raise DeclarationError("child step ID contains slash")
    return child


def _parse_leaf(snapshot, path, raw):
    if raw is None:
        return None
    try:
        return _leaf(raw)
    except (DeclarationError, ValueError, TypeError, KeyError, RecursionError):
        snapshot.gap("invalid-child", path)
        return None


def _json_manifest(snapshot, parent, targets):
    sidecar = parent.with_suffix(".includes.json")
    data = snapshot.capture(sidecar)
    if data is None:
        return None
    try:
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
        if (not isinstance(manifest, dict) or set(manifest) != {"manifest_version", "scenarios"}
                or type(manifest["manifest_version"]) is not int or manifest["manifest_version"] != 1
                or not isinstance(manifest["scenarios"], dict)
                or set(manifest["scenarios"]) != targets):
            raise ValueError
        for entry in manifest["scenarios"].values():
            if (not isinstance(entry, dict) or set(entry) != {"path", "sha256"}
                    or not isinstance(entry["sha256"], str)
                    or not re.fullmatch("[0-9a-f]{64}", entry["sha256"])):
                raise ValueError
        return manifest["scenarios"]
    except (DeclarationError, ValueError, UnicodeError, TypeError, RecursionError):
        snapshot.gap("invalid-sidecar", sidecar)
        return None


def _dependencies(snapshot, parent, raw, target):
    """Resolve and capture once; selected pin validity is returned separately."""
    calls = [step for step in raw.get("steps", []) if is_include(step)] if isinstance(raw, dict) and isinstance(raw.get("steps"), list) else []
    if not calls:
        return {}, {}, True
    try:
        targets = set()
        for call in calls:
            if set(call["do"]) != {"include"}:
                raise ValueError
            sid = call["do"]["include"]
            if not isinstance(sid, str) or not sid.strip() or sid == raw.get("scenario"):
                raise ValueError
            targets.add(sid)
        if len(targets) > 64:
            raise ValueError
    except (ValueError, TypeError):
        snapshot.gap("invalid-include-targets", parent)
        return {}, {}, False
    entries = _json_manifest(snapshot, parent, targets)
    if entries is None:
        return {}, {}, False
    dependencies, selected, seen, usable = {}, {}, set(), True
    for sid, entry in sorted(entries.items()):
        try:
            path = _safe_file(parent.parent, entry["path"])
            path = Path(os.path.abspath(path))
            if path == parent or path in seen:
                raise DeclarationError("aliased dependency")
            seen.add(path)
        except (DeclarationError, OSError, ValueError, TypeError):
            snapshot.gap("unsafe-or-missing-dependency", parent)
            usable = False
            continue
        if path == target:
            selected[sid] = entry
        child_raw = _decode(snapshot, path)
        child = _parse_leaf(snapshot, path, child_raw)
        if child is None:
            usable = False
            continue
        if child.id != sid:
            snapshot.gap("dependency-id-mismatch", parent)
            usable = False
            continue
        data = snapshot.cache[path]
        if path != target and _sha(data) != entry["sha256"]:
            snapshot.gap("non-target-pin-mismatch", parent)
            usable = False
            continue
        dependencies[sid] = (child, entry["sha256"], entry["path"])
    return dependencies, selected, usable


def _values(step, index):
    """Only grammar-owned value positions, never parameter default objects."""
    prefix = f"/steps/{index}"
    if is_include(step) and isinstance(step.get("with"), dict):
        for key, value in sorted(step["with"].items()):
            yield prefix + "/with/" + _pointer(key), value
    if step.get("do") == "fill" and "value" in step:
        yield prefix + "/value", step["value"]
    request = step.get("do", {}).get("request") if isinstance(step.get("do"), dict) else None
    expect = step.get("expect", {})
    for label, req in (("do", request), ("expect", expect.get("request") if isinstance(expect, dict) else None)):
        if isinstance(req, dict):
            for key in ("path", "body"):
                if key in req:
                    yield prefix + f"/{label}/request/{key}", req[key]
    if isinstance(expect, dict):
        for point in ("ui", "response", "backend_state"):
            assertions = expect.get(point, [])
            if not isinstance(assertions, list):
                continue
            for i, assertion in enumerate(assertions):
                if not isinstance(assertion, dict):
                    continue
                for key in ("value", "id"):
                    if key in assertion:
                        yield prefix + f"/expect/{point}/{i}/{key}", assertion[key]
                if assertion.get("check") == "collection_matching_count" and isinstance(assertion.get("matching"), dict):
                    for key, value in sorted(assertion["matching"].items()):
                        yield prefix + f"/expect/{point}/{i}/matching/" + _pointer(key), value


def _references(value, location):
    if isinstance(value, dict):
        # Match the loader's priority and terminal recognition. Invalid nodes
        # are not promoted into valid references by searching inside them.
        if "from_parameter" in value:
            return
        if "from_step" in value or "response_field" in value:
            if set(value) == {"from_step", "result"} and all(isinstance(v, str) for v in value.values()):
                yield value["from_step"], value["result"], location
            return
        if set(value) & {"from_input", "from_bind"}:
            return
        for key, item in sorted(value.items()):
            yield from _references(item, location + "/" + _pointer(key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _references(item, location + "/" + str(i))


def _wiring(value, show_values):
    if isinstance(value, dict):
        if set(value) == {"from_parameter"} and isinstance(value["from_parameter"], str):
            return {"kind": "parameter-reference", "from_parameter": value["from_parameter"]}
        if set(value) in ({"from_step", "result"}, {"from_step", "response_field"}) and all(isinstance(v, str) for v in value.values()):
            return {"kind": "step-reference", **value}
        return {"kind": "object", "entries": {k: _wiring(v, show_values) for k, v in sorted(value.items())}}
    if isinstance(value, list):
        return {"kind": "array", "items": [_wiring(v, show_values) for v in value]}
    return {"kind": "literal", **_describe(value, show_values)}


def _validity(raw, dependencies):
    try:
        _load_document(copy.deepcopy(raw), dependencies=copy.deepcopy(dependencies) or None)
        return "valid"
    except (DeclarationError, ValueError, KeyError, TypeError, RecursionError):
        return "invalid"


def _parent_record(snapshot, parent, raw, selected, before_raw, after_raw, before_hash, after_hash, show_values):
    sites = []
    steps = raw.get("steps", [])
    for i, call in enumerate(steps):
        if not is_include(call) or call["do"]["include"] not in selected:
            continue
        entry = selected[call["do"]["include"]]
        overrides = call.get("with", {})
        overrides = overrides if isinstance(overrides, dict) else {}
        pin = entry["sha256"]
        match = "both" if pin == before_hash == after_hash else "before" if pin == before_hash else "after" if pin == after_hash else "neither"
        consumers = []
        for j, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            for location, value in _values(step, j):
                for source, name, at in _references(value, location):
                    if source == call.get("id"):
                        consumers.append({"step_id": step.get("id") if isinstance(step.get("id"), str) else None, "position": j + 1,
                                          "result": name, "location": at})
        defaults = {}
        for label, child_raw in (("before", before_raw), ("after", after_raw)):
            defaults[label] = {key: _describe(value, show_values)
                               for key, value in sorted(child_raw.get("parameters", {}).items())
                               if key not in overrides}
        sites.append({"step_id": call.get("id") if isinstance(call.get("id"), str) else None, "position": i + 1,
                      "target_path": entry["path"], "expected_pin": pin,
                      "actual_sha256": after_hash, "pin_match": match,
                      "with": {key: _wiring(value, show_values) for key, value in sorted(overrides.items())},
                      "defaults": defaults,
                      "consumers": sorted(consumers, key=lambda row: (row["position"], row["location"]))})
    return {"path": snapshot.label(parent), "scenario_id": raw.get("scenario") if isinstance(raw.get("scenario"), str) else None, "includes": sites,
            "validity": {"actual": "unknown", "hypothetical_before": "unknown", "hypothetical_after": "unknown"}}


def inspect_impact(before, after, parents, *, show_values=False, limits=None):
    """Return a deterministic review report. No file or process is modified."""
    limits = limits or Limits()
    root = Path(os.path.abspath(parents))
    old_path, new_path = Path(os.path.abspath(before)), Path(os.path.abspath(after))
    snapshot = _Snapshot(root, limits)
    report = {"report_version": 1, "status": "INCOMPLETE", "review_required": True,
              "scope": {}, "target": {"path": snapshot.label(new_path), "scenario_id": None,
              "before_sha256": None, "after_sha256": None, "bytes_changed": None, "structure_changed": None},
              "changes": [], "parents": [], "gaps": []}
    paths = snapshot.walk()
    old_raw, new_raw = _decode(snapshot, old_path), _decode(snapshot, new_path)
    old_child, new_child = _parse_leaf(snapshot, old_path, old_raw), _parse_leaf(snapshot, new_path, new_raw)
    if not new_path.is_relative_to(root):
        snapshot.gap("target-outside-root", new_path)
    for label, path in (("before", old_path), ("after", new_path)):
        if path in snapshot.cache:
            report["target"][label + "_sha256"] = _sha(snapshot.cache[path])
    if old_child is not None and new_child is not None and old_child.id != new_child.id:
        snapshot.gap("target-id-changed", new_path)
    comparable = (old_child is not None and new_child is not None and old_child.id == new_child.id
                  and new_path.is_relative_to(root))
    if comparable:
        old_hash, new_hash = report["target"]["before_sha256"], report["target"]["after_sha256"]
        report["target"].update(scenario_id=new_child.id, bytes_changed=old_hash != new_hash,
                                structure_changed=not _same(old_raw, new_raw))
        report["changes"] = _changes(old_raw, new_raw, show_values)
    for path in paths:
        raw = old_raw if path == old_path else new_raw if path == new_path else _decode(snapshot, path)
        if raw is None:
            continue
        dependencies, selected, usable = _dependencies(snapshot, path, raw, new_path)
        if not selected or not comparable:
            if usable and _validity(raw, dependencies) != "valid":
                snapshot.gap("invalid-declaration", path)
            continue
        item = _parent_record(snapshot, path, raw, selected, old_raw, new_raw, old_hash, new_hash, show_values)
        report["parents"].append(item)
        pins = {site["pin_match"] for site in item["includes"]}
        if "neither" in pins:
            snapshot.gap("selected-pin-unknown", path)
        if usable:
            old_deps, new_deps = copy.deepcopy(dependencies), copy.deepcopy(dependencies)
            for sid, entry in selected.items():
                old_deps[sid] = (old_child, old_hash, entry["path"])
                new_deps[sid] = (new_child, new_hash, entry["path"])
            previous = _validity(raw, old_deps)
            following = _validity(raw, new_deps)
            item["validity"].update(hypothetical_before=previous, hypothetical_after=following,
                                    actual=following if pins <= {"after", "both"} else "invalid")
            if previous != "valid":
                snapshot.gap("invalid-before-parent", path)
        elif pins - {"after", "both"}:
            item["validity"]["actual"] = "invalid"
    report["parents"].sort(key=lambda row: row["path"])
    report["gaps"] = sorted(snapshot.gaps, key=lambda row: (row["location"], row["code"]))
    report["scope"] = {"root": str(root), "directory_entries_inspected": snapshot.entries,
                       "yaml_files_discovered": snapshot.discovered,
                       "files_captured": len(snapshot.cache), "bytes_captured": snapshot.bytes,
                       "limits": asdict(limits),
                       "inputs": [{"path": snapshot.label(path), "sha256": _sha(data)}
                                  for path, data in sorted(snapshot.cache.items(), key=lambda item: snapshot.label(item[0]))]}
    report["status"] = "INCOMPLETE" if report["gaps"] else "COMPLETE"
    report["review_required"] = bool(report["gaps"] or report["target"]["bytes_changed"] or
                                      any(row["validity"]["actual"] != "valid" for row in report["parents"]))
    return report


def exit_code(report):
    return 2 if report["status"] == "INCOMPLETE" else 1 if report["review_required"] else 0


def render_text(report, *, show_values=False):
    """A compact index into the full source; JSON retains every structured fact."""
    lines = [f"{report['status']} review_required={str(report['review_required']).lower()}",
             f"Scope: {report['scope']['root']}",
             f"Target: {report['target']['path']} bytes_changed={report['target']['bytes_changed']} "
             f"structure_changed={report['target']['structure_changed']}"]
    for change in report["changes"]:
        suffix = json.dumps({"before": change["before"], "after": change["after"]}, sort_keys=True, ensure_ascii=False)
        lines.append(f"Change {change['kind']}: {change['location']} {suffix}")
    for parent in report["parents"]:
        lines.append(f"Parent {parent['path']} ({parent['scenario_id']}): " +
                     ", ".join(f"{key}={value}" for key, value in parent["validity"].items()))
        for site in parent["includes"]:
            lines.append(f"  Include {site['step_id']} at step {site['position']}: pin={site['pin_match']} "
                         f"target={site['target_path']}")
            lines.append("    Wiring " + json.dumps({"with": site["with"], "defaults": site["defaults"]}, sort_keys=True, ensure_ascii=False))
            for consumer in site["consumers"]:
                lines.append(f"    Uses result {consumer['result']} at {consumer['location']} ({consumer['step_id']})")
    for gap in report["gaps"]:
        lines.append(f"Gap {gap['code']}: {gap['location']}")
    lines.extend(["Hypothetical checks use CURRENT parents and other dependencies, not historical replay.",
                  "Authored values are shown at source confidentiality." if show_values else
                  "Literal values are hidden; consult source or --show-values for full review.",
                  "Identifiers and paths may be confidential. No runtime values are read.",
                  "Inspection is not approval, business PASS, permission to update pins, or a search outside this scope."])
    return "\n".join(lines)
