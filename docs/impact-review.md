# Review a shared Scenario change

`refracto impact` compares an explicitly selected old child file with its current
version and finds current parents that include that exact file. It does not run
tests, change files, update fingerprints, or approve a change. The current
one-level include rules bind child-local participants through the caller's
explicit `with_users` map, or the retained single-user shorthand. Multi-user
children require complete mappings; an anonymous participant cannot be upgraded
to a named account, and distinct child participants cannot collapse to one target.

```sh
refracto impact --before old-child.yaml --after scenarios/shared/child.yaml --parents scenarios
refracto impact --before old-child.yaml --after scenarios/shared/child.yaml --parents scenarios --json
```

The old snapshot is supplied explicitly; the command does not search Git history.
The current child must be inside the selected parent directory. Both snapshots
must be valid leaf Scenarios with the same Scenario ID. Another file with that
same ID is not considered a caller of this file. The scan includes `.yaml` and
`.yml` files recursively, without consulting Git ignore rules. Select a Scenario
directory rather than an arbitrary repository containing other YAML formats.

## What to review

The report separates four questions:

1. **What changed in the child?** All authored fields are compared, including
   parameter defaults, users/session policies, actions, assertions, result names
   and result sources.
   An assertion removal is a fact to review, not an automatic judgment that the
   new requirement is wrong. No rename or semantic-equivalence inference occurs.
2. **Which parents use it?** Each include site lists its step, supplied arguments,
   defaults used in each child version, and downstream named-result consumers.
   User binding also shows the complete caller mapping, effective parent users,
   child-local users in both versions, and the child's explicit new-session
   policies. Anonymous selection remains explicit in this review view. An unchanged pin is
   not approval of the caller's account choice or session effects.
   Only executable reference positions count; reference-shaped literal parameter
   objects remain data.
3. **Does the recorded fingerprint match?** The pin is classified as matching
   before, after, both or neither. Comments and formatting change the byte hash
   even when the parsed declarations are structurally equal. No pin is refreshed.
4. **Can the current caller load with each child?** These are explicitly
   hypothetical checks: **current parent + current other dependencies + selected
   old/new child**. They are not a reconstruction of the historical project.
   Parent-versus-parent changes are not compared here.

For example, removing a result that the current parent consumes produces a
known before-valid/after-invalid impact. An old pin still makes the actual
declaration invalid even when both hypothetical loads succeed. An invalid old
caller or an unknown pin does not establish compatibility and makes inspection
incomplete. Other dependencies must still match their real current pins.

## Output and exit status

| Exit | Report | Meaning |
| --- | --- | --- |
| 0 | `COMPLETE`, `review_required=false` | The selected child is byte-identical and inspected declarations and pins are valid. |
| 1 | `COMPLETE`, `review_required=true` | A child change or a known caller/pin impact requires attention. |
| 2 | `INCOMPLETE`, `review_required=true` | Some required evidence could not be inspected reliably. |

These statuses are not approval, business acceptance, permission to update pins,
or proof that there are no callers outside the selected directory. No output
measures reviewer effort or establishes that reuse reduces it.

Text output provides a concise index of changes and callers. JSON has
`report_version: 1` and stable `scope`, `target`, `changes`, `parents`, and `gaps`
sections. Scope records actual inspection counts, limits, and captured file
hashes. Parent validity is `valid`, `invalid`, or `unknown` separately for the
actual declaration and the two hypothetical checks. Gaps use safe diagnostic
codes instead of raw parser messages.

Differences are strict about types: `false` is not `0`, `true` is not `1`, and an
integer is not a floating-point value. Missing values differ from null. Mapping
order is ignored, while array order is retained. Steps with the same ID are
paired and the step order is reported separately. Child review locations use
`/steps/by-id/<escaped-id>/...`; this is a stable review address, not a YAML
array index. Consumer locations such as `/steps/2/do/request/path/1` use the
actual zero-based authored position. Pointer components escape `~` as `~0` and
`/` as `~1`. No timestamps or random identifiers enter the report.

## Confidentiality

Literal values are hidden by default, including parameter defaults, request
payloads and assertion values. Add `--show-values` only when a full authored-data
view is appropriate; this has the same confidentiality as the source files.
Identifiers, field names and paths remain visible even without that flag and
may themselves be confidential. This is not a general redaction system. Parser
errors never echo source lines. No runtime response or binding values are read.
Do not publish a report merely because its literal values are hidden.

## Bounded, read-only inspection

Each input path is captured once, and hashing, parsing, comparisons and validation
reuse the same bytes. This is not an atomic filesystem snapshot or a defense
against a malicious concurrent writer. Inputs are never rewritten; there is no
temporary Scenario, subprocess, network call, adapter, or execution. Output is
stdout only; shell redirection, if used, is a separate user action.

Limits are inclusive: 4,096 directory entries, 512 discovered YAML files,
1,024 captured files, 2 MiB per file and 32 MiB total captured bytes. Explicit
snapshots and sidecars count toward file and byte limits. Symlinks are not
followed. Missing, unsafe, unreadable, malformed or over-limit evidence produces
an inspection gap rather than a silently truncated success. Duplicate keys,
aliases and unsafe YAML tags are rejected by the existing declaration decoder.

The runtime loader still independently enforces its ordinary declaration and
fingerprint rules. A review report is not an executable substitute for that gate.
