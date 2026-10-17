# Shared Scenario change-impact review

## Authorization and purpose

The maintainer authorized this bounded follow-up on 2026-10-16 after authorizing
submission of the preceding reuse walkthrough. Development starts only after
that submission, main CI, and branch cleanup finish. This task authorizes
specification, development, independent audit, and local architect acceptance;
it does not authorize its own staging, commit, push, PR, or merge.

Provide a read-only answer to: what changed in this child, which inspected
parents refer to this exact file, and what caller decisions need attention?
This is review assistance, not human approval, semantic equivalence, business
correctness, historical execution replay, or measured cognitive-cost reduction.
Use public syntax and independently constructed synthetic fixtures only. Do not
access private products or workspaces. Keep public material in English.

## 1. Fixed scope and interface

Add the offline command:

```sh
refracto impact --before old-child.yaml --after scenarios/shared/child.yaml --parents scenarios
```

`--before` is an explicitly selected old child snapshot. `--after` is the actual
current child file within the explicitly selected `--parents` directory. Both
must be regular, independently valid, leaf Scenario files with the same Scenario
ID; neither may contain an include. A renamed Scenario ID is an unsupported
comparison, not a guessed match. Before and after may be the same file.

Do not search Git history, other directories, the network, or an implicit global
registry. Target callers by resolved dependency file identity, not merely by
Scenario ID or equal content. A different file with the same ID is not a caller
of the selected file. Show the inspected scope and make no claim about callers
outside it. Existing one-level, same-actor and exact-pin rules remain unchanged.

Default output is concise English text. `--json` emits the deterministic
versioned report. `--show-values` explicitly opts into authored literal values;
the help and guide must warn that these have source-level confidentiality.
Default output hides literal values and never echoes raw parser exceptions.
Identifiers, field names and paths remain visible for locating changes and may
also be confidential; this is not a general secret-redaction system. No mode
contains runtime response/binding values or executes a Scenario.

## 2. Read-only bounded snapshot

Enumerate `.yaml` and `.yml` files recursively and deterministically under the
selected root, without silently consulting Git ignore rules. This is a Scenario
directory: unrelated malformed YAML is a visible inspection gap, not skipped.
Do not follow symlinks. A discovered symlink, unreadable entry, non-regular input,
missing file, unsafe dependency, decoding error, or limit causes an explicit
gap and INCOMPLETE result. Never convert incomplete discovery to no impact.

Limits are inclusive: 4096 inspected directory entries, 512 discovered YAML
files, 1024 distinct captured files including snapshots and sidecars, 2 MiB per
file, and 32 MiB total captured bytes. Above-limit input is not truncated into
a successful report. Tests may inject lower limits to prove boundaries cheaply.
Check file size/read limits before decoding. Existing strict YAML parsing must
reject aliases, duplicate keys, unsafe tags, and non-string mapping keys.

Read each resolved input file once into a bounded cache. Hashing, parsing,
comparison and validation reuse its captured bytes. Dependency references share
that cache. Record actual inspected counts and input hashes; do not invent a
complete count after traversal stops. This is a captured inspection, not an
atomic filesystem snapshot or defense against a malicious concurrent writer.

No directory creation, temporary rewritten Scenario, pin update, output file,
Git operation, subprocess, adapter, browser, authentication, or request is part
of the analyzer. Output goes to stdout; ordinary user redirection is external.

## 3. Child changes: structural facts only

Report before/after byte SHA-256 and separate `bytes_changed` and
`structure_changed`. Comments/format-only changes still change the exact pin
and require review even when parsed structure is equal.

Use strict recursive type-aware comparison: false/0, true/1, integer/float, null
and absence are distinct. Mapping key order is not a structural change; list
order is preserved. Compare all authored fields, including metadata, parameter
defaults, results, actions, polls and assertions. Pair steps by unchanged step
ID and report step order separately; additions/removals are not inferred renames.
Within steps, arrays such as assertions are compared positionally. Emit stable
locations, kind (added/removed/changed/order-changed) and typed before/after
descriptors. With explicit value opt-in, descriptors also contain the actual
authored value. Default descriptors contain no literal values.

Deleting an assertion is a reported removal, not an automatically incorrect or
weaker requirement. A renamed internal step is not automatically harmless.
No risk score, broad equivalence proof, or inferred approval status is produced.

## 4. Caller inspection and hypothetical validation

For each selected-file include, report parent path/ID, include step ID and
position, declared target path, expected sidecar pin, actual captured hash,
whether the pin matches before/after/both/neither, provided `with` expressions,
and which child defaults are used under each snapshot. Report named-result
consumers with result name, consumer step ID and exact authored location.

Find references only at existing executable value locations: include `with`,
fill value, request path/body (under do or expect), assertion value/id and
collection matching values. Respect existing reference recognition and do not
re-parse a literal parameter default as syntax. Descriptions, parameter objects,
result declarations and unrelated keys must not manufacture result consumers.

Reuse the strict declaration decoder and `_load_document` with captured
dependency tuples. Do not loosen or monkeypatch runtime `load_scenario` or its
pin enforcement. Validate sidecars with the existing exact target-set, unique
key, field/type, contained relative path, no-symlink, distinct-file and limit
rules. Other dependencies must be valid and match their actual pins.

