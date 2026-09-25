# Changelog

Notable changes to `loadcast`. This project follows
[semantic versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/Matt-haug/loadcast/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Matt-haug/loadcast/releases/tag/v0.1.0
