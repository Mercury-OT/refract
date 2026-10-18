# Stabilization: vocabulary and contract maintenance review

## Scope and decision boundary

This is delivery group 3 of the [approved stabilization specification](stabilization-20261018.md), not a language change or a contract-positioning decision.
The inspected source revision is `936c50aee490ff9d97ec7ee8bbd207f94de5eda5`; the batch starts after `67ce17f8855f976d138ee84e34e2df5fdde31cbe`.
All findings below derive from public source, public synthetic examples, and their tests.
No private product behavior or adoption claim is inferred.

**Recommendation:** retain the existing vocabulary for this sprint. There are narrow overlaps worth documenting, but no demonstrated maintenance or review benefit that justifies a new loader rejection. Keep contract's current guarantees while separately deciding its future role; shared recordings do not make its checks independent, but neither do they make those checks valueless.

The tables distinguish inspected implementation facts from recommendations and hypothetical future changes. Test references identify existing executable evidence; this report does not claim a new test run or new mutation score. The [measurement report](stabilization-20261018-measurements.md) records the actual bounded measurements separately.

## 1. Response equality: overlap is not interchangeability

The implementation sources are [`values.py`](../../refracto/declaration/values.py), [`field_comparison.py`](../../refracto/declaration/field_comparison.py), [`numeric_comparison.py`](../../refracto/declaration/numeric_comparison.py), [`collections.py`](../../refracto/declaration/collections.py), [`http_status.py`](../../refracto/declaration/http_status.py), [`headers.py`](../../refracto/headers.py), and their use in [`backend.py`](../../refracto/projection/backend.py) and [`contract/store.py`](../../refracto/contract/store.py).

“Equivalent” below means the same pass/fail predicate within the stated valid domain, not identical declaration validation, diagnostics, or evidence provenance. Missing or malformed evidence must not be replaced with a convenient value to manufacture equivalence.