For the selected dependency only, construct independent in-memory validation
inputs using the old and new parsed child. Label these results hypothetical:
they use the CURRENT parent and CURRENT other dependencies, not historical
versions of the whole project. The actual selected pin is checked separately
and never silently rewritten. Use independent copies so one validation cannot
mutate the other's inputs.

Report actual declaration validity plus hypothetical before/after validity as
valid/invalid/unknown. Before-valid/after-invalid (for example a consumed result
removed or an actor changed) is a COMPLETE, known impact. The parent remains
non-executable when its actual pin is stale, even if both hypothetical loads
succeed. Selected pins matching neither supplied snapshot, invalid prior parent,
missing/unsafe/mismatched other dependencies, and unreadable/invalid unselected
declarations cause inspection gaps. Do not call those situations compatible.
Keep observed caller locations where safe, explicitly alongside the gaps.

## 5. Report, status and exit rules

The JSON object has `report_version: 1` and the following stable sections:

- `status`: COMPLETE or INCOMPLETE; `review_required`: boolean.
- `scope`: selected root, inspected/discovered counts, limits and captured file
  paths/hashes. Paths inside the root are relative; explicitly supplied snapshots
  are identified without reading beyond the selected inputs.
- `target`: selected path, Scenario ID, before/after hashes, byte/structure flags.
- `changes`: ordered structural-change records with location/kind/descriptors.
- `parents`: ordered caller records, include sites, parameter/default wiring,
  result consumers, pin states and actual/hypothetical validity.
- `gaps`: ordered safe diagnostic codes and affected locations, no raw exception
  strings or literal data. Invalid initial inputs still produce this report with
  unavailable fields explicitly null/empty, never a fabricated clean result.

Sort parents by relative path, include sites by authored order, consumers by
step order/location, mapping keys lexically, and differences by stable location.
No timestamp, random ID or nondeterministic traversal order enters the report.
Use strict report contract tests rather than adding an approval schema/platform.

Exit 0: COMPLETE, byte-identical target, valid inspected declarations/pins and
no review-triggering discrepancy. Exit 1: COMPLETE with changes or known
review-required impact (including a stale selected pin). Exit 2: INCOMPLETE.
Gaps always imply `review_required=true`. A successful inspection is never a
business PASS, approval, permission to update a pin, or proof of no external
callers. The text output states these boundaries and directs readers to full
source when values are hidden.

## 6. Mandatory verification

1. Multiple parents and multiple include sites of one child are all found;
   same-ID different files are not falsely attributed.
2. Missing/changed/defaulted parameters, added/removed result names, internal
   step changes, action/expect/poll changes and step/assertion order are visible.
3. Removed consumed result yields before-valid/after-invalid, COMPLETE exit 1;
   stale actual pin never becomes actual valid. The real loader still rejects it.
4. Comment-only changes require review; mapping-order-only change remains a byte
   change; strict false/0 and true/1 differences are detected.
5. Literal reference-shaped parameter objects do not become result consumers;
   real references in all supported value positions, including another include's
   arguments, are captured with correct call identity.
6. Missing baseline/root/target/sidecar, mismatched IDs, invalid prior parent,
   wrong or extra sidecar fields, unknown pins, unrelated invalid YAML, duplicate
   keys, unsafe tags and aliases produce safe gaps and exit 2, not clean output.
7. Traversal/symlink/missing dependency and all configured resource limits have
   passing-at-boundary and failing-above-boundary tests; use tiny injected limits.
8. Non-target dependency drift is INCOMPLETE; selected dependency changes are
   inspectable without changing the files or runtime pin rules.
9. Default text/JSON and error paths hide sensitive literal sentinels; explicit
   show-values reveals only authored data with a confidentiality notice.
10. Repeated identical invocation has identical output, each captured path is
    read once, and input tree bytes/paths are unchanged. No runtime or network
    calls are made. Existing validate/expand behavior remains unchanged.
11. CLI exit/status contract, both formats, argument errors, no-caller scope,
    malformed structures and hypothetical unknown states are tested directly.
12. Independent audit uses counterexamples beyond developer fixtures. Run focused
    tests, full regression with real Demo tests, core litmus, lock, hygiene and
    diff/index checks. Inspect public sources/new files as well as tracked diff.

## 7. Deliverables and stop boundary

Add `refracto/declaration/impact.py` (small private helpers may be split if needed),
minimal `refracto/cli.py` integration, focused offline tests, and
`docs/impact-review.md`. Add a short link in SCENARIO.md's review section without
changing any YAML rule. Architect owns this specification, roadmap status and
the appended/new local acceptance record after independent audit.

No model, vocabulary, loader semantics, runtime projection, adapter, product,
existing Scenario, dependency/lock, CI, MANIFESTO, BRAND, editor or historical
acceptance changes. No new nested composition or approval files. If correct
inspection requires changing expression/execution semantics, stop for maintainer
confirmation rather than widening scope. Human time savings remain unmeasured;
usefulness must be assessed in later real review, not inferred from test count.
