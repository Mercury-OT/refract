# Two paths reusing one reviewed Scenario

## Authorization and stopping point

The maintainer authorized preparation on 2026-10-22, then confirmed the shared
child, existing update parent and proposed deletion parent and requested local
development, independent audit and acceptance. The earlier plan placed development
after run-values delivery; the confirmed local-work sequence now proceeds while
that separately accepted slice remains uncommitted. Preserve its exact files and
report the combined working-tree baseline. This task uses no run-value syntax.
Neither task authorizes staging, commits, pushes, PRs or merges here.

Delivery: [local acceptance](scenario-path-reuse-acceptance.md) passed after
independent audit and full regression. Submission remains separately gated.

Use only the public Demo, existing Scenario contract, examples and tests. Do not
access private workspaces or products. Public text remains English; the
maintainer receives a Chinese explanation in the conversation. Approval of a
draft is not execution evidence or permission to publish.

## Purpose and existing baseline

Determine what existing one-level inclusion already provides for two paths with
a shared creation prefix. This is not a Flow implementation, a new file format,
deeper nesting, a UI, or proof of reduced review time or improved review quality.

Reuse unchanged:

- `examples/scenario-reuse/shared/create_item.yaml` and its public named results;
- `examples/scenario-reuse/create_update_read.yaml` and its existing sidecar;
- existing create/read examples, reuse review material and the `impact` command.

Creation and update/read already have executable coverage. Do not report them
as newly implemented capabilities. Existing review cases already demonstrate
internal renaming, changed caller input and a removed assertion; reuse those
cases rather than constructing another review experiment.

The Demo supports PUT/DELETE of an item and GET of the complete list. It does
not support GET of a single item. Therefore disappearance is checked by actual
ID in the complete observed list, not a 404 from a nonexistent route. This
assumption must not be generalized to paginated or incomplete product lists.

## Approved additional parent

File: `examples/scenario-reuse/create_delete_read.yaml`.

```yaml
schema_version: 1
scenario: demo.create_delete_read
description: Create, delete, then confirm that the created item is absent from the list.
users: [user]
parameters:
  record_name: Delete test record
steps:
  - id: create
    do:
      include: shared.create_item
    with:
      item_name: {from_parameter: record_name}
  - id: delete
    do:
      request:
        method: DELETE
        path: [items, {from_step: create, result: record_id}]
    expect:
      response:
        - {check: success}
        - {check: field_equals, field: deleted, value: 1}
      backend_state:
        - {check: span_exists, span: item.delete}
  - id: read
    do:
      request:
        method: GET
        path: [items]
    expect:
      response:
        - {check: success}
        - check: collection_matching_count
          field: items
          matching:
            id: {from_step: create, result: record_id}
          count: 0
```

Its new sidecar must pin the same existing child file and exact bytes as the
update/read parent. Do not copy the child, refresh existing pins, or reinterpret
a matching pin as proof of human approval. The Chinese review copy may have
different comments; execution and sidecar hashing use the English source bytes.

## Execution and review boundaries

Each parent runs separately with backend projection, producing its own ordinary
RunReport. Both execute the child; neither caches a previous result. Within a
parent the single declared user reuses its projection-local session. Separate
parents do not share sessions, results or execution identity. Fixed example names
are deliberate: the Demo permits duplicate names and references use observed
IDs. This task does not depend on run-token syntax or claim environment isolation.

Run both orderings against a fresh real Demo process per test, retaining an
unrelated item. Each ordering uses one target process for both paths to expose
possible sibling interference. Require separate created IDs within that target;
do not assume IDs are globally unique across fresh processes. At the end of each
ordering, the modified item must retain its expected updated name and the
unrelated item must remain unchanged. In update-then-delete order, also check that
deletion preserves the already modified item. Compare only declared
properties, not presumed rollback, transactionality or universal isolation.

Default assertion FAILED continues; ERROR, SKIPPED and explicit leaf stop retain
their current behavior. Never change failure policy to make a demonstration
green. Child checks, parameters, user rules and result sources remain unchanged.
No UI evidence is claimed. Demo authentication is synthetic, and its spans are
system-reported, not independent database or real authorization evidence.

Reusable review covers unchanged, applicable child internals. Both callers still
require review of chosen inputs, user mapping, order, result use and final
obligations. In particular, a final count of zero means no member with the
created ID, not an empty list or a missing response field. Do not substitute a
name, position, guessed ID or previous run's evidence.

## Bounded verification

1. Load exact files and sidecars; compare existing child/update source bytes
   with the starting baseline. Validate/expand must preserve every child check,
   effective user and named result, without an action or a generated value.
2. Execute both parent orderings with real Demo HTTP. Require each RunReport to
   be PASSED, without degradation. Inspect current-run recordings for the two
   POSTs, distinct created IDs and each update/delete/read binding. Independently
   read the final list to check the retained unrelated and modified items.
3. In test-only observation wrappers, verify session reuse inside each parent
   and new authentication identities across parents; retain normal Demo behavior.
   Do not claim that the Demo server enforces these account identities.
4. Unknown named results, undeclared users and stale pins must be rejected
   before authentication or requests. A missing consumed response ID must block
   the dependent action; inspect actual statuses, not only a nonzero exit.
5. A test-only caller variant sending the initial name on update while retaining
   the final-name check must execute and fail that check. A labeled observation
   fault omitting the list field must not satisfy the zero-count assertion.
   Do not monkeypatch core validation or assertions, and distinguish altered
   observations from actual target defects.
6. Use the existing impact tool on temporary, explicitly selected source copies.
   A child byte change must identify both callers and their stale actual pins;
   sources stay unchanged. Separately exercise a removed consumed public result.
   Reuse current CLI behavior; do not build a new analyzer or update pins silently.
7. Explain the existing wrong-input-and-matching-expectation review case: a valid,
   green declaration can still violate the approved intent. This remains a human
   judgment, not a new detector. Report unmeasured review effort as unmeasured;
   no AI timing, line count or test count substitutes for human review evidence.

## Deliverables and acceptance

Following expression confirmation, add only the new parent and sidecar, bounded
tests, a short addition to the existing reuse README, and a local acceptance
record. A two-path outline is a reading aid, not another executable format.
Use existing tests and examples as references rather than duplicating them.

Architect acceptance checks exact scope, declaration/execution distinctions,
real HTTP results, negative controls, impact output and public-source neutrality.
Run targeted tests, full regression, core-only/import checks, lock, hygiene and
diff/index checks. Record the actual source revision and any prior unmerged
changes; do not attribute the preceding run-values tests or changes to this task.

No changes to core, vocabulary, existing YAML, adapters, Demo target, dependencies,
CI, MANIFESTO, BRAND, historical evidence or workroom. Any newly discovered
implementation defect is reported for separate scope approval, not fixed here.

The final decision may be that current parent/include composition suffices for
these two paths. A new Flow proposal requires a concrete remaining limitation,
explicit session/result/failure boundaries and a separate expression review.
No result from this exercise automatically authorizes Flow or graphical work.
