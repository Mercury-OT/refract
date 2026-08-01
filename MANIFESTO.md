# The Refract Manifesto

## Preamble

We are entering an era in which the pace of software production is being redefined.

AI turns requirements into code faster, turns code into systems faster, and drives the cost of change, refactor, extension, and duplication down at a rate that has no precedent. Software is being generated faster, and it is changing faster.

But speed has never been the same as correctness. Producing code faster is not the same as producing trustworthy software faster.

Without a matching quality infrastructure, what AI accelerates is not only throughput. It also accelerates drift, hidden deviation, expensive rework, and, in the end, a backlash against the very velocity it appeared to grant.

Software goes out of control not because it changes too slowly, but precisely because it changes too fast — and its correctness is no longer continuously constrained, continuously verified, or continuously governed.

Refract exists to answer that.

Refract does not try to replace requirements. It does not try to invent business truth. And it does not rest quality on a pile of fragile scripts.

What Refract does is to lift "what counts as correct" out of brittle execution details and settle it as a stable scenario contract; and then, through multi-projection, multi-evidence execution, to give a traceable verdict on whether the system remains faithful to its intent and still deserves to be trusted.

In the AI era, the scarce resource is no longer generation capability. What is scarce is:

* a clear expression of correctness;
* timely exposure of deviation;
* credible evidence behind every quality verdict;
* and sustained governance of the verification assets themselves.

Refract is not built to make people write more tests. It is built so that, in the midst of high-velocity generation, software does not lose its boundaries, its order, or its trustworthiness.

## What We Believe

### 1. Quality is not "the absence of errors." It is "behavior that remains faithful to intent."

A successful response is not proof that the system is correct. A page that looks normal is not proof that the business really holds. A pipeline that does not break is not proof that internal semantics have not degraded.

The essence of quality is not that some endpoint returned 200, or that some page finished a click. It is whether:

* the outcome the user expects has actually happened;
* the contract the system promised still holds;
* the software, after change, is still faithful to the requirement and intent it was meant to serve.

### 2. Correctness must be declared, not buried in script details.

If "what counts as correct" only lives in a selector, a wait loop, a hard-coded path, or a script that happened to pass this time — then quality will inevitably rot together with those implementation details.

Refract holds that the durable testing asset is not the script; it is the scenario contract.

The scenario declares intent, constraints, and expectations. Selectors, path mappings, wait policies, and trace queries belong to the mechanical layer — replaceable, rebuildable, generatable, and repairable.

### 3. Single-point evidence is not worth trusting. Multi-source evidence is what a verdict requires.

Looking only at the UI is easy to fool with appearance. Looking only at APIs misses real experience. Looking only at return values misses internal state. Looking only at internal instrumentation loses the user's viewpoint.

Refract therefore runs the same scenario across multiple projections, and cross-verifies the same business fact from multiple faces of evidence.

For Web / API products today, this means asking, in one execution:

* whether the frontend rendered the correct result;
* whether the outgoing request obeyed the contract;
* whether the response satisfied its promise;
* whether the backend emitted the semantic evidence it should have.

We do not pursue more test styles. We pursue a stronger evidence structure.

### 4. AI can accelerate generation. It must not replace truth.

AI can help us understand requirements, draft scenarios, repair the mechanical execution layer, summarize failures, and propose improvements.

But AI must not unilaterally decide what counts as business correctness, which assertion may be deleted, which failure may be ignored, or which requirement has been sufficiently verified.

Refract does not delegate quality judgment to AI. It establishes, for the AI era, a verification infrastructure with clear boundaries:

* humans define intent;
* the system collects evidence;
* AI participates in generation and analysis;
* governance decides admission and release.

### 5. The point is not "how many tests can be generated," but "whether correctness can be governed."

AI makes scenarios, scripts, examples, and adapters generatable at scale. Generation was never the endpoint.

What actually decides whether a system is reliable is not the number of test files it has, but whether those scenarios express real business risk, whether those assertions are actually strong enough, whether that evidence can support a release decision, and whether those assets can be tracked, audited, and evolved.

Refract pursues the quality density of verification assets, not the quantity of tests.

### 6. Quality is not an obstacle to speed. It is the precondition for speed to last.

High-velocity generation without quality constraints only pays a larger bill later. Rework, incidents, collapsed trust, and uncontrolled regression eventually consume the very efficiency they seemed to unlock.

Sustainable speed is not writing code faster. It is writing code, faster, that can still be trusted.

Refract does not aim to slow engineering down. It aims to keep engineering from being crushed by its own loss of control.

Quality is not the enemy of speed. The absence of a quality infrastructure is.

## What We Acknowledge

We provide traceable evidence, not an absolute proof of complete correctness.

Quality is not something to be proven once. It is a process of continuous exposure, continuous verification, and continuous governance.

The value of Refract is not to claim that software will never drift. The value of Refract is to make drift visible earlier, easier to locate, and systematically governable.

## What We Hold

* scenarios, not scripts, are the long-term asset;
* contracts, not incidental passes, are the basis of correctness;
* multiple projections, not a single vantage point, support a quality verdict;
* evidence, not intuition, drives release decisions;
* governance, not a pile of test files, is what builds a trustworthy system;
* human–AI collaboration, not wholesale automation, establishes the quality order of the AI era.

## Our Vision

We hope Refract becomes the verification infrastructure of software engineering in the AI era.

It connects requirement with implementation, scenario with execution, change with evidence, AI-driven generation with human-driven governance.

Its purpose is not more tests. Its purpose is that software systems, changing at high speed, still retain a sense of boundary, explainability, and trust.

We look toward a path in which requirements are understood, scenarios are generated, contracts are reviewed, systems are executed, evidence is collected, results are traced, quality is governed — and release, as a consequence, is both faster and more stable.

In an era where code can be created at unprecedented speed, what Refract guards is not generation itself, but whether — after generation — the software is still worth using, still worth maintaining, and still worth being trusted.

## Closing

Software can be created faster and faster. Correctness can no longer rest on luck.

Refract — bounding drift by contract, exposing drift by evidence, for the trustworthy delivery of software in the AI era.
