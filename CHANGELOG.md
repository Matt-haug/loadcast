# Changelog

Notable changes to `loadcast`. This project follows
[semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.4] - 2026-10-21

### Changed
- The README, the documentation's home page, the package docstring and the
  citation abstract present the package as a parametric demand generator: a
  common demand that any study can regenerate from its inputs, for comparing
  technologies, parametric and sensitivity analyses, and uncertainty
  propagation. The coupling between carriers remains the input that sets it
  apart.
- The README states which statistics are exact (annual energy, composition,
  load factor) and which only land near their targets (spread, persistence),
  and gives the row count of a sub-hourly year and the `waste_kw` column.
- The usage, examples and mathematics pages and the public docstrings are
  rewritten for plain reading: each paragraph leads with its point, every term
  is defined where it first appears, and the internal "knob" is called what it
  is, the correlation between the carriers' latent series. The usage page gains
  sections on waste heat, sub-hourly steps and sites with only some carriers.
- The bias table on the mathematics page is refreshed from `bias_report()` and
  now shows the spread as well: the batch class comes out at 1.41 against a
  target of 1.18.

### Added
- A documentation page on sweeps and uncertainty propagation: one input at a
  time, sampled inputs with the source of each range, and polynomial chaos
  expansions with their leave-one-out check. It shows, on measured numbers, why
  every sample should use the same seed and the study be repeated over a few.
- `examples/02_uncertainty.py`: 32 years of demand for a semi-continuous food
  plant, sampled over its heat-to-cold ratio, electricity share, coupling and
  lag between carriers.

### Fixed
- PyPI listed the co-authors as the authors and the first author only as
  an email; all three are now authors, with a maintainer contact.
- Documentation errors: the energy balance on the mathematics page lacked the
  factor 1000 between kWh and MWh; its symbols `T`, `k`, `h` and `m` each named
  two things; `bias_report` said persistence comes out above target, which
  holds only for classes without an on/off state; `DemandSpec` pointed to
  `solve_correlation_knob` in the wrong module and did not document
  `waste_to_heat`; the examples page gave waste heat a correlation of its own,
  which it does not have.
- The diagnostics now work in hours at any step length. They counted time
  steps, so on a 15-minute profile `cross_correlogram` reported offsets in
  quarter-hours, `integrated_drift(window_h=24)` summed six hours rather than a
  day, and `profile_statistics` gave four times the annual energy. Each now
  reads the step length from the series' time index, or from a new
  `hours_per_step` argument for a bare array; `lag_h` is in hours and the drift
  is weighted by the step. Hourly results are unchanged.

## [0.1.3] - 2026-10-09

### Added
- A logo: the camel - a two-shift day of industrial load with an eye - on the
  README, the documentation and the social preview (`docs/assets/`).
- An API reference page in the documentation, generated from the docstrings.

### Changed
- The documentation is restyled to match the logo: Manrope for text, IBM Plex
  Mono for code and titles, the package colour in moderation, a dark mode.

## [0.1.2] - 2026-10-09

### Changed
- The version now comes from the git tag of each release (setuptools-scm).
- Ward De Paepe and Francesco Contino added as authors.

## [0.1.1] - 2026-10-09

First release on PyPI.

### Fixed
- The bundled calibration data could not be read on Python 3.9:
  `loadcast.data` is now a regular package rather than a namespace package.
- Time-step detection under pandas 3, which stores timestamps at microsecond
  rather than nanosecond resolution.

### Added
- Tutorial notebook and an examples gallery in the documentation.

## [0.1.0] - 2026-09-25

First public release.

### Added
- Multi-carrier generator for industrial heat, cold and electricity demand:
  calendar factor, lognormal AR(1) residual, Gaussian-copula intermittency
  mask, and a capacity cap applied as a fixed-point iteration.
- Cross-carrier structure as explicit inputs: `carrier_correlation` (defined at
  peak alignment) and `carrier_lag_h`.
- Waste heat as a fourth carrier with its own residual, sized off the heat
  demand rather than taking a share of the demand budget.
- Four process classes calibrated on metered industrial sites, shipped as
  derived statistics and calendar factors only.
- `class_from_observations` and `register_class` for generating from a user's
  own measured statistics, via closed-form parameter inversion.
- Any subset of carriers, through `DemandSpec.from_shares`.
- Sub-hourly output: persistence rescaled as `phi ** hours_per_step`, energy
  normalised over elapsed hours, lags given in hours at any resolution.
- `loadcast.reference`: indicative published values from three peer-reviewed
  sources, each shipped with its caveat.
- Diagnostics: `profile_statistics`, `duration_curve`, `cross_correlogram`,
  `integrated_drift`, `bias_report`.
- Test suite covering the imposed identities, the closed-form inversions, and
  the resolution invariants.

### Known limitations
- No site in the calibration archive meters refrigeration, so the cold
  carrier's hourly shape rests on the same calendar and correlation assumptions
  as the others and is not independently validated.
- Spread and persistence are aimed at rather than imposed; `bias_report()`
  reports the systematic offset, whose sign differs by process class.
- Refitting a class on generated output degenerates. See the warning on
  `class_from_observations`.

[Unreleased]: https://github.com/Matt-haug/loadcast/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/Matt-haug/loadcast/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Matt-haug/loadcast/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Matt-haug/loadcast/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Matt-haug/loadcast/releases/tag/v0.1.0
