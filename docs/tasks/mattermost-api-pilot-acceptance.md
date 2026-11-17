# Mattermost API pilot: delivery and evidence

Status: independent audit and architect acceptance passed on 2026-11-17.
This record concerns the finite
[approved pilot](mattermost-api-pilot.md), not general product certification.
Starting public main: `e76848848533ce331b68dca66de291d101ea2c02`.
The maintainer accepted the delivery and separately authorized task-branch
submission and merge on 2026-11-17, subject to green PR and post-merge checks.
Raw execution evidence remains local and is excluded from publication.
Submission preflight added trailing slashes to three synthetic test URLs to
satisfy the existing tracked-file hygiene rule. Test intent, runtime sources and
reviewed inputs were unchanged; the original accepted test source was retained
locally and the focused checks were repeated. The historical cost snapshot
identifies the original test bytes, not this submission-only spelling correction.

## Maintainer summary

- Six approved API scenarios ran on two unmodified application versions.
- All 36 planned executions and 12 independent audit executions passed strictly.
- Ordinary HTTP comparison cases also passed; this does not establish a cost advantage.
- Normal browser access worked, but the unchanged Refract page helper was blocked.
- Core, declaration syntax and approved assertions stayed unchanged; download work stays paused.

## What actually ran

The target was Mattermost Team Edition 11.7.15, followed by 11.11.4 on the same
retained database. The application used pinned `linux/amd64` images under
emulation; PostgreSQL 16.14 used a pinned `linux/arm64` image. This was a disposable
local development installation, not a production performance test. The
[environment utility](../../examples/mattermost_api/environment.py) records image
digests and creates dedicated labeled resources. Only the application port was
published, on loopback. The dedicated bridge allowed outbound connectivity; this
was not an air-gapped environment.

The bootstrap account was an administrator. Both business accounts were distinct
ordinary users. The host created accounts and environment configuration only;
approved steps created every business team, channel and message. The six Scenario
files, shared setup and include pins remained byte-for-byte identical throughout
the version comparison. Their approval hashes are enforced by the
[runner](../../examples/mattermost_api/run.py).

| Case | Approved obligation | 11.7.15 | 11.11.4 |
| --- | --- | --- | --- |
| S1 | Create, read, rename and reread a private channel with retained identity. | 3/3 PASSED | 3/3 PASSED |
| S2 | Create and read a message with the declared content, author and channel. | 3/3 PASSED | 3/3 PASSED |
| S3 | Edit an own message and read the changed content with retained identity. | 3/3 PASSED | 3/3 PASSED |
| S4 | A valid member post succeeds; a same-team nonmember post is rejected; the observed page stays unchanged. | 3/3 PASSED | 3/3 PASSED |
| S5 | The same peer session sees channel access denied, granted, then revoked; authentication and owner access remain valid. | 3/3 PASSED | 3/3 PASSED |
| S6 | Delete an own message; an ordinary ID read is not found and the observed page returns to its earlier snapshot. | 3/3 PASSED | 3/3 PASSED |
| S7/S8 | Page integration gate, before any business UI Scenario. | BLOCKED; NOT_EXECUTED | BLOCKED; NOT_EXECUTED |

Each API version panel made 168 HTTP exchanges including authentication and
produced 636 native checks across backend and contract. These counts include
framework checks and are not 636 independent business obligations. Contract
consumed the same backend recordings and normalizer; it did not provide an
independent witness or execute another write.

The independent audit additionally ran each of the six cases once on each
version: 12/12 strict passes, separate from the planned three repetitions. It
also read actual HTTP observations without the Refract evaluator and checked the
business facts, session continuity and output hashes. For S5 the peer's actual
channel statuses were 403, 200, 403, followed by a successful identity read;
one peer login served that sequence.

S4 and S6 inspect a bounded normal message page. They do not prove absence from
all storage, physical deletion, database invariants, or broader authorization
correctness. No genuine product defect was found in this finite panel.

