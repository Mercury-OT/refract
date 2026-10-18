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
Human (top)             Drafting (middle)            Framework (bottom)
examples/authoring/     human or AI                 refracto/
*.case.yaml      ->     rules.md guidance    ->     scenarios/*.yaml -> RunReport
intent + oracle         explicit transformation     frozen handoff       execution
```

* Humans may write `cases/*.case.yaml`: intent plus oracle. These are optional
  drafting inputs, not another executable language or approval artifact.
* A human or optional AI tool drafts `scenarios/*.yaml` using `rules.md`.
  No packaged authoring skill or automatic conversion tool is supplied here.
* Humans approve the exact resulting `schema_version: 1` YAML, then the framework
  executes that frozen scenario. Validation is not approval or execution.

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
    -> optional drafting using rules.md
    -> human review and approval
    -> scenarios/demo_item_update.yaml
    -> refracto runner
    -> RunReport
```

See `GENERATION-LOG.md` for example capture records.

The existing `cases/*.case.yaml` and generation log are historical authoring
inputs, not executable Scenarios or current-format templates. In particular,
their preparation descriptions must become explicit actions when drafting a
current Scenario; they do not authorize an adapter precondition callback.
