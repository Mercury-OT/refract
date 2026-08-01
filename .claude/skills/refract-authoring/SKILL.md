---
name: refract-authoring
description: Use when turning a human-authored `examples/authoring/cases/*.case.yaml` file into a frozen `scenarios/*.yaml` artifact for Refracto. Capture a real request against the running demo product, map the natural-language oracle to the bounded vocabulary, present the oracle-to-assertion mapping for human approval, then freeze the scenario and append a generation-log entry.
---

# refract-authoring: case -> frozen scenario

The normative source is `examples/authoring/rules.md`. This skill is the
executable checklist derived from it. Do not modify `refracto/` while running
this workflow.

## Preconditions

* Target case: `examples/authoring/cases/<name>.case.yaml`
* Runnable product: the repository demo app can be started locally

## Checklist

1. Read the case and confirm the required fields are present.
2. Start the demo app on a free local port.
3. Capture first: perform one real request that matches the case intent and
   record the real request, response envelope, and spans.
4. Map each oracle bullet to bounded vocabulary terms from
   `refracto/declaration/vocabulary.py`. If any bullet cannot be mapped,
   stop and report it.
5. Present `oracle -> assertion -> capture evidence` for human review.
6. After approval, freeze the scenario under `scenarios/demo_<name>.yaml`.
7. Append a record to `examples/authoring/GENERATION-LOG.md`.

## Never do

* Never declare facts that were not observed during capture.
* Never use vocabulary terms that are not registered.
* Never invent the oracle or decide correctness on behalf of the human.
* Never regenerate an already frozen scenario at runtime.
