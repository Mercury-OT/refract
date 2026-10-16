# Review exercise answer key — read after the first review

This is an inspectable exercise key, not a hidden, independent or tamper-proof
oracle. Its judgments assume the three synthetic requirements in the task
specification remain fixed. A participant can reasonably question those
requirements before reviewing; that starts a different baseline rather than
constituting a missed defect. No participant decisions or human time are
recorded here.

## Case 01

Expected decision: approve, after reviewing the internal rename and updated pin.

The child step changes from `create` to `persist`, and the `record_id` result
source changes with it. The included parent is byte-identical. Its sidecar must
pin the new child bytes; an old pin correctly fails loading. The flat form makes
the corresponding first-step rename and updates all three local response
references. Requests and assertions are unchanged after resolving references.

This illustrates the possible maintenance value of a stable named result. It
does not show that reviewing the child or pin is free, nor that a new fingerprint
is automatically approval. Actual human effort is still unmeasured.

## Case 02

Expected decision: reject against fixed requirement 1, or request a requirement
change before approval.

The included parent supplies `final_name` instead of `draft_name` for creation.
The child and pin are unchanged. The child correctly checks the supplied name;
it cannot know that this caller was supposed to supply the draft name. The flat
form changes both the creation request and its matching name assertion to the
same final-name parameter, so it has exactly the same checks and weakness.

Both forms pass against the normal Demo, but actual first traffic sends
`review-final`, contrary to the fixed requirement to create `review-draft`.
Updating that item to `review-final` and reading it succeeds. This is a caller
wiring error relative to the exercise requirement, not a Demo product defect or
an include-engine defect. Reusing an approved child does not approve its caller.

## Case 03

Expected decision: reject against fixed requirement 1, or request explicit
approval to remove that evidence obligation.

Only the creation `span_attr` assertion for `row_count == 3` is removed. The
`item.create` span-exists assertion remains. The included parent is byte-identical
and its child pin changes. The flat form removes the same single assertion.

Both forms pass on the unchanged Demo. With the test wrapper changing only the
observed creation `row_count` from 3 to 2, both forms still pass in this case.
Baseline and cases 01/02 detect that observation fault and block later steps.
The wrapper first verifies that the real Demo observation was exactly 3; it does
not change the product's stored rows or replace the evaluator. This is one
selected observation-fault control, not a general mutation score, an independent
database check, or proof of a real Demo data defect.

## Limits and interpretation

- Declaration validity and normal execution success cannot approve changed
  requirements or prove the requirement set is complete.
- Pairs have the same requests and every assertion. A shorter parent is not a
  stronger or weaker oracle in itself; child and pin review remains in scope.
- Only backend execution is tested here. No UI, contract, or additional evidence
  independence is claimed.
- Runtime and test counts are not human time. Neither these cases nor this key
  demonstrates review cost savings, better approval quality, or product adoption.
- The participant first sees mixed representations, then may see the opposite
  representations. The second pass is affected by learning; a one-person exercise
  cannot establish a causal advantage or a population estimate.
- Preserve first answers and any missing measurements honestly. Do not add
  personal results to public files without separate permission.