| Apparent overlap | Exact domain or counterexample | Affected maintained material | Recommendation, not a new rule |
| --- | --- | --- | --- |
| `field_equals` versus `field_compare` with `op: ==` | Equivalent when the observed field exists and both operands are valid finite numbers. Both retain exact type: integer `1` is not float `1.0`, and booleans are not numbers. `field_equals` also supports strings, null, booleans, complete objects and lists; numeric comparison does not. Runtime threshold validation has its own failure boundary. | `tests/test_response_numeric_length.py::test_exact_numeric_comparison_has_no_float_rounding`; `tests/test_response_field_comparison.py::test_complete_type_strict_comparison_and_complement`. The maintained page-limit examples use numeric inequalities, not numeric `==`. | **Keep** both. Prefer `field_equals` for a plain equality explanation and numeric operators for bounds, without forbidding a consistent numeric operator family. **Defer** any canonical-style restriction until it has measured review benefit. |
| Whole-list `field_equals` versus `collection_length` with `op: ==` | Length does not check contents or order: `[1, 2]` and `[2, 1]` have the same length but are not equal. In the narrow domain of valid lists, length zero and equality to `[]` agree. That special case does not make arbitrary list equality redundant. | `examples/minimal/check_page_limits.yaml`; `examples/documents/scenarios/check_page_limits.yaml`; `tests/test_numeric_check_consumers.py::test_actual_empty_oversized_or_wrong_type_page_cannot_pass`; `tests/test_field_comparison_consumers.py::test_complete_list_field_uses_real_target_content`. | **Keep** both; **defer** rejecting an empty-list spelling. A size promise and a content promise should remain separately visible. |
| Exact list length versus `collection_matching_count` | Matching count examines only members meeting all declared scalar predicates; list length counts every element. Two objects with only one matching `category` give length two and matching count one. Matching requires object members and a nonempty predicate map; length can count heterogeneous valid JSON-like members. They agree only with additional knowledge that every member matches, which the length assertion itself does not establish. | Both page-limit examples deliberately use both checks; `tests/test_collection_matching_count.py::test_exact_content_matching`; `test_malformed_collection_never_counts_as_zero`; `tests/test_response_numeric_length.py::test_list_length_counts_heterogeneous_duplicate_and_shared_members_without_mutation`. | **Keep**, without normalization into one another. **Reject the proposed equivalence**, not either YAML form. |
| `field_equals` on a reported count versus length of the actual list | A reported count can be wrong independently of the list. A response reporting one while returning two members can pass a count-field check and fail the actual length check. Deriving the reported count in the normalizer would erase the distinction. | Page-limit examples; `tests/test_numeric_check_consumers.py::test_reported_count_is_checked_without_repairing_it_from_the_actual_list`; `test_correct_bounds_do_not_hide_wrong_filter_or_repeated_page`. | **Keep** the distinct observations. Do not remove one merely because the normal response currently makes them equal. |
| `status_equals: N` versus `status_in: [N]` (parameters abbreviated here) | Exact equality and singleton membership agree for the same valid captured integer HTTP status. A larger set is deliberately weaker than any one member. Both use captured transport evidence, not a normalized field named `status`; allowed values are literal integers from 100 through 599. | `tests/test_http_status_assertions.py::test_evaluator_captured_fact_not_normalized_fields`; `test_contract_status_and_recording_identity_are_independent_of_normalizer`; inventory below. | **Keep** both accepted forms. Prefer exact status when the obligation specifies one. **Defer** a singleton-set ban: no maintained executable YAML currently needs migration, but tests and syntax documentation would change. |
| Raw status checks versus `success` / `failure` or `field_equals` on a normalized status-like field | These are not equivalent. A body may report business failure with HTTP 200, and a normalizer may expose a misleading status field. Business outcome and actual HTTP status are intentionally independent obligations. | `examples/documents/scenarios/http_status_create_delete.yaml`; `tests/test_http_status_assertions.py::test_success_failure_and_status_constraints_remain_independent`; `test_execution_ignores_normalizer_status_and_mutation`. | **Keep** the distinct evidence channels. Do not substitute a normalized field for captured status. |
| `header_equals` versus normalized-field equality | Header equality uses a complete captured name/value-pair collection: names are case-insensitive, values are exact strings, and ambiguous duplicate values are not silently flattened. A normalized field can discard duplicates or omit transport evidence. | `examples/documents/scenarios/idempotent_create.yaml`; `tests/test_business_headers.py::test_response_complete_pair_semantics_all_consumers`; `test_no_flattened_or_normalized_fallback_for_new_response_checks`. | **Keep** raw-header equality separate. A future contract role still needs actual header evidence if it promises to check headers. |
| Absence, equality to null/empty, and inequality | Missing `field` fails both `field_equals` and `field_not_equals`; it is not evidence of difference. Present null can satisfy equality to null but cannot satisfy `field_absent`. An empty present header is likewise not absent. `has` admits any present value, not just null. | `examples/minimal/rejected_update_preserves_content.yaml`; `tests/test_response_field_comparison.py::test_missing_current_field_never_satisfies_comparison`; `tests/test_field_absent.py::test_backend_field_absent_fails_for_every_present_value_without_reporting_it`; `tests/test_business_headers.py::test_response_complete_pair_semantics_all_consumers`. | **Keep** absence and inequality distinct. Restricting one in favor of the other would weaken or change an obligation. |

Complete-field equality is recursive and type-strict: object key order does not matter, while list order and scalar types do. Compared data must be finite JSON-like values with string object keys, without cycles. The report does not equate “looks the same in YAML” with type equality.

`from_parameter`, `from_step`, named results, dictionary `key`, and unique-member selection are value sources for these checks, not extra equality operators. A selected value must still be usable at its consuming position; an unavailable response reference is not an unequal value. See `tests/test_response_member_references.py::test_contract_selector_use_sites_follow_runtime_rules` and `tests/test_response_field_comparison.py::test_contract_missing_and_null_source_cannot_be_inequality_evidence`.

### Consequences of a future restriction

- Banning numeric `==` would change the operator-boundary tests and documentation contract, not remove any numeric-equality use from the maintained executable example YAML at this revision. Existing `op: ==` examples under `scenarios/` are `span_attr` checks, a different observation point.
- Banning singleton `status_in` would change accepted grammar and its boundary tests. It would not simplify the only executable shared-child set `[401, 403]`.
- Replacing matching count with length, or complete equality with length, would weaken the page/content examples. This is not a safe vocabulary reduction.
- Replacing absence checks with inequality would allow missing evidence to be misdescribed. The current tests deliberately prevent that.

