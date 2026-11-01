# One Flow, three Scenarios

This is the runnable example for [FLOW.md](../../FLOW.md). The Flow creates a
document, modifies its content, then reads the same document. All three calls use
one mapped user's current session and explicit shared values.

The existing Documents adapter and in-process REST target are reused unchanged.
The example exercises actual target state and responses, not a preconstructed
passing report. It is a synthetic demonstration, not evidence of product adoption.

```sh
uv run --locked --no-sync refracto validate-flow examples/flow/document_lifecycle.flow.yaml
uv run --locked --no-sync python -m examples.flow.run_example
```

`document_id` begins unset and is published from creation's observed response.
`content` is overwritten after update succeeds, using the independently declared
`updated_content`. Read-back cannot obtain an expected value from its own response.
The sidecar pins the exact three Scenario files. They deliberately require a
Flow, so standalone Scenario validation rejects them before any target action.
