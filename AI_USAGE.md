# AI usage disclosure

## Tools used

| Tool | Version / model | Where |
|---|---|---|
| Claude Code (Anthropic) | Claude Opus 5 | package code, tests, documentation |
| Claude Code (Anthropic) | Claude Opus 5.5 | documentation |

Period of use: September 2026, during the extraction of this package from the
author's research codebase; October 2026, to rewrite the documentation and add
the page on sweeps and uncertainty.

## Nature and scope of assistance

**What preceded the AI assistance.** The generator's method is the author's own
prior research work: the multiplicative decomposition, the choice of a lognormal
AR(1) residual, the intermittency mask, the capacity cap, the cross-carrier
correlation calibration, and the four process classes calibrated on metered
industrial sites the author obtained and analysed. That work existed as research
code before this package, and the scientific contribution is not AI-generated.

**Where AI assistance was used.**

- *Code generation and refactoring.* Restructuring the existing research code
  into a standalone, installable package: module layout, the public API, the
  `DemandSpec` parameterisation, sub-hourly support, the waste-heat carrier, and
  the reference-data module.
- *Test scaffolding.* Writing the test suite, including the property-based
  tests that assert the generator's identities.
- *Derivation and verification.* Deriving the closed-form cross-carrier
  correlation transfer and its calendar floor, and checking both against Monte
  Carlo simulation. The numerical experiment demonstrating that recursive
  refitting degenerates was proposed and run as part of this assistance.
- *Documentation.* Drafting `README.md`, `docs/mathematics.md`, `docs/usage.md`
  and the docstrings.

## Human review and responsibility

*The author confirms, by retaining the statements below, that each is true.*

- The core design decisions were made by the author, not by the tool. These
  include: the decision that the cross-carrier lag is exogenous rather than
  fitted; the parameterisation by heat:cold ratio and electricity share; the
  treatment of waste heat as a by-product sized off the heat demand rather than
  as a share of the demand budget; the exclusion of temperature from the
  generator; and the scope boundaries recorded in `CONTRIBUTING.md`.
- The author has reviewed, edited and validated the generated code,
  documentation and text.
- The author has independently verified the claims made about other software
  and datasets, and every citation in the paper's bibliography.
- The author has verified the numerical results reported in the documentation,
  including the correlation floor, the resolution invariance of persistence, and
  the recursive-refit degeneration.
- The author is responsible for the accuracy, originality, licensing and
  ethical and legal compliance of everything in this repository.

## Note on the development history

This package was extracted from existing research code over a short period. Any
claim about iterative development should describe the history of the *research
code* separately from the history of this repository, and should not present
this repository's commit history as longer than it is.