## Ordinary-test comparison and counterexamples

S2 and S4 were independently expressed as pytest plus HTTP, sharing mechanical
transport only. They did not use the Refract loader, normalizer or evaluators.
Both versions passed all six comparison executions each, for 12/12 total.

The evidence comparison verified the same ordered business checks and request
method, path, query and body after renaming generated identities only in the
comparison copy. S2 had 26 business checks, five business requests and one login;
S4 had 38 checks, nine business requests and two logins. The original recordings
were preserved. Trace and contract checks were not credited as extra product
observations.

Five labeled variants across four fault classes were applied to copies of real
responses on each version. Every normal baseline passed first; every injected
variant reached its specified failing assertion. There were no target requests
or target modifications during this control exercise.

| Artificial change | Check that detected it |
| --- | --- |
| Edited message read returns its old text. | Expected new text and inequality with the prior text. |
| Expected permission rejection is instead login failure. | Exact expected status. |
| Expected permission rejection is instead request validation failure. | Exact status and native error identifier. |
| Removed peer can still read the channel. | Expected denial status and native error identifier. |
| Deleted message remains readable. | Expected not-found status and native error identifier. |

This is 5/5 selected variants detected per version, not a product-quality
percentage, live fault injection, or proof that all bad mappings are detectable.

## Measured costs

Local `cost/summary.json` is recalculated from hashed execution artifacts by
`cost/recalculate.py`; its `--check` mode reproduced the same summary. Counts keep
the 36 formal native executions, 12 additional independent native executions,
12 ordinary-test executions and offline controls separate.

| Responsibility | Physical source lines | Nonblank, noncomment lines |
| --- | ---: | ---: |
| Adapter, HTTP transport and export protection | 259 | 224 |
| Frozen-input runner and evidence writing | 214 | 188 |
| Disposable environment lifecycle | 223 | 191 |
| Ordinary pytest comparison | 277 | 246 |
| Offline response controls | 200 | 178 |
| Offline example tests | 312 | 258 |
| Seven reviewed YAML files, including shared setup | 599 | 503 |

The line count excludes blank lines and full-line comments in the right column,
but retains docstrings. It is not a semantic complexity or labor measure. The
259-line adapter includes transport and export mechanics, not just product field
mapping. The other harness work is reported separately rather than hidden in an
adapter-only adoption number. The comparison supports two cases; the Refract
runner supports six, so their file sizes are not a like-for-like productivity
comparison.

| Measured runtime | 11.7.15 | 11.11.4 |
| --- | ---: | ---: |
| Sum of 18 native execution durations | 11.203 s | 11.533 s |
| S2 native / ordinary median, three runs each | 0.485 / 0.434 s | 0.485 / 0.417 s |
| S4 native / ordinary median, three runs each | 0.911 / 0.825 s | 0.917 / 0.788 s |

Native durations include per-run input/source guards and report preparation;
ordinary durations use their own recorded timing boundary. Neither includes
image download or initial deployment. These small, sequential, warm-environment
samples on an emulated application are descriptive, not a randomized performance
or human-efficiency comparison. No speed advantage is claimed.

Three human approval batches covered six top-level scenarios and shared setup.
No approved assertion or input byte changed during integration. No business API
wiring repair was needed after source freeze, and no adapter edit was required
for the version change. The selected APIs may simply have remained stable;
difficult-change maintenance savings remain unverified.

Two host wiring issues were retained: initial internal-network publication did
not expose the application to the host, and the first UI authentication probe
did not receive browser cookies. The former was corrected with a dedicated
bridge and loopback-only publication; the latter is described below. Baseline
application readiness took 210.862 seconds including the network investigation;
comparison readiness took 1.040 seconds. These are readiness timers, not total
installation or active engineering time. Ordinary-test source/version and exit
guards were also corrected during independent review before the formal panel.

