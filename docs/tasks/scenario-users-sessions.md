# Scenario users, sessions, and one-level inclusion

Status: specification approved for implementation by the maintainer on 2026-10-17.
Submission is not authorized. Starting main: `95ba66d`.
Public, synthetic consumers only; no private repository access or changes.

Implementation and verification evidence: [local acceptance](scenario-users-sessions-acceptance.md).
Current delivery status is indexed in the public roadmap; acceptance is not submission.

## Purpose and non-claims

Execute declared actions as fixed logical users, retain each user's current
session, and explicitly authenticate the same account again. Observe owner/peer
access and the effects of a declared permission change. Names do not prove roles,
HTTP denial does not identify an authorization decision point, and mock evidence
does not establish live permissions. No automatic account creation, grants,
recovery, session refresh, login-page workflow, cleanup, or adoption claims.

## Approved declaration

Keep `schema_version: 1` and the existing actions, expectations, references,
parameters, named results, failure policy, and one-level inclusion.

- Top-level `users` is required: a list of distinct nonblank literal names.
  `users: []` means no account binding/authentication, not a proof of anonymity.
  Null, strings, mappings, duplicate names, dynamic values, and `actor` are errors.
- With no users, a step must omit `user` and `session`.
- With exactly one user, omission selects that user; an explicit `user` must
  equal it. With multiple users every step must name a declared user, including
  waits and include nodes. User selection is never a runtime expression.
- An ordinary leaf may say `session: new`. Omission reuses its user's session,
  acquiring one on first use. No other explicit session policy is accepted.
  Dependency-blocked or globally blocked leaves do not authenticate or replace
  sessions. A fresh session replaces only this user's current session.
- Include nodes accept `user` under the same cardinality rules, but no session
  override. A child with one user maps that local name to the effective parent
  include user; no `with_users` or duplicate mapping field. A child with zero
  users may only be included by an anonymous parent. All other combinations,
  including a child with multiple users, fail before side effects.
- Child leaves are independently validated before binding. Their assertions,
  failure policy and explicit `session: new` survive expansion. Mapping does
  not edit the child bytes. Public named results and exact sidecar pins remain.
  Source/expanded review output shows local and effective user names.

Illustrative identity fields (not a standalone Scenario):

```yaml
users: [creator, peer]
steps:
  - id: setup
    user: creator
    do: {include: shared.create_record}
    with: {record_name: owner-record}
```

The old YAML `actor` form is rejected rather than silently converted. Migrate
maintained examples and current guides explicitly; refresh reviewed sidecar pins.
Historical acceptance documents and recorded historical outcomes remain history,
not executable proof under the new declaration. Internal Python constructors may
retain their positional layout for bounded migration, but must not create a
second YAML grammar or bypass runtime identity/session validation.

## Authentication port and trust boundary

Authenticator identifies a logical user's fixed, opaque principal identity and
acquires an authenticated session for that same logical user. Core validates
nonempty strict-string principal/session identities, rejects duplicate principal
bindings, rejects changed principals on reauthentication, and rejects reused
authentication identities on a requested new session. Resolve declared principals
before business actions; actual authentication remains lazy. No implicit fallback
to the old opaque role-only session protocol may pass a users declaration.

The concrete interface is `identify(user) -> str` and `session(user) -> UserSession`.
`UserSession` is a frozen keyword-only value containing `principal_id`,
`authentication_id`, and opaque `credentials`, all hidden from repr and tagged
sensitive. Each call to `session` must acquire a new authentication instance;
core, not the adapter, decides when to call it. Account bindings must not be
reselected by role or restore permissions. An inability to provide this capability
is a structured execution error, never an anonymous fallback or pass.

Adapter-provided identities are a declared trust boundary, not cryptographic
proof against a malicious adapter. An independent synthetic target must actually
enforce per-account access and session policy in reference tests. No credentials,
principal IDs or authentication IDs enter default reports or expanded views.

## Execution and evidence

A projection-local session manager owns each logical user's session and a
value-free generation number (first acquisition 1; explicit new increments).
Anonymous execution passes no credentials and never calls Authenticator. It
must not inherit an already authenticated browser context or transport default.

