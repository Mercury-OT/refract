# Mattermost API adoption and cost pilot

Status: the maintainer approved six API declarations in three review batches,
then authorized implementation and the independent audit and architect acceptance
gates on 2026-11-16.
Starting main is `e768488`. After acceptance, the maintainer separately authorized
task-branch submission and merge on 2026-11-17, subject to green hosted checks.
The reviewed original
declarations and local execution evidence stay outside this repository; the
runner accepts their directory explicitly and verifies their frozen hashes.

## Question and boundaries

Exercise the existing framework against a real, isolated public open-source
application. Measure setup, adapter, authoring, review, diagnosis, repeated-run
and version-change work separately. Six green declarations, if obtained, are
not proof of general adoption value, security, or production readiness.

Use unmodified Mattermost Team Edition 11.7.15 and 11.11.4, pinned to their
reviewed source and image digests. Record the actual database image, platform,
configuration and response version. These releases may have identical behavior
on the chosen APIs: no-change maintenance is a valid but limited observation.
Use dedicated disposable resources and loopback-only publication. Bootstrap
the administrator first, then two distinct ordinary accounts. Account creation
and environment policy are host setup; all teams, channels and posts are
created by the visible Scenario steps. No existing application is touched.

Keep format 1, one-level inclusion, core, browser support, production target,
dependencies, CI and existing declarations unchanged. No download work, new
assertion, UI action, alternate browser evidence collector or private workspace
access is permitted. Any newly found core gap is reported, not repaired here.

## Approved panel

| ID | Obligation |
| --- | --- |
| S1 | Create/read/rename/read a private channel, preserving identity and team. |
| S2 | Create/read a message with correct identity, author, channel and content. |
| S3 | Edit an own message, then independently read changed content and retained identity. |
| S4 | A logged-in same-team nonmember cannot post; a member control succeeds; the observed message page remains unchanged. |
| S5 | One retained peer session sees channel-read access denied, granted and revoked; login remains valid and the owner retains access. |
| S6 | An existing own message is deleted; ordinary ID read returns the exact not-found response and the bounded page returns to its pre-creation snapshot. |

The shared, already reviewed setup creates an invitation-only team and ordinary
private channel. Preserve the seven reviewed YAML files byte-for-byte, including
the shared file and its pins. Never substitute a rewritten or weaker declaration
to obtain a pass. The code accepts external inputs so the approved review text
does not become a second public authoring format.

Use backend plus contract only. Contract consumes the backend recordings and
normalizer, so it is a different check, not independent evidence or a second
write execution. No database probe is implied. S4 and S6 inspect one actual
normal page, not all storage; system messages and all observed fields remain.

## Adapter contract

The resolver prefixes logical paths with `/api/v4`, preserving declared method,
query, headers and body. The driver sends actual HTTP and retains actual status,
request and response observations. It does not follow redirects with credentials,
retry writes, infer success from expected values, or silently log in again.
The authenticator maps owner/peer to distinct ordinary principals, with one
session per requested generation. Credentials are external and never public.

Normalization retains complete actual JSON object fields and types. Validate
PostList structure: order entries identify actual posts, map keys agree with
post IDs, and malformed data is not replaced by empty objects/lists. Preserve
extra map entries, including parents outside order. Do not require a universal
map/order bijection. No assertion data reaches these ports.

## Experiments and acceptance

1. Validate every frozen declaration and pin; record code/input/environment
   hashes before running. Freeze the environment account/permission policy.
2. Run all six API scenarios three times on each pinned version, retaining every
   attempt, failure, request/response, strict top-level status and per-step result.
   Each run owns fresh Scenario-created resources. Do not retry-hide failures.
3. Use at most two concentrated wiring repair rounds per Scenario. If an approved
   obligation cannot be met, retain the blocker and stop expanding that slice.
4. Compare S2 and S4 with ordinary pytest plus HTTP, using the same inputs,
   observation channels and assertion obligations. Keep framework checks separate
   from product checks. Do not credit additional observations to the framework.
5. Test mapping against explicit neutral samples; also inject a bounded set of
   labeled changes into copies of actual observed responses. Retain the reached
   injection and failing check. These are artificial controls, not product bugs
   or a product-quality percentage.
6. Bound the UI compatibility gate to two hours of active investigation. Use the
   unchanged browser helper against the normal application. If a required path
   uses unsupported transport or cannot supply reliable evidence, mark S7/S8
   blocked/not executed with the observed reason; do not disable target features
   or substitute API actions for UI execution. No unapproved UI Scenario runs.
7. Record version-comparison changes, unchanged inputs, adapter edits and
   verification effort. Both target versions and their raw outcomes remain
   identifiable. Separate environment installation failures from product results.

Costs include timestamped activity/wait intervals, source lines by responsibility,
actual command duration, repeated-run status, diagnosis causes and repair rounds.
Human active review time and unavailable AI token usage remain explicitly unknown,
not inferred from elapsed chat time. Record approval rounds and changed assertions
without claiming those counts measure cognitive effort. Report ordinary-test
comparison as descriptive evidence, not an unbiased controlled human study.

## Deliverables and gates

- A small example adapter, frozen-input runner and reproducible environment entry.
- Offline mapping/transport/control tests and ordinary-HTTP comparison cases.
- Local-only immutable raw run artifacts and a credential-free public summary.
- Cost and failure accounting, all eight case dispositions, version comparison,
  independent audit, and a five-line maintainer summary.

Stop when the finite panel has an evidenced disposition, tests/checks pass and
independent findings are resolved. Full API success is not required to accept
honest blocker delivery. Run focused tests, core litmus, lock and hygiene checks;
broaden validation for new failures or unresolved concerns. Verify no core or
existing adapter changes and no staging/submission. Public information sources
are the approved panel, public Mattermost source and this isolated synthetic-data
execution only; raw credentials, local paths and unrelated environment details
must not enter public artifacts.
