# Refract

Refract is a product-neutral testing infrastructure core for the AI era.

It provides three things:

* a standard scenario contract
* a deterministic multi-projection executor
* a port-based adapter model

A scenario declares what should be true, not how to click it. The framework runs that declaration across multiple projections so one scenario can validate frontend behavior, request shape, response contract, and backend evidence.

## Current Scope

Refract currently targets a Web/API reference profile:

* frontend
* request
* response
* backend state

This repository contains:

* the core package `refracto`
* the public scenario contract in `SCENARIO.md`
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
```

## Contract

See [`SCENARIO.md`](SCENARIO.md) for the public scenario contract.

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
