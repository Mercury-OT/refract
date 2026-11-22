# Private-channel message: live pilot evidence

Independent audit and architect acceptance passed for the evidence delivery on
2026-11-22. The send-and-reread business scenario remains unverified.

Scope: the [approved four steps](mattermost-channel-message.md) on Mattermost
Team Edition 11.11.4, using live e2e only. No target, core or browser-helper
changes. The fixture bound the ordinary member and private channel from separate
environment records before the business run. The public template and the local
review copy have the same actions and assertions.

| Step | Native step | What was established |
| --- | --- | --- |
| Enter channel | PASSED | New document at the expected channel path, composer visible. |
| Enter message | PASSED | The composer displayed the full run-specific input. |
| Click send | ERROR | Browser action timed out. No associated post request or server-assigned message ID was collected. Sending is unverified. |
| Reopen and read | BLOCKED | The stop rule and missing send evidence prevented rereading. Message identity, count, and visible body on reentry are unverified. |

The native run status was FAILED and the command exited 1. A separate diagnostic
run, with the same declaration and ordinary browser actions, located the enabled
send button. Chromium repeatedly reported that the application's first-use
onboarding overlay intercepted pointer events. The click timed out after
30.06 seconds. The observer saw no post response. A separate read-only API
inspection of the bounded channel page found no matching text after the formal
attempt. This inspection cannot establish action attribution or a UI verdict.

The pilot did not dismiss the overlay, force a click, send via API, or change
the account's preferences. Establishing what a returning member can do requires
a separately reviewed starting state or a visible step for handling onboarding.
A rendered combined membership-activity row also lacks a single post identity.
The mapper preserves such a row as anonymous. The final page checks were never
reached, so the effect of that row on a successful send and reread is unknown.

The first engineering run was retained with a failed source-integrity check:
document identity diagnostics were being added while it ran. It is excluded
from final evidence. A fresh execution with frozen sources took 31.50 seconds
including interpreter startup and exit, and reproduced the four statuses above.
The independent rerun took 31.43 seconds, exited 1 and reproduced them again.
It used identical reviewed and bound declarations, verified all 66 runtime
source hashes and generated a different message. Its Chromium log recorded 55
pointer interceptions by the onboarding overlay. Each run retained its own output.

The focused suite passed 54 tests. Real Chromium controls on synthetic pages
checked same text under a different ID, duplicate IDs, missing or conflicting
row identity, stale text, and incomplete lists. These controls test the mapping
and evaluator separately from the unexecuted target reread. The dev-only
regression completed with exit 0 over 5,749 collected tests.

## Cost observations

- The maintainer reviewed one four-step declaration, asked two clarification
  questions and approved it. One comment was clarified. No action or assertion
  changed. Active reading time and AI token use were not measured.
- The elapsed interval from initial fixture preparation to verified independent
  binding was 107.60 seconds, including investigation and idle time. Measured
  command intervals totaled 13.29 seconds. Two setup attempts failed while
  preparing the team, before a business action. The successful setup kept
  provisioning credentials separate from the ordinary member's browser session.
- The page mapping, runner, template, and offline tests are counted separately.
  Physical lines were 163, 237, 72 and 83 respectively. Excluding blanks and
  full-line comments, the counts were 140, 204, 62 and 70 (docstrings included).
  These are incremental files; the existing browser helper and API pilot
  components were reused. The wall interval from the first measured setup
  checkpoint to completion of the independent business run was 10 min 30 s.
  It includes concurrent implementation and automated waiting, and excludes the
  preceding review conversation and subsequent release. Neither wall time nor
  source lines are an estimate of human labor or evidence of maintenance savings.

Raw attempts, diagnostic observations, exact fixture values and authentication
material remain local. The [public runner](../../examples/mattermost_api/README.md#separate-live-channel-message-pilot)
uses an exclusive output directory for each invocation.
