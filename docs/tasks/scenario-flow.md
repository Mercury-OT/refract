# Ordered Scenario Flow and shared parameters

Status: specification and expression approved by the maintainer on 2026-11-01;
implementation, two independent audits and architect acceptance passed. See the
[verification record](scenario-flow-acceptance.md). Submission, PR, green-check
merge and cleanup are authorized; hosted delivery is recorded separately.

## Purpose and boundaries

A Flow is an ordered, end-to-end business execution made of independently named
Scenarios. It retains the user's current session and application context between
Scenarios and exposes Flow / Scenario / projection / step evidence. It is not a
catalogue of unrelated runner calls. Shared data is explicitly read and written;
system-state dependencies need not have a data reference.

This implements the maintainer-approved four-document create/update/read pattern.
The runnable public consumer uses document content in place of a record name so
the existing synthetic Documents target and adapter remain unchanged. This changes
only the neutral example's business field, not the approved Flow expression,
read/write rules, observed-identity binding or independent expected-value source.
It does not claim measured review savings or complete business correctness. No
private source, private product, external corpus or private evidence informs the
public examples. All new public material is neutral synthetic material.

Format remains `schema_version: 1`. Existing standalone Scenario behavior and
one-level include remain supported. No Flow nesting, branches, joins, concurrency,
automatic retry, cleanup action, UI editor, new assertion vocabulary or object
absence assertion is introduced. No product changes, workroom access or writes.

R1 review: shared values are copied, not transformed. The existing prohibition on
expressions, conditional declarations, loops, templates and JSONPath remains.
The approved execution-error policy is metadata, not a data-dependent branch.
Run-relative time and bounded string composition retain their existing limits.

## Approved expression

A Flow document has exactly `schema_version`, `flow`, optional `description`,
`users`, optional `on_failure`, optional `parameters`, and `scenarios`.
`on_failure` is `stop` by default, or the explicit literal `continue`.
`scenarios` is a nonempty ordered list of invocations, each with a unique `id`,
literal `scenario` identifier and complete `with_users` mapping when participants
exist. User identities and anonymous restrictions follow existing include rules.
Ordinary Scenario users still select their own steps; mapping cannot collapse two
participants to one account or silently turn anonymous into authenticated work.

Flow `parameters` maps names to declaration objects. `{}` means declared but
unset; `{initial: value}` supplies finite JSON-like initial data. In particular,
`{initial: null}` and `{initial: {}}` are actual values, not unset. There are no
mandatory parameter type declarations, implicit values, undeclared writes or
generator/expression extensions to this initial-data position.

Scenario value positions can use the exact reference `{from_flow: name}`.
It is distinct from `from_parameter`; authored literal data and observed data are
never reparsed into references. Existing local parameters keep their semantics.
The top-level optional `write_flow` maps declared Flow names to copied sources:
`from_step` with `response_field`, `from_step` with a named included `result`,
`from_flow`, or `from_parameter`. No transformation or inline concat is added
to this write position. Source shape, ordering and visibility are validated.

Only a directly scheduled Scenario owns `write_flow`. An included child declaring
it is rejected, not ignored. Included children may read the containing Scenario's
snapshot and return existing named results; the scheduled caller publishes them.
The existing no-re-export restriction on Scenario `results` is unchanged.

Loading a standalone Scenario which depends on Flow reads or writes fails before
adapter calls. Ordinary standalone Scenarios remain executable. A Flow may include
an otherwise standalone Scenario without introducing an implicit Flow dependency.

## Dependency identity and preflight

Use a local `<flow-stem>.scenarios.json` sidecar with manifest version 1 and exact
Scenario ID targets. Every entry pins its relative local path and raw SHA-256.
If a scheduled Scenario contains includes, its include-sidecar SHA-256 must also
be pinned by the Flow entry; unchanged parent bytes cannot authorize a changed
transitive dependency. Existing include sidecars pin their child bytes.

Reuse existing protections against duplicate keys, symlinks, traversal, aliasing,
unknown fields and mismatched IDs/hashes. Limit to 64 distinct scheduled source
files, 100 invocations and 10000 expanded leaves (existing per-Scenario include
limits still apply). A Flow cannot be a scheduled Scenario or an included child.
The complete declaration, dependency closure, mappings and reference shapes are
validated before actions. Each selected projection preflights the complete plan
for unsupported capabilities before its actions. Hash identity is not approval.

`refracto validate-flow PATH [--expand]` inspects this declaration without running
the target or generating runtime values. Expansion retains invocation boundaries,
source identities and symbolic read/write declarations, not runtime secrets.

## Runtime and shared parameter semantics

The public `run_flow` entry executes an ordered plan using the existing projection
action engines. It must not simulate continuity by separately opening and closing
independent Scenario runs. Namespaced step identities distinguish repeated calls
and included leaves. Adapter action ports still receive only mechanical action
inputs and identity, never assertions or the Flow parameter store.

Every live projection owns an independent parameter store and session manager.
At Scenario entry take a deep snapshot; all `from_flow` reads in that invocation
use it. Available values undergo the existing destination's strict type checks.
Missing/unavailable references cannot be defaulted or converted. Unrelated
steps can follow existing local dependency-blocking rules. Record value-free
read/write version and source provenance; sensitive actual values are hidden
from default representations and are not automatically printed by CLI/reporting.

