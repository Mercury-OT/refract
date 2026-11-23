# Mattermost API adoption pilot

This is a finite, opt-in example against an unmodified public application, not a
general Mattermost integration package or an addition to Refract core.
See the [approved scope](../../docs/tasks/mattermost-api-pilot.md).

The six externally reviewed declarations cover a private channel, message
creation/edit/deletion, nonmember rejection and same-session permission changes.
Run the exact reviewed files: the executable inventory in `run.py` checks seven
YAML hashes and six include pins before any business request. The approved
review originals are not rewritten or translated by this example. Source hashes
and strict per-run outcomes accompany the local evidence.

## Local inputs and execution

Provide an external directory containing the six named Scenario files and
`shared/prepare_private_channel.yaml`, plus their matching include sidecars.
The approval JSON contains a `scenarios` array of `{path, sha256}` entries matching
`APPROVED_INPUTS` in `run.py`. Those hashes identify reviewed bytes; they do not
establish who approved them. A separate maintainer approval remains necessary.

Set `PILOT_DIR` to an external local evidence directory, not this repository.
The commands below require Docker and the existing Python development environment.
The environment script uses pinned Mattermost Team Edition images for
`linux/amd64` and a pinned PostgreSQL 16.14 image for `linux/arm64`. This particular
host setup is a development pilot, not a portable production deployment recipe.
On an ARM host the application uses emulation; measured timings are not production
performance estimates. Image retrieval requires network access and disk space.

```bash
python -B -m examples.mattermost_api.environment start --directory "$PILOT_DIR/environment"
python -B -m examples.mattermost_api.run \
  --scenarios-dir "$PILOT_DIR/reviewed-scenarios" \
  --approval "$PILOT_DIR/approval.json" \
  --accounts "$PILOT_DIR/environment/accounts.json" \
  --base-url "$PILOT_BASE_URL" --output-dir "$PILOT_DIR/runs" \
  --version 11.7.15 --repetitions 3
```

Use the loopback URL returned by `environment start` as `PILOT_BASE_URL`.
The host creates the bootstrap administrator first and then two ordinary users.
The adapter account JSON has exactly `owner` and `peer`, each containing `id`,
`login_id` and `password`. Generated credentials/configuration stay local with
restricted file permissions. Teams, channels and messages are created only by
the visible Scenario steps. Business requests use ordinary accounts.

After retaining baseline evidence, upgrade the application on the same database,
then repeat the command with `--version 11.11.4`. Keep the declarations and adapter
unchanged. Do not overwrite earlier result directories.

```bash
python -B -m examples.mattermost_api.environment upgrade --directory "$PILOT_DIR/environment"
```

The runner checks the actual server version, runs backend plus contract, and
exits zero only for a complete strict pass. Contract reuses backend observations;
it is not an independent witness or another write execution. There are no write
retries, automatic reauthentication, redirect following or expectation-derived
response fields. PostList maps, order and extra parent entries are preserved;
malformed observations are not replaced by empty values.

## Comparison and counterexamples

`plain_http.py` is an explicitly invoked pytest file for S2 and S4, three repeats
each. It shares mechanical HTTP transport only; its business assertions are
written independently without the Refract loader, normalizer or evaluators.
An external JSON file supplies `base_url`, `accounts`, `scenarios_dir`,
`output_dir` and `version`. Run:

```bash
MATTERMOST_PLAIN_CONFIG="$PILOT_DIR/plain-config.json" \
  python -B -m pytest examples/mattermost_api/plain_http.py
python -B -m examples.mattermost_api.controls \
  --suite-dir "$PILOT_SUITE" --scenarios-dir "$PILOT_DIR/reviewed-scenarios" \
  --approval "$PILOT_DIR/approval.json" --output-dir "$PILOT_DIR/controls"
```

The controls change copies of actual response observations, never the product or
approved declarations. Normal neighbors must pass and each mutation must reach
its named check. These are offline response-assertion tests, not new network
runs, real product defects, or a product-quality percentage.

## Evidence and limits

Local artifacts retain source/input hashes, actual version, safe HTTP observations,
session identities, native reports, timings and failed attempts. Credential and
cookie headers and authentication bodies are explicitly excluded. Known reflected
credentials cause export refusal. These omissions are not evidence of header
absence, and the files are not automatically safe to publish. Do not serialize
authenticator objects or upload the external evidence directory.

Record setup and investigation separately from business mapping, test harness and
machine waiting. Report source lines by responsibility. Human active review time
and unavailable AI token measurements remain unknown. Runtime comparisons share
the same assertions and observation channels, but are not randomized human-cost
or production-performance studies. A version change requiring no adapter edits
does not establish difficult-change maintenance savings.

The original API pilot's page gate used the browser helper available at that
time. It recorded a compatibility blocker before any UI business scenario ran.

### Separate live channel-message pilot

The [page Scenario](channel_message.yaml) uses the live e2e projection. Run it
only in a disposable local 11.11.4 deployment. Each execution may create a real
post even if evidence collection fails. Preserve each attempt separately.

Before running, prepare an ordinary member of a private channel and obtain that
member's browser storage state through the application's own login. Verify the
authenticated identity, channel type, membership, and channel ID/path against
the application independently of the message to be sent. Store a private JSON
fixture outside the checkout with `base_url`, `server_version`, `channel_path`,
`channel_id`, `member_id`, and the Playwright `storage_state` object.
The latter contains credentials. Keep fixture and result directories local.

```sh
python -B -m examples.mattermost_api.channel_message \
  --fixture "$PAGE_FIXTURE" --output-dir "$NEW_RUN_DIR"
```

The runner binds the three marked environment slots. To use an independently
retained review copy, pass `--scenario` with its path. Check the native step
results and the separate business verdict in the run output. A socket event or
an API read alone cannot verify what the member saw after reopening the page.

For the [same-text control](channel_message_same_text.yaml), create a separate
older post with the exact text `Friday delivery` using normal product controls.
Verify its server ID independently and add it to the local fixture as
`old_post_id` before the run. Complete the normal onboarding interface for the
ordinary member if it intercepts the send button. Invoke the same command with
`--scenario examples/mattermost_api/channel_message_same_text.yaml` and an
unused output directory. The seeded ID stays in the runner's evidence checks;
the new post ID always comes from the response to the observed send action.

Both profiles use identical steps and assertions. On this release, a positively
identified grouped membership activity has a consistent system card, body and
permalink. The page observation records the group count separately from the
individual posts. Unidentified rows prevent a verified reread. The same-text
control also requires the older post on both pages, the new ID absent on entry,
and precisely one new row with the correct text after reentry.

After independent verification, remove only the dedicated labeled resources:

```bash
python -B -m examples.mattermost_api.environment cleanup --directory "$PILOT_DIR/environment"
```

The command retains local evidence and downloaded image cache. It does not manage
other containers, networks or volumes. Do not use it for an existing deployment.