No restriction above is implemented or approved by this report.

## 2. Complete tracked `status_in` inventory

At the frozen revision, `git grep -n status_in 936c50a -- ':!uv.lock'` reports **33 matching lines in 12 tracked files**. These are textual occurrences, not 33 Scenarios or 33 distinct status sets. Line numbers in this section refer to that revision, not a subsequently edited document.

| File and matching lines | Classification and actual purpose | Multiple-status rationale / review disposition |
| --- | --- | --- |
| `SCENARIO.md`: 358, 506, 523 | Vocabulary entry, prose, and response-fragment illustration `[200, 204]`. | A syntax illustration, not an executable product promise. No product-specific multi-status requirement is supplied. **Review candidate for clearer illustrative labeling**, not a reason to ban the syntax. |
| `docs/roadmap.md`: 35, 204 | Delivery index and expression-approval history. | No acceptance declaration or status set; retain as history. Approval of an expression is not approval of all values authors might put in it. |
| `docs/tasks/http-status-assertions-acceptance.md`: 18 | Description of delivered membership semantics. | No product-status permission claim. |
| `docs/tasks/http-status-assertions.md`: 44, 55 | `[200, 204]` syntax fragment and rejection of simultaneous status constraints. | Generic specification illustration; no independent product rationale. Same labeling recommendation as SCENARIO.md. |
| `examples/documents/scenarios/shared/access_document.yaml`: 46 | **Only tracked executable YAML containing `status_in`**: shared child's `[401, 403]` refusal obligation. | Explicitly allows either login refusal or ownership refusal; deliberately does not distinguish the reason. Its two maintained parents add exact status/reason checks; details below. **Keep** this stated shared promise. |
| `refracto/contract/store.py`: 80 | Consumer-contract documentation. | Definition of captured-status constraint, not an acceptance choice. |
| `refracto/declaration/http_status.py`: 3 | Shared check-name registration. | Definition only. |
| `refracto/declaration/loader.py`: 272, 277 | Loader branch and exact error message. | Enforces nonempty, distinct literal integer set within the status range; does not assert why a business requirement allows multiple statuses. |
| `refracto/declaration/vocabulary.py`: 26 | Required parameter registration. | Definition only. |
| `tests/demo/test_demo_http_status.py`: 33, 34 | Synthetic browser controls: frontend `[202, 204]` must fail against actual mock 201; e2e `[200, 202]` must pass against actual live 200. | Test of capture independence from a misleading normalizer, not a claim that the Demo supports every member of either set as a product outcome. |
| `tests/test_http_status_assertions.py`: 50, 54, 66, 68, 72, 74, 76, 77, 99, 100, 195, 196 | Registration/range test `[599, 100, 204]`; invalid-set parameterization; missing/extra/duplicate/mixed constraints; `[200, 204]` success/failure neighbors in evaluator and contract. | Grammar and evaluator controls. Singleton sets at 74 and 76 participate in **otherwise invalid declarations**; this is not a singleton-set ban. Tests intentionally exercise broad sets and must not be promoted to product commitments. |
| `tests/test_http_status_consumers.py`: 61, 72, 165, 190, 198 | Temporary `[201, 202]` declaration with injected 201/202 passing and 200 failing neighbors; included-contract widening/impact test; documentation-fragment discovery. | `StatusOnlyMutation` supplies the altered statuses. The real Documents create endpoint's 201 does not thereby become a product requirement permitting 202. Widening is tested for review visibility, not endorsed as a change. |

The new stabilization boundary page is outside this frozen inventory: E02 rejects an empty `status_in` set, and E03 rejects combined exact/set constraints. Its sentinel reuses these existing loader rules. New measurement controls and this review's mentions are also not additional frozen product declarations.

### Shared child and exact parent obligations

The child [`access_document.yaml`](../../examples/documents/scenarios/shared/access_document.yaml) says in its source comment that login and ownership refusal are both permitted by its shared promise. It also requires normalized failure and a present error code. This does **not** prove a particular refusal mechanism.

