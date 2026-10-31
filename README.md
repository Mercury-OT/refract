<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/refract-v2-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="assets/refract-v2-light.png">
    <img src="assets/refract-v2-dark.png" alt="Refract logo" width="200">
  </picture>
</p>

<h1 align="center">Refract</h1>

<p align="center">
  <i>Bounding drift by contract, exposing drift by evidence.</i>
</p>

<p align="center">
  <a href="MANIFESTO.md"><b>Read the Refract Manifesto →</b></a>
</p>

---

Refract is a product-neutral testing infrastructure core for the AI era.

It provides three things:

* a standard scenario contract
* a deterministic multi-projection executor
* a port-based adapter model

A scenario declares ordered actions and what should be true after them. Logical UI targets keep product selectors in the adapter; direct API requests remain explicit actions. Selected projections check frontend behavior, outgoing requests, responses, and backend evidence without hiding business preparation in adapter scripts.

Declare logical accounts under `users`, select the acting `user` when there is
more than one, and use `session: new` when the same account must log in again.
Declare `anonymous` alongside named users to exercise unauthenticated actions
without inheriting their sessions. One-level inclusion uses `with_users` to map
a reusable child's participants explicitly to the parent's participants.
See the [user/session contract](SCENARIO.md#users-and-current-sessions)
for account, context, evidence, and reuse limits.

## Current Scope

Refract currently targets a Web/API reference profile:

* frontend
* request
* response
* backend state

This repository contains:

* the core package `refracto`
* the public scenario contract in `SCENARIO.md`
* the minimal integration guide in `docs/onboarding.md`
* a dependency-free clean-room example in `examples/minimal/`
* a reference demo adapter set in `adapters/demo/`
* a self-contained demo application in `examples/demo-app/`
* demo scenarios in `scenarios/`

The demo is intentionally retained as a teaching and validation asset so the framework remains understandable and runnable without private product dependencies.

## Package

* Distribution name: `refracto`
* Import: `import refracto`

## Installation

Install the core package:

```bash
pip install -e .
```

Install the offline development test dependencies:

```bash
pip install -e ".[dev]"
```

Install the demo application and demo-adapter test dependencies as well:

```bash
pip install -e ".[dev,demo]"
```

For UI tests, also install the Playwright browser runtime:

```bash
playwright install chromium
```

## Validate a Scenario

After installation:

```bash
refracto validate path/to/scenario.yaml
```

## Repository Layout

```text
refracto/            core package
adapters/demo/       reference adapter implementation
examples/demo-app/   self-contained example target
scenarios/           public demo scenarios
SCENARIO.md          scenario contract
MANIFESTO.md         project philosophy and beliefs
BRAND.md             logo usage and project identity guidance
```

## Contract

See [`SCENARIO.md`](SCENARIO.md) for the public scenario contract.

## Brand Assets

See [`BRAND.md`](BRAND.md) for the intended use of the Refract name and logo
variants.

## Onboarding

See [`docs/onboarding.md`](docs/onboarding.md) for a CI-tested minimal
request/response integration.

For optional Playwright support in UI adapters, see
[`docs/browser-support.md`](docs/browser-support.md).

For changes affecting existing Python integrations, see the
[selected compatibility notes](CHANGELOG.md).

## Philosophy

See [`MANIFESTO.md`](MANIFESTO.md) for the beliefs and vision behind this framework.

## Planning

See the [public roadmap](docs/roadmap.md) for task priorities, design boundaries,
and the distinction between planned work and the currently supported contract.

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
