# authoring/ — Explicit authoring layer

This directory is an optional satellite layer above the execution boundary. It
shows one reference workflow for turning human intent into frozen scenario
artifacts. The framework itself can execute any valid scenario regardless of
how it was authored; small projects may write `scenarios/*.yaml` directly and
skip this layer entirely.

Refracto has two orthogonal kinds of layering:

* Collaboration layering: human / AI / framework — roles and workflow.
* Code architecture layering: declaration / `refracto` engine / adapters + ports.

## Three roles and their files

```text
Human (top)             AI (middle)                 Framework (bottom)
examples/authoring/     .claude/skills/             refracto/
*.case.yaml      ->     refract-authoring   ->      scenarios/*.yaml -> RunReport
intent + oracle         structure from rules.md     frozen handoff       deterministic
```

* Humans write `cases/*.case.yaml`: intent plus oracle.
* AI structures those cases into deterministic `scenarios/*.yaml` according to
  `rules.md`.
* The framework executes the frozen scenario and returns a deterministic report.

## The handoff boundary

`scenarios/` is the handoff artifact between authoring and execution. Above the
boundary is authoring; below it is deterministic execution.

## Deterministic contract

The same scenario in the same environment should produce the same `RunReport`.
AI participates only before freeze time; once a scenario is frozen, it is not
regenerated during execution.

## Projection choice belongs to the caller

A scenario declares which observation blocks exist. The caller chooses which
projections to run. A backend-only scenario does not need frontend or e2e
execution.

## Lifecycle of one case

```text
examples/authoring/cases/item_update.case.yaml
    -> refract-authoring skill
    -> human review and approval
    -> scenarios/demo_item_update.yaml
    -> refracto runner
    -> RunReport
```

See `GENERATION-LOG.md` for example capture records.
