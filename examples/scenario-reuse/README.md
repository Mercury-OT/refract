# Review a reused Scenario

This small public Demo example creates one item, then reads the list and checks
the same item. It uses existing one-level inclusion and named results; no new
syntax, runtime behavior, or approval system is introduced.

## Read the pair together

1. [Child: create an item](shared/create_item.yaml) accepts `item_name`, checks
   creation, and exposes `record_id` and `record_name` from the actual response.
2. [Parent: create, then read](create_read.yaml) supplies `Test record`, then
   checks exactly one list member matching both the returned ID and that expected
   name. It does not require the whole list to contain only one item.

The parent deliberately checks the name against its input requirement rather
than simply repeating an observed name. Its `setup` reference identifies this
invocation of the child, not the child's internal step name. The returned values
belong to this run; no earlier execution result is reused.

## What needs review?

First review the child fully. For later parents, unchanged child internals can
reuse that review when the previous assumptions still apply. The reviewer should
still have access to the full child, not just a label saying it was approved.

For **each new parent**, review:

- Whether this child is appropriate here, including the mapped logical user and starting state.
- Which values are passed, including defaults that are relied on.
- Where the child runs in the sequence and how its results are used.
- What the parent requires afterward, and whether its assertions cover that.

In this example the question is: should this caller create `Test record`, then
require a matching record in the returned list? The existing creation request,
creation checks, and mapping of child response fields to named results need not
be re-read line by line for every caller if unchanged and still applicable.

The [sidecar](create_read.includes.json) identifies the child file and fixes its
exact byte fingerprint. It detects a different file; it does **not** record or
prove human approval. Even comment changes alter the fingerprint. A changed
child requires review of the change and its affected callers before their pins
are updated. Do not refresh pins merely to make validation pass.

Every inclusion still executes all child steps and checks. A prior successful
run cannot replace current evidence. Declaration validity, a human review, and
an execution passing are separate facts. This example's backend span is
system-reported evidence, not an independent database check.

## Several parents sharing one child

A create/read, create/update, and create/delete parent could share the same
creation child. Reuse can avoid repeatedly inspecting the same creation logic,
while each parent still needs its own caller review.

The [create/update/read parent](create_update_read.yaml) is the explicitly migrated
executable copy of the previously approved named-results task example. It uses
this same child and its own [pin](create_update_read.includes.json), preserving
the creation, update and read assertions. The historical task prose and measured
outcomes are not rewritten; this current example uses `users` instead of `actor`.

More repeated use of a stable child creates more opportunities for saving review
effort. It also means more affected callers when that child changes. No time
saving, correctness percentage, or linear relationship has been measured by this
example. It does not justify additional nesting or automatic approval propagation.

## Two separately executed paths

The [create/delete/read parent](create_delete_read.yaml) uses the same unchanged
child, with its own [pin](create_delete_read.includes.json). These are ordinary
parents, not a new Flow format:

- Create/update/read: create a record, update its observed ID, and check the new name.
- Create/delete/read: create another record, delete its observed ID, and check its absence.

Each parent executes creation again and produces its own report. The single user
reuses a session within each backend run; separate runs acquire separate sessions
even when they use the same adapter instance. This is not target-state isolation.
The Demo authentication is synthetic, and spans are system-reported evidence.

Deletion expects `deleted: 1`, then zero members with the created ID in the Demo's
complete list. It does not require an empty list, and a missing `items` field must
fail rather than count as zero. Do not apply this absence check to a paginated or
incomplete list without another appropriate check. A retained same-name record
must remain: neither deletion nor the final expectation uses names as identity.

Run the bounded real-HTTP checks with:

```sh
uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/demo/test_demo_path_reuse.py
```

Both parent orderings are checked on one target per ordering, retaining an unrelated
record and the updated record. Negative controls distinguish unavailable response
IDs, a wrong update input with the final obligation unchanged, and a missing list
observation. Observation wrappers are test faults, not defects attributed to the
Demo. The existing [review exercise](../../docs/review-exercise/README.md) also
shows that changing both input and expectation can remain green while violating
the approved intent; declaration validation cannot replace that human judgment.
Human review time and quality remain unmeasured. Current one-level composition is
enough for these two paths; this example does not authorize deeper inclusion or UI.

## Validate and run

From the repository root, in the existing project environment:

```sh
uv run --locked --no-sync refracto validate examples/scenario-reuse/create_read.yaml
uv run --locked --no-sync refracto validate examples/scenario-reuse/create_read.yaml --expand
```

These commands check the declaration/pin and print an optional symbolic expanded
view; they do not execute the application or grant approval.

With the existing Demo test dependencies installed:

```sh
uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/demo/test_demo_reuse_walkthrough.py
```

The test starts an isolated real Demo server and uses the existing adapters. An
unrelated item is present before the Scenario runs, so the check cannot silently
depend on an empty list. Tests verify execution and example fidelity, not human
review cost. No private product, UI, or contract-projection evidence is claimed.