- [`mapped_peer_access.yaml`](../../examples/documents/scenarios/mapped_peer_access.yaml) maps `reader` to `peer`, then makes a subsequent read with exact HTTP 403, normalized failure, and `error_code == owner_required`.
- [`mapped_anonymous_access.yaml`](../../examples/documents/scenarios/mapped_anonymous_access.yaml) maps `reader` to `anonymous`, then makes a subsequent read with exact HTTP 401, normalized failure, and `error_code == session_required`.
- Both pin the same child bytes. `tests/test_anonymous_documents.py::test_same_pinned_child_maps_each_leaf_to_actual_named_or_anonymous_participant`, `test_two_maintained_callers_pin_exactly_the_same_unchanged_child`, and `test_fixed_403_child_is_not_relaxed_by_anonymous_mapping` cover reuse and the prohibition on caller relaxation.

Thus the composed parent does not merely accept any denial. However, the exact parent check observes **another request**: it does not retroactively prove the refusal reason of the earlier child response. This bounded distinction should remain visible when reviewing a parent's intended obligation. It is neither a newly discovered engine defect nor evidence that all broad child contracts are safe.

No current tracked executable use lacks a stated multiple-status purpose after considering its callers. The two generic documentation fragments lack a product rationale because they are illustrations; labeling them more explicitly is a candidate documentation refinement, not an inferred business rule or a new loader policy.

## 3. Direct contract maintenance: reproducible line inventory

Only `refracto/contract/` and `refracto/projection/contract.py` count as **direct contract lines** here. Each row is that commit versus its first parent, as reported by `git show --numstat`. Within this batch, only `contract/store.py` and `projection/contract.py` changed inside that scope.

| Capability group | Commit | `contract/store.py` + / - | `projection/contract.py` + / - | Direct total + / - |
| --- | --- | --- | --- | --- |
| HTTP status | `d2a5ed9` | 26 / 5 | 3 / 1 | 29 / 6 |
| Failure continuation | `95ba66d` | 2 / 2 | 7 / 4 | 9 / 6 |
| Users and sessions | `b2fdab2` | 14 / 3 | 31 / 3 | 45 / 6 |
| Refusal evidence examples | `eaca8cb` | 0 / 0 | 0 / 0 | 0 / 0 |
| Query parameters | `68af23a` | 0 / 0 | 0 / 0 | 0 / 0 |
| Anonymous/include user maps | `0c14865` | 0 / 0 | 0 / 0 | 0 / 0 |
| Business/response headers | `b3ddace` | 25 / 2 | 10 / 6 | 35 / 8 |
| Headers: bounded mock follow-up | `73b356f` | 0 / 0 | 0 / 0 | 0 / 0 |
| Complete field comparison | `b7996c4` | 27 / 9 | 2 / 1 | 29 / 10 |
| Member references | `75db346` | 14 / 0 | 0 / 0 | 14 / 0 |
| Numeric/list-length checks | `936c50a` | 14 / 0 | 0 / 0 | 14 / 0 |
| **Gross sum: ten groups, eleven commits** | | **122 / 21** | **53 / 15** | **175 / 36** |
| **Endpoint diff: start to current** | `67ce17f..936c50a` | **117 / 16** | **48 / 10** | **165 / 26** |

Gross changed lines total 211; the endpoint diff totals 191. Both have net growth of 139 lines. Intermediate additions/deletions account for the 20-line difference in churn; do not add endpoint and per-commit figures together. Zero direct edits do not mean zero integration work. These are source line counts, **not measured engineering hours, review effort, defect rates, or marginal adoption cost**.

### Protected properties and a hypothetical narrower contract role

The hypothetical here is a checker limited to comparing evidence across versions or environments, not a second live execution. “Still necessary” means the property remains necessary **if that checker retains the corresponding declared promise**, not that the present implementation must remain unchanged. “Undecided” means the future input/evidence protocol must be specified first.