At Scenario completion require strict `PASSED` and no incomplete obligations.
Resolve every declared write source before atomically publishing the whole set.
A missing/invalid write source is a visible boundary error, never a successful
Scenario with a silently missing output. Write sources cannot borrow another
Scenario's internal response or another run/projection's value.

Any unsuccessful invocation invalidates all parameters it declared to write.
They become unavailable to later readers; a prior value remains diagnostic history
only. Parameters outside that write set are untouched. This prevents `continue`
from treating an obsolete value as a successful update. Explicit successful writes
may overwrite an existing parameter; no extra overwrite flag is introduced.
Neither publication nor invalidation rolls back actions in the tested system.

Scenario-local run-unique sources remain independent per invocation and live
projection. One Flow logical run freezes one UTC base for existing Scenario time
parameters. Fixed `run_time` remains reproducible. Contract consumes backend's
frozen values, per-node snapshots, provider records and execution provenance; it
does not authenticate, generate fresh values or reuse the final store for earlier
nodes. No live projection borrows evidence from another live projection.

## Users, sessions and continuation

Flow participants map explicitly to each scheduled Scenario's local names.
Within one projection, all invocations retain the same mapped user's current
session and browser context. Switching users preserves the others. Anonymous
remains separate; `session: new` replaces only its named user's session/context.
No reauthentication on 401/403 and no automatic focus/context repair. Every
retained UI context closes once on final exit, including failures.

Existing continuation rules apply within each Scenario: ordinary FAILED continues,
explicit leaf stop/ERROR/SKIPPED stops its remaining leaves, unavailable data blocks
consumers. Include nodes cannot override a child's stopping policy.

Between Scenarios, `stop` blocks remaining invocations after any non-PASSED result.
`continue` attempts the next invocation with usable data/session/context; it does
not erase failure, override missing dependencies, repair unusable contexts or
guarantee cleanup. The policy applies per projection execution chain; the overall
Flow remains non-PASSED if any selected required chain is non-PASSED.

## Reporting and threat boundary

Expose Flow -> Scenario invocation -> projection -> original leaf/check results.
Keep invocation ID distinct from reusable Scenario ID. Retain exact source pins,
effective user, session generation, preceding failures, blocked reasons, parameter
read/write provenance and synthetic publication errors. No new public status
vocabulary; strict success still means `status == "PASSED"`.

Context-close and recorder errors remain visible in the final outcome and cannot
be hidden by a previously successful publication. An unsuccessful Flow does not
claim that its earlier physical effects were undone. A shared session is not proof
that every implicit application-state prerequisite holds.

Protect against accidental aliasing, stale evidence, incorrect mappings and
unavailable data. This does not sandbox hostile in-process adapter code, prove
external system honesty or make contract an independent observation source.
Approved expected names come from declared input, not the same observed value
they are meant to judge. A bad mapping or jointly weakened inputs/expectations
still requires review and negative controls.

## Acceptance matrix

- Complete four-document create/update/read example: real request IDs, mapped user,
  intended-content overwrite only after verified update, same session across nodes.
- Flow and standalone loader positive/negative cases; all reserved references,
  keys/types, null/unset/false/zero/empty preservation, duplicate and missing pins,
  tampered direct/transitive bytes, invalid user mappings and over-depth includes.
- Reads frozen at node entry; literal marker-looking objects remain data; actual
  responses are not mutated or reread from another projection.
- Failed/missing-source multi-write is atomic; old destination values are unusable;
  independent later work can run under continue; failed results remain visible.
- Missing Flow context rejects standalone execution before any adapter call.
- Normal FAILED, explicit stop, ERROR, SKIPPED, BLOCKED, EMPTY and degradation at
  Scenario boundaries cannot become a successful Flow; no synthetic green checks.
- Repeated Scenario invocation, one-level include named output publication and
  child write rejection; stable invocation provenance and source pins.
- Multiple mapped named users and anonymous; distinct principals; session:new;
  no login/context on blocked work and exactly-once context closure.
- Real Chromium frontend/e2e continuity across nodes; stale permit/evidence cannot
  substitute for a new action; no new adapter expectation access.
- Backend/contract replay uses each invocation's actual snapshot and recordings;
  later overwrites and different live-projection IDs cannot change earlier checks.
- One Flow time base/fixed replay and distinct per-invocation/projection unique
  values preserve existing bounded semantics.
- Default repr/CLI errors do not expose credentials, bodies or shared values.
- Maintained public docs/examples in English; independent audit, focused tests,
  full suite, core-only, litmus, hygiene, lock and diff checks pass. Assertion
  vocabulary and private/local boundaries unchanged.

## Delivery

Specification, declaration/runtime code, focused negative tests, a neutral runnable
example with pinned dependencies, user documentation and acceptance evidence.
No performance or review-cost improvement is claimed without measurements.
After architect acceptance submit only accepted files on a dedicated branch,
wait for required PR checks, merge, verify main CI, then clean up both branches.
