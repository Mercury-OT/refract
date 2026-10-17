# Mixed anonymous users and explicit included-user mappings

Status: approved for specification, implementation, independent audit and local
architect acceptance on 2026-10-17. Starting main: `68af23a`.
The maintainer separately and explicitly authorized submission after those gates
pass in this request. No staging or submission before final acceptance.
Only public synthetic sources and consumers are in scope; no private workspace
access, product changes, new dependencies, MANIFESTO or BRAND changes.

## Purpose and non-claims

Run authenticated and anonymous actions within one Scenario. Reuse an unchanged,
pinned multi-user child under explicit caller-selected participants. This is
static one-level sequence inclusion, not recursion, branching, a user generator,
or permission to change child actions or expectations. Review of a child does
not approve arbitrary caller bindings, prove account truth, or establish review
cost savings. No new rejection categories or automatic authentication recovery.

## Approved expression and exact boundaries

Keep `schema_version: 1`, all existing action/expectation/value/reference forms,
named results, query support, failure policy and sidecar content pins.

1. `users` remains a required list of distinct nonblank literal strings. Exact
   lowercase `anonymous` is reserved for no account binding, never passed to
   Authenticator as an account name. Other names remain logical account aliases.
   Null, booleans, mappings, duplicate names and dynamic selections are invalid.
2. `users: []` retains its implicit anonymous behavior: ordinary steps omit both
   `user` and `session`. With one declared participant (including `anonymous`),
   omission selects it. With two or more participants, every ordinary step,
   including waits, explicitly selects one declared `user`. Explicit null or an
   empty value is never a shortcut for anonymous. `anonymous` must be declared
   when selected in a nonempty users list.
3. Named users keep lazy acquisition and current-session reuse. `session: new`
   remains ordinary-leaf reauthentication of that same named user. An anonymous
   leaf with `session: new` fails before any action, including when an included
   named user is mapped to anonymous. No silent omission of a session policy.
4. Anonymous actions do not identify or authenticate an account, and never
   replace, log out or inherit another participant's credentials or UI context.
   Switching back to a named user reuses its retained current session. One
   anonymous context may be reused within a projection; it is isolated from
   authenticated contexts and from other runs. No multiple anonymous identities
   or explicit anonymous-context renewal facility is introduced.
5. Multi-user children may now be included, but they must remain leaves: no
   include inside a child. The child independently validates with at least one
   assertion. Existing cycle, path, pin, step-count and result-visibility limits
   remain. Parent edits never rewrite the pinned child bytes.
6. Include steps may use `with_users`, a nonempty literal mapping whose keys
   exactly equal the child's declared `users`. Values select declared parent
   participants. For a parent with `users: []`, the only implicit target is
   `anonymous`. No missing/extra keys, nulls, expressions, unknown targets or
   duplicate YAML keys. `with_users` is rejected on ordinary steps.
7. A child declaring two or more participants requires `with_users`, even when
   the two lists happen to contain the same names. Its include node must not
   also contain `user`: the mapping replaces the single-executor choice at that
   node. A single-user child may use the same complete mapping, or retain the
   existing `user`/single-parent-default shorthand. `with_users` and `user` are
   mutually exclusive for every include node. A child with `users: []` uses the
   anonymous shorthand only, not a pointless empty mapping.
8. An explicitly or implicitly anonymous child participant stays anonymous;
   it cannot be rebound to a named user. A named child alias may map to either
   a named parent user or anonymous, subject to all unchanged child assertions
   and session rules. Distinct child participants cannot map to the same target,
   including anonymous. Actual principal uniqueness for named parent users is
   still checked before actions; two aliases must not conceal one account.
9. Include nodes cannot override child assertions, session policies, failure
   policies or selected steps. A child expecting an authenticated denial remains
   that declaration: substituting an anonymous caller does not turn a 401 into
   an accepted 403. Appropriate caller mappings require human review; core
   does not infer that an unchanged child is suitable for every new context.

Illustrative caller fragments (not standalone executable Scenarios):

```yaml
users: [owner, peer]
steps:
  - id: access_check
    do: {include: shared.access_check}
    with_users: {creator: owner, reader: peer}
```

```yaml
users: [owner, anonymous]
steps:
  - id: access_check
    do: {include: shared.access_check}
    with_users: {creator: owner, reader: anonymous}
```

The fixed child declares `users: [creator, reader]`; its actual steps and
expectations determine whether either mapping passes. Both parents pin the same
bytes. Business values continue to use `with`, independently of `with_users`.