| Group | What the direct change protects; actual supporting tests | If contract became cross-version/environment-only |
| --- | --- | --- |
| HTTP status | Consumer stores allowed captured statuses; provider preserves the actual status independently of normalization and does not let malformed capture be repaired by a normalizer. `tests/test_http_status_assertions.py::test_contract_status_and_recording_identity_are_independent_of_normalizer`, `test_contract_rejects_invalid_status_before_normalizer`; `tests/test_http_status_consumers.py::test_documents_status_only_mutation_fails_with_business_success_unchanged`. | **Still necessary** for HTTP-status promises. Historical bundles would also need genuine status capture and compatible step/request identity. A field-only comparator would lose this promise, not merely save duplicate code. |
| Failure continuation | Reuses protected `normalize_response` and converts provider-construction exceptions into structured contract ERROR rather than escaping the report. The direct diff does **not** implement a second continuation loop. `tests/test_failure_continuation.py::test_malformed_normalization_is_never_passing_evidence`; `tests/test_documents_failure_continuation.py::test_documents_collect_checks_and_really_delete`. | **Still necessary** to reject bad evidence without a false pass. **Undecided** whether the present exception/DomainResult wrapper is reused. A standalone comparator would not need its own business-action continuation loop; there is none to remove from these direct lines. |
| Users/sessions | Joins recording user and generation to backend execution provenance; rejects duplicated finals, stale/missing identities and invalid generations. `tests/test_users_sessions_core.py::test_contract_rejects_wrong_or_missing_user_attribution`, `test_contract_rejects_stale_generation_for_same_user_after_new`, `test_contract_rejects_duplicate_or_type_confused_execution_provenance`. | Identity provenance is **still necessary**. The current same-run `execution_steps` join and generation scheme are **undecided**: independent bundle manifests could replace them, but omitting attribution would allow comparison of the wrong actor/session. |
| Refusal evidence | **No direct change**: existing captured-status and normalized-reason checks carry the obligation. `tests/test_rejection_evidence.py::test_invalid_peer_session_cannot_be_counted_as_ownership_denial`, `test_same_403_with_missing_confused_or_wrong_type_reason`, `test_removing_only_reason_check_demonstrates_ambiguous_403_false_positive`. | **Still necessary** to keep the status and reason promises distinct if refusal semantics are compared. No separate direct implementation is available to remove. Black-box reason extraction does not become independent decision-point evidence. |
| Query parameters | **No direct change**: current response checks consume the resulting recordings and actual bound values. Direct contract entries are not a new request-query assertion language. `tests/test_query_documents.py::test_approved_five_step_example_follows_observed_cursor`, `test_wrong_declared_query_is_observed_by_target_and_cannot_pass_response_checks`. | Response obligations remain useful. **Undecided** how a cross-version bundle establishes equivalent query context; current contract diff alone is not proof that requests from two environments had the same query. No zero-line saving should be advertised as a removed feature. |
| Anonymous/include maps | **No direct change**: expansion and session handling supply effective users to the existing attribution checks. `tests/test_anonymous_documents.py::test_same_pinned_child_maps_each_leaf_to_actual_named_or_anonymous_participant`, `test_anonymous_label_does_not_prove_unauthenticated_target_request`. | **Still necessary** to distinguish anonymous from authenticated observations and retain include provenance. Live session creation is **unnecessary for an offline comparator**, but belongs to shared execution machinery, not these zero direct lines. |
| Headers, including follow-up | Preserves complete captured header pairs and constraints, resolves expected values, reports missing/ambiguous evidence, and hides sensitive values. `tests/test_business_headers.py::test_response_complete_pair_semantics_all_consumers`, `test_contract_missing_recording_or_reference_is_an_error_without_values`, `test_contract_normalizer_exception_with_captured_headers_is_value_free`; `tests/test_header_documents.py::test_document_response_checks_require_complete_single_value_evidence`. Follow-up `73b356f` changes bounded browser mock collection, not these direct files. | **Still necessary** for response-header promises and sensitive evidence. Browser collection mechanics are **unnecessary inside an offline comparator**, but capture must happen somewhere; moving the checker does not eliminate the upstream capture requirement. |
| Complete field comparison | Retains all field constraints, finite complete values and strict recursive semantics; deep copies provider binding data; handles binding/diff failures without turning absence into inequality. `tests/test_response_field_comparison.py::test_contract_retains_both_terms_and_hides_nested_values`, `test_contract_missing_and_null_source_cannot_be_inequality_evidence`, `test_contract_order_duplicate_missing_and_changed_recording_controls`; `tests/test_field_comparison_consumers.py::test_actual_unauthorized_state_change_is_detected_despite_refusal`. | **Still necessary** if comparing complete normalized fields. Raw entire-response comparison remains a different, undelivered promise. **Undecided** how cross-version normalization compatibility would be approved. |
| Member references | Reconstructs actual provider observations and calls shared `prepare_step` for selector-bearing bindings. A plausible downstream recording cannot hide an unavailable or invalid selector at its declared use site. `tests/test_response_member_references.py::test_contract_rejects_unavailable_actual_selection_even_if_only_used_in_path`, `test_contract_selector_use_sites_follow_runtime_rules`. | **Still necessary** for declarations with those dependencies. **Undecided** whether to re-resolve from a bundle or verify a previously recorded resolution proof. Comparing only the final response would drop the dependency promise. |
| Numeric/list length | Retains ordered constraints, resolves actual expected thresholds, validates their domain, and reuses the numeric evaluator for actual fields/lists. `tests/test_response_numeric_length.py::test_runtime_and_contract_share_evidence_classification`, `test_contract_retains_ordered_bounds_and_uses_actual_provider_thresholds`; `tests/test_numeric_check_consumers.py::test_numeric_thresholds_use_actual_prior_service_value_and_contract_recomputes_it`. | **Still necessary** for bound/length promises. Reuse of the shared evaluator avoids a second arithmetic definition. Merely comparing version snapshots would not ensure either version satisfies the declared bound. |

