# Same-tab object navigation: acceptance record

Date: 2026-10-31. Starting main: `f77450f`. Governing
[specification](same-tab-object-navigation.md). Development, independent browser
and consumer audits, final full-suite verification and architect acceptance
passed. Hosted submission and CI remain separately evidenced delivery gates.

## Maintainer summary

- A selected record can open its separate editor in the same tab and origin.
- The actual old-page selection survives replacement; no desired ID is echoed.
- New-page startup requests remain background, not click response evidence.
- The next explicit fill/save/read actions retain the same user session.
- Missing, competing or unsupported navigation proof is an error; YAML is unchanged.

## Feasibility and implementation

Separate Chromium probes established old-document receipt delivery and native
navigation signals before implementation. They also showed why eventPhase or an
initiator stack alone is insufficient: Promise callbacks may retain the former,
and synthetic anchor clicks may inherit the latter. Supported cases are therefore
the pinned anchor's trusted default navigation and synchronous navigation in the
accepted handler, with a separate synchronous invocation scope.

The browser helper retains actual selection and action-work facts on the host.
It validates source default-world unique context, frame, action and owned permit,
then one navigation observation, GET document request, loader and committed
successful HTML response. Pagehide delivery proved unreliable in the real legacy
transport: it is optional corroboration, not the completion gate. Pending/error
transitions and source-context retirement provide that bounded gate instead.

The collector is created lazily at the first scoped click. This preserves the
ordinary browser lifecycle and avoids adding CDP initialization to unrelated
offline tests. A final event-pumping race was reproduced: an invalid receipt
arriving during the last page read could escape the earlier error check. Host
errors are now rechecked at finalization. The retained regressions inject the
collected event at that deterministic boundary during a real browser run; both
transports were red before the fix and green afterward. The independent reviewer
also delivered an actual browser binding at that boundary. A missing receipt channel has
a bounded error path instead of recursive error notification.

No core, port, loader, vocabulary, schema version, include depth or existing YAML
bytes change. Existing target sources, dependencies, CI, principles and branding
remain unchanged. A frozen 130-file public baseline checks these claims.

## Consumers and evidence limits

The [new neutral example](../../examples/ui_object_navigation/README.md) has two
navigation forms with one shared server renderer/editor and the preceding public
records API service. Their three normal/shared-source hashes were frozen before
mapping and test authoring and remain identical. These are bounded synthetic
mechanism checks, not two independent products or measured adoption savings.

Both execute create -> list -> object-specific navigation -> fill -> save ->
explicit API read, with one user session, one context and one close. The selected
record is not initially first; decoy records remain unchanged. The startup GET
is diagnostic and click traffic is empty. Subsequent save traffic has its own
action identity. Destination identity/name checks run before modification.

Explicit faulty variants open the wrong editor or save to the wrong object.
The former reaches a UI FAILED check; the latter produces request ERROR and
retains its real side effect. Neither is repaired. Declaring the startup request
as the click's expected API also fails despite the actual network response.
An API read is not separate database evidence. Browser signals are consistency
evidence, not hostile-page attestation or independent server instrumentation.

## Independent audit

The consumer reviewer independently ran all nine consumer tests and 51
documentation/litmus checks. Four extra inline Chromium probes covered startup
navigation to another object and duplicate rendered editors, each for both
navigation forms. All blocked saving, sent no PATCH and closed once. No normal
source or implementation was changed by that reviewer.

The receipt reviewer passed a retained 154-test focused suite and 12 final
changed-boundary checks, plus 32 meaningful independent real-browser controls
and 11 source/ledger cases. These exercised actual late pending/error work,
Promise/await/timer and synthetic navigation, competing requests, and navigation
during rendered-state collection. Its final-read probe independently sent an
actual wrong-source browser binding during the last page read; both transports
rejected it and closed. Two
pagehide probes did not execute their product handler on the tested browser;
they are explicitly not evidence of teardown-handler coverage. Retained tests
and the host ledger, not an unexecuted callback, support the completion boundary.
The final independent verdict is PASS after the race fix; full-suite and hosted
CI gates remain separate. Extra exploratory probes were inline or temporary,
not retained public benchmark files and not a coverage percentage.

## Reproducible verification

Commands run from the public repository. Counts from separate runs are not
additive numbers of unique checks.

| Command or check | Actual result |
| --- | --- |
| `uv run --locked --no-sync refracto validate examples/ui_object_navigation/scenario.yaml` | Exit 0; six steps, three requests, three UI and nine response checks. |
| `uv run --locked --no-sync python -m examples.ui_object_navigation.run` | Exit 0; anchor and synchronous-location live e2e PASSED, no degradation. |
| Navigation browser development tests | 60 passed; two added finalization regressions separately passed after the reproduced race fix. |
| Existing scoped-click browser tests | 66 passed. |
| Browser lifecycle and user binding tests | 19 passed after lazy collector initialization. |
| Independent consumer tests | 9 passed. |
| Independent browser focused / final changed-boundary checks | 154 passed / 12 passed. |
| Documentation and core litmus tests | 51 passed. |
| Dev-only Python 3.11 / 3.12 offline suites | 4241 passed each; one optional Demo collection skip because httpx is absent. |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q` | 5103 passed, no skips, one existing Starlette/httpx deprecation warning; exit 0 in 729.56 seconds. |
| `uv lock --check`, repository hygiene, `git diff --check`, cached diff check | Passed. Staged hygiene is repeated before committing the accepted files. |

An earlier full run was deliberately interrupted before completion when the
finalization race was discovered; it is not counted as a passing suite. The
final suite uses the corrected implementation. Information-source review passed:
only existing public code, official browser behavior and new neutral synthetic
fixtures informed these changes. No private product details, sources or evidence
were read or copied. The 130-file unchanged check passed after verification.

## Remaining boundaries

Only exact same-origin, same-tab successful HTML GET navigation is supported in
this slice. Deferred navigation, redirects, forms, downloads, other tabs/frames
and unfinished old-page action work fail visibly. Correct selection still needs
destination checks; the helper does not infer business identity from a URL.
Existing explicit unscoped actions retain their prior contract. No product was
modified, no private workspace was accessed, and object absence/Flow remain
deferred. No new YAML or broader compatibility claim is authorized here.