Backend acquires the correct session after bindings resolve and before execution.
Polling attempts reuse that session; they do not repeatedly authenticate.
An ordinary mismatched 401/403 remains a check failure, not an automatic refresh.
All execution ERROR/SKIPPED and explicit `on_failure: stop` retain their existing
stop semantics. Permission change and cleanup are visible declared actions.

The existing shared frontend/e2e loop remains the only UI orchestrator. Maintain
one live context per current user/session, switch without closing other users,
and close/replace only the selected user's context on new authentication. Close
all remaining contexts exactly once on normal and failure exits. A new context
starts with the intended fresh authentication, not inherited storage from the
old context. Login-page behavior still requires declared UI primitives.

Core-issued UI permits bind user, session generation and context identity in
addition to existing run/action/request identities. Evidence and traffic must
match. Browser support refuses a permit for the wrong bound context. Cross-user
and stale-generation evidence cannot satisfy checks. Mock response order remains
global and explicit across contexts; opening a context must not reset or clone
the consumption queue. Do not construct mocks from expectations.

Step reports include effective user and actual session generation (no generation
for unexecuted work). Response origins and cross-step binding provenance include
their source user/generation. Report inclusion source aliases separately. Live
recordings retain core-controlled user/generation metadata; normalization cannot
rewrite it. Backend also retains its own recording snapshots and validates
Recorder append/read results, including strict identity types, content, count,
and order. Unverified adapter records cannot replace core evidence; a mismatch
is an execution error even when contract is not selected. This preserves evidence
across a port boundary, not a claim of independent observation of the target.
Contract consumes those recordings without authentication and checks
their declared user attribution; it does not add independent identity evidence.
Runner also supplies backend step execution metadata so contract compares the
actual session generation, not merely a positive number. A direct contract call
without that execution provenance cannot verify a flow containing session
replacement and must report an error rather than guess from the static plan.
No recording from another user may substitute merely because endpoint and step
labels match. Sensitive runtime values remain excluded from default repr.

## Required validation and negative controls

1. Required list, strict member types/uniqueness; empty/single/multiple cardinality;
   unknown/missing user on ordinary, wait and include steps; forbidden role/map/
   dynamic actor selection; strict session policy and anonymous rejection.
2. One-user child maps to two different parent users without changing child bytes;
   correct named results, source aliases, independent binding values and policy.
   Reject multi-user children, anonymous/authenticated mismatch, nested includes,
   missing/stale pins and attempted child session/assertion override.
3. Preflight missing identity capability/configuration and duplicate accounts:
   zero business actions. Lazy acquisition and reuse, changed principal on new,
   repeated authentication identity, invalid types and authentication errors.
4. No authentication for anonymous actions; no inherited browser/storage or
   transport credentials. Same-account new session does not grant permissions.
5. Owner succeeds, distinct authenticated peer denied, positive same-role evidence
   where asserted. Permission change is an actual action. Old session check can
   fail while new-session comparison still runs; overall result remains failed.
6. Backend, mock UI and live e2e user switching, generation and context isolation,
   wrong-user/stale-session/cross-run evidence, poll reuse, mixed API/UI session
   reuse, global mock ordering and exact close counts on all failure paths.
7. User/generation diagnostics and reference provenance, sensitive sentinel repr,
   contract wrong-user/missing-session metadata and no extra authentication.
8. Source/CLI expansion and impact review do not conceal changed user/session
   bindings or treat unchanged pin bytes as unchanged caller obligations.

## Consumers, migration and acceptance

Use existing public Demo/browser support for real Chromium context switching and
live/mock evidence. Use the unrelated synthetic Documents target for actual
owner/peer access and old/new authentication after permission changes. Tests
must actually enforce the policy, not return expected results from YAML.
No private product code, schema, roles, evidence or paths enter public artifacts.

Migrate maintained YAML, reference authenticators, test fakes, executable docs,
and current authoring examples to the strict declaration. Preserve business
checks; review intentional format-derived hash changes separately from runtime
results. Do not rewrite historical measured outcomes as new results.

Run focused negative controls, real Chromium tests without skip, full regression,
isolated dev-only tests, Scenario/doc loading, repository hygiene, lock and diff
checks. An independent reviewer audits the finished implementation and runs
additional probes, followed by architect acceptance. Document actual commands,
counts, limits and findings. Stop unstaged/uncommitted/unpushed; no workroom work.