The current contract projection sends no additional product request. It uses backend recordings and the same normalizer, with independent checks of declared constraints and attribution. For example, `tests/test_http_status_consumers.py::test_documents_complete_example_creates_201_and_deletes_empty_204` explicitly checks that backend plus contract makes only two requests. Neither duplicated checks nor cross-version naming creates independent evidence. Conversely, removing a declared-constraint check solely because it reads shared traffic would remove a real check.

## 4. Shared maintenance, excluded from direct line totals

These are integration surfaces, not an additional numerical estimate. Paths below are relative to `refracto/` unless they start with `tests/` or `refracto_browser/`. A shared file may appear in several rows; it is **not counted again** in the direct-contract table. Supporting tests are maintained tests, not a second list of measured mutants.

| Group | Shared reference/evaluator/identity/report surfaces | Supporting tests outside the direct implementation |
| --- | --- | --- |
| Status | `declaration/http_status.py`, loader/vocabulary, `projection/backend.py`, `projection/ui_stepwise.py`: one captured-status rule used by response consumers. | `tests/test_http_status_assertions.py`; `tests/test_http_status_consumers.py`; `tests/demo/test_demo_http_status.py`. |
| Continuation | `projection/continuation.py`, backend/UI loops, `declaration/binding.py`, expansion/model/loader, `normalization.py`, `report.py`, `asyncwait.py`: dependency availability, stop policy, error distinction and failure-retaining aggregation. | `tests/test_failure_continuation.py`; `tests/test_documents_failure_continuation.py`; `tests/demo/test_demo_failure_continuation.py`. |
| Users/sessions | `sessions.py`, `recording.py`, `ports.py`, model/includes/expansion/impact, backend/UI loops, runner/report: account distinction, lazy session generations, evidence ownership and source attribution. | `tests/test_users_sessions_core.py`; `tests/test_documents_users_sessions.py`; `tests/test_ui_users_sessions.py`. |
| Refusal evidence | Existing normalizer fields and status/field evaluators; no new production declaration code or refusal-category vocabulary. | `tests/test_rejection_evidence.py`, including its deliberately weakened-scenario counterexample. |
| Query | `query.py`, binding/expansion/includes/impact/loader/model, ports/normalization, backend/frontend/UI request matching: preserve declared query values, actual encoding and actual cursor dependencies. | `tests/test_query_parameters.py`; `tests/test_query_documents.py`; `tests/browser/test_query_parameters.py`; `tests/demo/test_demo_query.py`. |
| Anonymous/maps | `sessions.py`, model/loader/includes/expansion/impact: explicit participant mapping and real unauthenticated sessions, with existing recording attribution. | `tests/test_anonymous_users_inclusion.py`; `tests/test_anonymous_documents.py`; `tests/test_anonymous_ui_users.py`; `tests/browser/test_anonymous_users.py`. |
| Headers | `headers.py`, binding/includes/expansion/impact/loader/model/vocabulary, ports/normalization, backend/frontend/UI, report: reserved-name rules, actual request matching, complete response capture and sensitivity. Follow-up uses `refracto_browser/_support.py`, outside core/direct contract. | `tests/test_business_headers.py`; `tests/test_header_documents.py`; `tests/browser/test_business_headers.py`; `tests/demo/test_demo_headers.py`. |
| Complete comparison | `declaration/field_comparison.py`, binding/includes/loader/vocabulary, normalization and backend/UI consumers: strict finite data, actual reference resolution, no observation mutation. | `tests/test_response_field_comparison.py`; `tests/test_field_comparison_consumers.py`; the tests distinguish existing normalized-field checks from arbitrary raw-response comparison. |
| Members | Binding/model/loader/includes/expansion/impact: literal one-level key or unique matching member, use-site validity, named-result rewriting and review identity. | `tests/test_response_member_references.py`; `tests/test_member_reference_consumers.py`, including ambiguous selections with no count assertion to mask the guard. |
| Numeric/length | `declaration/numeric_comparison.py`, binding/includes/loader/vocabulary and backend evaluation: strict thresholds, list evidence and shared operator semantics. | `tests/test_response_numeric_length.py`; `tests/test_numeric_check_consumers.py`; `tests/test_numeric_length_inclusion.py`; `tests/browser/test_response_numeric_length.py`. |

