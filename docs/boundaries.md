# Declaration boundaries

The tables below list rejected declarations, not instructions for writing passing
tests. Each table fragment has a valid surrounding Scenario in the
[executable sentinel](../tests/test_stabilization_boundaries.py). The linked tests
establish the existing loader boundary; no new rejection rule is added here.

### Composition commitment (governance status)

Under the [R1 revision of 2026-10-27](roadmap.md#maintainer-decision-r1-revision-2026-10-27),
the committed `concat` scope is parameter-level composition of string literals
and references to string-valued parameters. Operand content is unchanged; nested
concat, implicit conversion, and templates remain disallowed.

Other currently accepted composition forms are outside that commitment. In
particular, step-level prior-response operands (`from_step` with `response_field`)
and concat in assertion-value positions are **frozen: retention is not promised**.
Requests and assertions may still reference a committed composed parameter using
ordinary `from_parameter`; freezing direct assertion-value concat does not freeze
such parameter references.
These are governance limits, **not loader rejections**. The existing implementation
and runtime behavior remain unchanged; further support requires concrete use
cases and separate review. The rejection catalog below does not claim to reject
these frozen forms.

## Top level

| ID | Cannot write | Rejection reason | Existing test |
| --- | --- | --- | --- |
| T01 | `users: [{name: owner, role: member}]` | Participants are names, not role records. | [test_users_required_actor_rejected_and_no_role_metadata](../tests/test_users_sessions_core.py) |
| T02 | `users: [owner, peer]` | Multiple participants require a user on every ordinary step; this context omits it. | [test_multiuser_requires_user_on_every_step](../tests/test_users_sessions_core.py) |

## Step, including an include call

| ID | Cannot write | Rejection reason | Existing test |
| --- | --- | --- | --- |
| S01 | `on_failure: continue` | Omission is the default; only explicit `stop` is accepted. | [test_only_explicit_literal_stop_is_allowed](../tests/test_failure_continuation.py) |
| S02 | `on_failure: {from_parameter: policy}` | The stopping policy cannot be dynamic. | [test_only_explicit_literal_stop_is_allowed](../tests/test_failure_continuation.py) |
| S03 | `session: reuse` | Reuse is the default; only explicit `new` is accepted. | [test_only_explicit_new_session](../tests/test_users_sessions_core.py) |
| S04 | `on_failure: stop` | An include call cannot override the child's stopping policy. | [test_include_call_cannot_override_policy](../tests/test_failure_continuation.py) |
| S05 | `with_users: {creator: owner}` | The two-user child also requires its reader mapping. | [test_malformed_or_colliding_user_mappings_rejected](../tests/test_anonymous_users_inclusion.py) |
| S06 | `with_users: {creator: owner, reader: owner}` | Distinct child users cannot map to one participant. | [test_malformed_or_colliding_user_mappings_rejected](../tests/test_anonymous_users_inclusion.py) |
| S07 | `with_users: {creator: owner, anonymous: peer}` | A child's anonymous participant cannot become a named user. | [test_explicit_child_anonymous_cannot_be_upgraded_in_full_mapping](../tests/test_anonymous_users_inclusion.py) |

## Do: request fields

| ID | Cannot write | Rejection reason | Existing test |
| --- | --- | --- | --- |
| D01 | `query: {q: null}` | Query values cannot be null. | [test_loader_rejects_invalid_query](../tests/test_query_parameters.py) |
| D02 | `query: {q: [1]}` | Query values cannot be containers. | [test_loader_rejects_invalid_query](../tests/test_query_parameters.py) |
| D03 | `query: {"": x}` | Query keys cannot be empty. | [test_loader_rejects_invalid_query](../tests/test_query_parameters.py) |
| D04 | `headers: {Authorization: x}` | Authentication headers belong to session handling. | [test_credentials_transport_and_reserved_prefixes_rejected](../tests/test_business_headers.py) |
| D05 | `headers: {X-Key: x, x-key: x}` | Header names cannot collide after case folding. | [test_invalid_header_maps_are_rejected_without_values](../tests/test_business_headers.py) |
| D06 | `headers: {X-Key: 1}` | Business header values must be strings, without coercion. | [test_invalid_header_maps_are_rejected_without_values](../tests/test_business_headers.py) |

## Expect: response checks

| ID | Cannot write | Rejection reason | Existing test |
| --- | --- | --- | --- |
| E01 | `[{check: status_equals, value: "201"}]` | HTTP status must be a literal integer, not a string. | [test_status_equals_rejects_nonliteral_or_invalid_values](../tests/test_http_status_assertions.py) |
| E02 | `[{check: status_in, values: []}]` | An allowed status set cannot be empty. | [test_status_in_rejects_invalid_sets](../tests/test_http_status_assertions.py) |
| E03 | `[{check: status_equals, value: 201}, {check: status_in, values: [200, 201]}]` | One step cannot declare both status forms. | [test_missing_extra_and_duplicate_constraints_rejected](../tests/test_http_status_assertions.py) |
| E04 | `[{check: field_equals, field: error_code}]` | Field equality requires an expected value, including for a refusal reason. | [test_comparison_requires_both_parameters](../tests/test_response_field_comparison.py) |
| E05 | `[{check: field_equals, field: content, value: .nan}]` | Compared data must be finite JSON-like values. | [test_invalid_declared_data_rejected](../tests/test_response_field_comparison.py) |
| E06 | `[{check: field_equals, field: content, value: {}}, {check: field_absent, field: content}]` | Equality and absence cannot require opposite presence states. | [test_duplicate_and_presence_conflicts_rejected](../tests/test_response_field_comparison.py) |
| E07 | `[{check: field_compare, field: returned, op: "!=", value: 1}]` | Numeric comparison does not declare this operator. | [test_invalid_shape_field_and_operator_rejected](../tests/test_response_numeric_length.py) |
| E08 | `[{check: field_compare, field: returned, op: ">=", value: true}]` | A boolean is not a numeric bound. | [test_invalid_literals_and_parameter_defaults_rejected](../tests/test_response_numeric_length.py) |
| E09 | `[{check: collection_length, field: records, op: "<=", value: 1.0}]` | A length bound must be a nonnegative integer, not a float. | [test_invalid_literals_and_parameter_defaults_rejected](../tests/test_response_numeric_length.py) |

## Prior-response references

| ID | Cannot write | Rejection reason | Existing test |
| --- | --- | --- | --- |
| R01 | `{from_step: source, response_field: record, key: id, matching: {code: B}, member_field: id}` | Dictionary and list selectors cannot be combined. | [test_malformed_shapes_and_sources_are_rejected](../tests/test_response_member_references.py) |
| R02 | `{from_step: source, response_field: record, matching: {code: B}}` | A list selector also needs the member field to read. | [test_malformed_shapes_and_sources_are_rejected](../tests/test_response_member_references.py) |
| R03 | `{from_step: source, response_field: record, key: {from_parameter: key}}` | A selected dictionary key must be a literal string. | [test_literal_nonblank_selector_names_required](../tests/test_response_member_references.py) |

The refusal-evidence slice shares E01, E03 and E04; it added no declaration syntax.
A valid declaration can still fail at runtime: [invalid session](../tests/test_rejection_evidence.py),
[input validation instead of authorization](../tests/test_rejection_evidence.py), and
[missing or confused refusal reason](../tests/test_rejection_evidence.py) are evidence failures, not loader rejections.
