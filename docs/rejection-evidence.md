# Checking the reason for a rejected request

The maintained [owner-access example](../examples/documents/scenarios/owner_access.yaml)
uses existing format-1 response checks. It creates a document, verifies that its
creator can read it, verifies the peer's current session, and asks that peer to
read the same observed document ID. The peer must receive both status 403 and the
actual error code `owner_required`. Preparation steps use `on_failure: stop` so
a broken prerequisite cannot count as a successful permission test.

`owner_required` belongs to this synthetic Documents service, not a Refract
rejection vocabulary. The [normalizer](../adapters/documents/normalizer.py)
extracts `error_code` from the response's `fault.code`. It does not infer the
reason from 403. A real integration must preserve its own response evidence and
review the normalization rules; it must not invent the expected reason.

## What the example distinguishes

| Actual observation | Meaning for this example |
| --- | --- |
| 403 with `owner_required` | The declared response checks pass. |
| 401 with `session_required` | The session was not accepted; this is not evidence of an ownership refusal. |
| 400 with `title_required` during creation | Input validation rejected the prerequisite; later steps are blocked. |
| 403 with a missing, malformed, or different reason | The reason check fails even though status and normalized failure match. |

These status/code combinations are the example service's contract, not a
universal HTTP classification. `session_required` does not distinguish expiry,
revocation, and never having logged in. A successful profile request proves only
that request's session worked. If it stops working before the document request,
the latter's actual 401 must remain visible. Refract does not automatically
authenticate again after a 401/403.

## Evidence limits and reporting

The response reports the target's stated reason. This is not independent proof
that its internal ownership decision executed correctly. An incorrect or
malicious target could return that code for a different reason. Both users also
remain dependent on truthful adapter account bindings. The positive read checks
reduce ambiguity but do not establish all security properties.

Use `report.status == "PASSED"` as the strict gate. A missing required reason
produces a failed assertion and a `FAILED` report. Explain this as "the required
ownership-refusal evidence was not obtained"; do not silently pass it or conclude
that a particular access-control vulnerability has been proved. There is no new
native `UNVERIFIED` status. A transport or adapter exception instead produces a
step `ERROR`, a failed aggregate, and subsequent `BLOCKED` steps.

If internal evidence is required, declare suitable `backend_state` checks and
connect a `StateProbe`. Missing probe capability is visible as degradation;
successfully reading no required record fails its assertion; a probe exception
is an execution error. These are different outcomes. Missing telemetry alone
does not prove that a decision was not made. Trace association is not independent
verification. Existing `span_attr` checks independently search same-named spans:
several passing attributes do not prove that one shared event contains them all.
This example has no telemetry and makes no internal-decision claim.

Contract reads the backend's recordings with the same normalizer. It can detect
response-contract mismatches without additional requests, but is not an
independent witness. The explicit-API e2e path also executes no browser here;
its passing result is not UI evidence. Full execution success, complete business
acceptance, and a release decision remain distinct claims.

Default report representations hide sensitive details and recordings. This is
not permission to publish raw responses, session tokens, `localize()` details,
or generic `asdict(report)` output. Keep detailed artifacts at the appropriate
confidentiality level.

## Reproduce the bounded controls

From the repository root:

```sh
uv run refracto validate examples/documents/scenarios/owner_access.yaml
uv run pytest tests/test_rejection_evidence.py
```

The tests run the real loader, runner, transport, normalizer, and offline
Documents target with backend plus contract and with explicit-API e2e. They
invalidate a real session before and after the profile control, send an invalid
creation value through the target's real validation, and change only the final
403 reason in bounded test subclasses. Each final-response control verifies
that all prerequisites passed and that the mutation was actually reached.

A temporary test-only copy omitting just the reason check passes an ambiguous
403 that the maintained declaration rejects. This demonstrates the value of the
stronger assertion, not superiority over another framework or a measured
security detection rate. No production declaration is weakened, and none of
the target responses is generated from the assertions. Additional controls
cover actual execution errors, missing state capability, unavailable records,
and default-representation confidentiality. No network, browser, real product,
new taxonomy, or core behavior is introduced by these tests.