The direct review shows repeated additions to the consumer/provider constraint representation and reuse of shared evaluators, not a measured estimate of the effort to redesign contract. There are genuine future choices about evidence bundles and the relationship between declaration conformance and version comparison. This sprint supplies their current costs and guarantees, not a verdict on which future role to adopt.

## 5. Reproduction and limitations

Run from the public repository root. These read-only source-inspection commands were executed successfully for this inventory; zero numstat rows mean zero direct edits, not an omitted capability.

```sh
git rev-parse HEAD
git grep -n status_in 936c50a -- ':!uv.lock'
git diff --numstat 67ce17f 936c50a -- refracto/contract refracto/projection/contract.py
for revision in d2a5ed9 95ba66d b2fdab2 eaca8cb 68af23a 0c14865 b3ddace 73b356f b7996c4 75db346 936c50a; do
  git show --format='commit %h %s' --numstat "$revision" -- refracto/contract refracto/projection/contract.py
done
```

The following equivalent aggregation was executed with exit code 0 and produced `gross [175, 36]` and `status_in lines 33 files 12`:

```sh
uv run python - <<'PY'
import subprocess
commits = 'd2a5ed9 95ba66d b2fdab2 eaca8cb 68af23a 0c14865 b3ddace 73b356f b7996c4 75db346 936c50a'.split()
gross = [0, 0]
for commit in commits:
    rows = subprocess.check_output([
        'git', 'show', '--format=', '--numstat', commit, '--',
        'refracto/contract', 'refracto/projection/contract.py'], text=True).splitlines()
    count = [sum(int(row.split('\t')[i]) for row in rows) for i in (0, 1)]
    gross = [a + b for a, b in zip(gross, count)]
    print(commit, count)
print('gross', gross)
lines = subprocess.check_output([
    'git', 'grep', '-n', 'status_in', '936c50a', '--', ':!uv.lock'], text=True).splitlines()
print('status_in lines', len(lines), 'files', len({line.split(':')[1] for line in lines}))
PY
```

Inspect an individual protected change with `git show <commit> -- refracto/contract refracto/projection/contract.py`, and shared affected files with `git show --format= --name-only <commit>`. The tables intentionally use frozen source lines, so later documentation corrections do not change the historical count.

This group delivers one report only. It changes no YAML, core source, vocabulary, capability, or test expectation; it authorizes no submission. There is no new assertion restriction and no claim that the maintainer's review cost has been measured. Final sprint verification and the independent review of this report are separate delivery gates.