Human active authoring, review, setup and diagnosis time, AI token use, image
download duration and total installation effort were not reliably instrumented
and remain unknown. Approval counts and chat elapsed time do not substitute for
those measurements. The pilot measures code, observed runtime and unchanged
version adaptation; it does not yet establish lower end-to-end adoption cost.

## Page gate and retained failures

An ordinary browser, with cookies actually issued by the application, verified
the expected account and opened the actual channel on both versions. The document
returned 200, an application WebSocket was observed, and no uncaught page error
was recorded. With the unchanged Refract browser helper, opening the login page
reported `policy_denied`; opening the authenticated channel reported
`evidence_invalid`. Contexts were explicitly closed.

The first baseline attempt had omitted the application's browser-login request
header, received no browser cookies and returned to login. That failed host
wiring attempt remains recorded. One wiring correction used the official login
convention and verified identity using cookies alone. No application or helper
feature was disabled or modified. The same corrected probe was used on the
comparison version. One baseline helper action also reported cleanup failure;
explicit context close still completed, and the comparison probe did not report
that condition.

WebSocket use was independently observed and is outside the helper's current
supported path. The generic helper error does not establish WebSocket as its
only cause. The accepted conclusion is a reproducible integration blocker;
neither UI business pass nor product failure is claimed. Three probe attempts
used about 34.87 seconds of measured machine execution, excluding preparation
and waiting. The bounded investigation stopped there.

## Provenance limits

Actual server versions were verified from `X-Version-Id` before both native and
ordinary-test execution. Image digests were pinned; native panels checked
core and example Python source hashes plus approved input hashes before each run
and after the panel. Those sources and inputs were identical between versions.

One planned provenance measure was incomplete: the original formal panels did
not have a separate pre-run hash checkpoint for all generated environment files.
The pinned images, hashed provisioning source, recorded configuration, observed
policy and roles, and actual server-version records are available. Final hashes
protect retained files going forward; they are not retroactive freeze proof.
A separate environment checkpoint preceded the independent comparison-version
rerun and remained unchanged afterwards. This limits the original environment
provenance claim; no configuration drift was observed.

The host readiness record's optional version field is empty because that utility
looked for a different header name. Native suite `server.json` files and
ordinary-test result records, which use `X-Version-Id`, are the authoritative
observed-version evidence.

Local artifacts retain failures, actual observations, strict native results,
source/input identities and timings. Credential/cookie headers and authentication
bodies are explicitly omitted from exported observations; those omissions are
not evidence of header absence. Raw artifacts remain outside the public repository
and are not automatically approved for publication.

## Checks and remaining limits

- Focused example tests plus core boundary litmus: 42 passed.
- Lock check, repository hygiene, diff checks and core/adapter/dependency/CI
  unchanged checks passed.
- Target execution was opt-in. The existing full browser/core suite was not
  rerun for this example-only change; no existing runtime code was modified.
- Independent audit checked actual outcomes, ordinary-test parity, artificial
  controls, credentials, source/input identity and the page blocker.
- Dedicated containers, network and database volume were removed after all
  target-dependent checks. Exact-name and ownership-label inventories confirmed
  no pilot resources remained. Evidence and downloaded image cache were retained.

At the acceptance gate, no staging, commit, push or pull request had been
performed. No private workspace was accessed. The finite pilot establishes
existing API applicability and a concrete
page-access limitation. It does not establish reduced human review effort,
general maintenance savings, production readiness, or a need to add new syntax.

Architect acceptance retains the documented environment-checkpoint limitation;
it does not upgrade that incomplete provenance to a pre-run freeze. The audited
implementation scope is the example package, its offline tests, the task and
acceptance records, and the roadmap entry. No unresolved blocking audit finding
remains. The maintainer's subsequent review and submission authorization are
separate gates; actual publication, hosted checks and cleanup belong to the
associated PR and main history.
