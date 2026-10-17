# Review exercise: first pass

This optional comparison remains unmeasured and is not a required next gate.
For a shorter practical walkthrough, start with the repository's
`examples/scenario-reuse/README.md`.
The business changes below remain unchanged; a walkthrough does not count as
answering them. Current executable YAML and sidecar pins have been migrated from
`actor` to `users` for the current engine. Recorded historical measurements remain
unchanged and refer to their original inputs, not these migrated bytes. The
migration is not a new human review or a repeated measurement.

This is a small review exercise, not a request to approve a product release.
Please judge each proposed change independently against the same requirements.
You can answer **approve**, **reject**, or **insufficient information**, with one
short reason. No implementation or terminology quiz is intended.

## Requirements to retain

1. Create an item named `review-draft`, sending rows `[1, 2, 3]`. Check success,
   the returned ID and requested name, and the creation span's `row_count == 3`.
2. Update that same ID to `review-final`; check success, the same returned ID,
   and the update span.
3. Read the collection; check success and exactly one member with that ID and
   `review-final` (not a total collection size of one).

These are hypothetical exercise requirements. If they are unclear or unsuitable,
say so before deciding; a requirement correction is not a review mistake.
The span reports what the Demo says happened, not an independent database audit.

The [included baseline](baseline/included.yaml), [child](baseline/child.yaml),
[child pin](baseline/included.includes.json), and [flat baseline](baseline/flat.yaml)
contain the full executable YAML and exact pin. A pin detects changed bytes;
it does not prove approval. Each change below starts from this baseline, not
from the preceding change. The snippets are exact source diffs, not translated
requirements; full files remain available if the snippets are insufficient.

## A — included form

Full proposed [parent](case-02/included.yaml), [child](case-02/child.yaml), and
[pin](case-02/included.includes.json). The child and pin are unchanged.

```diff
--- baseline/included.yaml
+++ case-02/included.yaml
@@ -9,7 +9,7 @@
   - id: setup
     do: {include: review.create_item}
     with:
-      item_name: {from_parameter: draft_name}
+      item_name: {from_parameter: final_name}
   - id: update
     do:
       request:
```

## B — flat form

Full proposed [Scenario](case-01/flat.yaml).

```diff
--- baseline/flat.yaml
+++ case-01/flat.yaml
@@ -6,7 +6,7 @@
   draft_name: review-draft
   final_name: review-final
 steps:
-  - id: create
+  - id: persist
     do:
       request:
         method: POST
@@ -28,7 +28,7 @@
     do:
       request:
         method: PUT
-        path: [items, {from_step: create, response_field: itemId}]
+        path: [items, {from_step: persist, response_field: itemId}]
         body:
           name: {from_parameter: final_name}
     expect:
@@ -36,7 +36,7 @@
         - {check: success}
         - check: field_equals
           field: itemId
-          value: {from_step: create, response_field: itemId}
+          value: {from_step: persist, response_field: itemId}
       backend_state:
         - {check: span_exists, span: item.update}
   - id: read
@@ -50,6 +50,6 @@
         - check: collection_matching_count
           field: items
           matching:
-            id: {from_step: create, response_field: itemId}
+            id: {from_step: persist, response_field: itemId}
             name: {from_parameter: final_name}
           count: 1
```

## C — included form

Full proposed [parent](case-03/included.yaml), [child](case-03/child.yaml), and
[pin](case-03/included.includes.json). The parent YAML is unchanged.

```diff
--- baseline/child.yaml
+++ case-03/child.yaml
@@ -22,6 +22,5 @@
           value: {from_parameter: item_name}
       backend_state:
         - {check: span_exists, span: item.create}
-        - {check: span_attr, span: item.create, attr: row_count, op: '==', value: 3}
 results:
   record_id: {from_step: create, response_field: itemId}
```

The changed child also requires a changed pin. Review both; a refreshed hash is
not a reason by itself to approve the change. See the complete
[old pin](baseline/included.includes.json) and [new pin](case-03/included.includes.json).

## Reply

```text
Requirements clear / need clarification:
A: approve / reject / insufficient information — reason:
B: approve / reject / insufficient information — reason:
C: approve / reject / insufficient information — reason:
Which part required the most effort or explanation?
Optional: active setup minutes; active minutes and files consulted for A/B/C.
```

Times are optional self-reports, not chat elapsed time. Include time inspecting
children and pins. Missing measurements remain unknown. Results stay in the
conversation unless you authorize a scoped public summary.

After this first reply, the opposite representation of each case can be reviewed
without changing the first answers. That second pass is affected by learning.
One person's three changes cannot establish general savings or review quality.
The separate `answer-key.md` contains the audit rationale: please leave it until
after the first pass if you want an unprompted review. This is not a blinded study.