## Compilation, review and runtime

Expansion resolves each child's own effective participant independently, then
maps it to its caller participant. Never assign one include-wide user to every
leaf. Preserve cross-step references, named results, parameters, declaration
order, explicit new sessions, stop policies and assertion values. Compile to
the existing flat runtime shape; no second orchestration loop.

Retain the existing anonymous execution protocol: no principal/credentials,
runtime user `None`, session generation 0. Named users retain their names and
positive generations. The declaration must distinguish the literal anonymous
choice from omitted/default user selection before translating to that protocol;
Python-constructed declarations receive equivalent preflight validation.
Review views show the explicit `anonymous` selection and the complete child-to-
parent mapping, plus each leaf's local and effective participant. Reports,
recordings and binding origins continue to use the documented runtime identity;
an unexecuted step must not invent an acquired session. Default representations
must not expose credentials, principal/authentication IDs or resolved values.

SessionManager identifies only named users, including in mixed declarations.
Backend and the shared frontend/e2e loop reuse it. Poll attempts retain the
selected lease; blocked steps do not acquire or renew a session. Context open,
switch, renewal and close preserve isolation and exactly-once cleanup. Anonymous
API sends receive no credentials; reference transports must not reuse a previous
user's authentication defaults. Browser support keeps existing no-inherited-
storage/credentials guards and verifies user/generation/context ownership.

Contract consumes backend recordings without authenticating or sending another
request. Mixed attribution must match each expanded leaf and actual backend
generation; tampered anonymous/named attribution is an error. Contract remains
another check of the same evidence, not an independent identity witness.

Expanded and impact review must expose `with_users` and distinguish an old/new
child's local participants, effective bindings and session policies. No runtime
values, pin updates or automatic approval. A changed caller mapping needs review
even when child bytes and pins have not changed. Historical measured outcomes
remain historical; update current guides, not earlier acceptance evidence.

## Required checks and negative controls

- Empty, anonymous-only, named-only, and mixed cardinalities; explicit/omitted
  defaults; undeclared anonymous; null/empty/dynamic values and duplicate keys.
- Named -> anonymous -> named reuses the original named lease, zero anonymous
  authentication calls; anonymous-only runs need no Authenticator. Separate
  named accounts, strict generation types, session failures, blocked consumers,
  polling and `session: new` semantics retain their original gates.
- Complete maps for single/multi-user children; unchanged pinned child reused
  by two callers; reject missing/extra/duplicate/dynamic maps, undeclared values,
  user-plus-map, colliding targets, anonymous upgrade, anonymous reauthentication,
  stale pins, nested includes and forbidden override fields before side effects.
- Included and hand-authored flat flows produce equivalent observations except
  source provenance. Cross-user and cross-include named results, query references,
  continuation/stop policy, local alias remapping and report attribution work.
- Backend plus contract and explicit-API e2e against public Documents exercise
  actual 200/201/401/403 decisions. A caller changing a named reader to anonymous
  does not weaken fixed 403 assertions; record the resulting failure honestly.
  Positive coverage for both modes uses an explicitly appropriate unchanged
  declaration, not mock responses made from expectations.
- Real Chromium live and mock paths exercise named/anonymous context switching,
  same-user return, separate cookies/storage, global mock consumption, zero
  hidden login/logout, exactly-once closure and second-run isolation. Include
  wrong-user, wrong-generation, stale/replayed context and credential-leak
  controls. A second public Demo/reference transport covers actual HTTP sends.
- Review/CLI and impact views expose all mappings and provenance; negative
  controls prove malformed maps cannot become a valid flattened view. Report,
  permit, evidence and session default representations retain sensitive-value
  protections. No response classification or authentication claim from a label.

## Delivery gates and scope

Deliver code, maintained documentation, synthetic parent/child examples with
reviewed sidecar pins, focused positive and negative tests, and a local acceptance
record. Public sources are the approved neutral expression and existing public
code, Documents/Demo targets and browser laboratory. Do not change target
authorization policy just to make a test pass. No real-product adoption claim.

Run targeted tests and independent additional probes, full regression with real
Chromium (not skipped), fresh dev-only dependency isolation, maintained Scenario
loading, executable-document checks, lock, hygiene and diff checks. Independent
audit owns no implementation edits. Final acceptance freezes the public file
scope before the conditionally authorized submission workflow. No private
workspace work, multilevel composition, dynamic identity, role declaration,
new rejection taxonomy or general authentication/security platform.
