# Changelog

Notable changes to `loadcast`. This project follows
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- Your own calendar: `loadcast.Calendar`, twelve month factors and 168
  hour-of-week factors, built from a shift schedule (`from_schedule`, with a
  base load outside the shifts), a metered series of a week or more
  (`from_series`), twelve monthly bills (`with_monthly_energy`) or a shipped
  class (`Calendar.of`). A week of 168 factors lets each day keep its own
  hours, such as a Saturday morning shift.
- `loadcast.custom_class`: a shipped class with any of its numbers changed --
  calendar, share of hours stopped, idle level, load factor, spread,
  persistence. What is not given is derived so the plant behaves as the base
  does while it runs: the base's fluctuation is kept, and the load factor is
  the one whose cap clips the same share of hours as the base's
  (`matched_load_factor`).
- `DemandSpec.rated_kw`: each carrier's rating in kW, which becomes the cap on
  its profile: the peak equals the rating, and the load factor is the mean
  demand over it.
- `DemandSpec.load_factor`: each carrier's load factor, the other way to set
  its cap. A carrier takes a rating or a load factor, not both: with its annual
  energy fixed, each implies the other, and the error says so in numbers.
- `DemandSpec.calendars`: a calendar of its own for a carrier that keeps other
  hours, such as cold rooms running through the weekend. It lowers the
  correlation floor accordingly.
- `DemandSpec.process_class` takes a `ProcessClass` object, so a class built in
  a loop needs no registering.
- `loadcast.delivery_report` and `loadcast.TargetMissedWarning`: every
  statistic asked against what was delivered, and a warning naming the cause
  of each miss -- a rating above the profile's own peaks, a load factor the
  calendar makes unreachable, a correlation below the floor, a spread smaller
  than the calendar already makes. The shipped classes at their defaults never
  warn.
- `correlation_floor` of a `DemandSpec` measures the floor of that site, own
  calendars and ratings included.
- The usage page gains a section on fitting a class to a site, with four
  figures (`usage_*.png`, drawn by `examples/build_doc_figures.py`); the uncertainty
  page sweeps the calendar, the share of hours stopped and a rating, with a
  figure; the mathematics page derives all of it (section 12); the "Choosing
  inputs" page says where a calendar and a rating come from.
- A documentation page, "Choosing inputs": how to turn an energy bill into the
  inputs; published values by sector for when the site cannot answer, each with
  its source and its limits; and the process and waste heat temperatures a
  study needs, which the generator does not carry. It is a guide, not a
  calibration. The README, the home page and the usage page point to it.
- `loadcast.reference.temperature_bands`: heat by temperature band for 13 German
  branches (Naegler et al., 2015), and heating and cooling by band for 7 UK
  subsectors in two datasets (Rehfeldt et al., 2018). Naegler et al. join the
  sources listed by `reference.sources()`.
- The mathematics page credits the time-series theory it builds on (Box,
  Jenkins, Reinsel and Ljung, *Time Series Analysis*): the package adds no new
  theory, only a way of combining it to produce the signals a user asks for.
- The README and the documentation's home page point to the sister project
  `pricecast`, by the same authors, for hourly electricity prices.

### Changed
- Every figure of the documentation and the tutorial notebook shares one style,
  `examples/figure_style.py`, after Jean-luc Doumont's *Trees, maps, and
  theorems*: each figure's message opens its caption on the page, and the image
  carries no title; lines are named on the plot, not in a legend; the y label
  stands horizontal above its axis; the axes stand apart from the data, run from
  tick to tick, and carry inward ticks; every line is solid, told apart by
  colour -- a carrier keeps one colour, variants of it are shades of that colour,
  anything else is ink or grey, and reference lines are light grey; weeks start
  on Monday with the weekend shaded. The text is set in Manrope when it is
  installed or its files sit in the folder `LOADCAST_FIGURE_FONTS` names, and in
  matplotlib's default font otherwise; the package ships no font.
- `carrier_correlation` defaults to `None`: 0.47, raised to the floor without a
  warning where the floor is higher, as before.
- The documentation and `DemandSpec` state the energy basis: delivered energy,
  the heat and cold the process receives and the electricity it uses for
  everything else, not the fuel and electricity bought.
- `heat_to_cold_range` gives `None` as its high value when one of the two
  datasets reports no cooling for a subsector, as for paper: the ratio is then
  unbounded above.

### Fixed
- The cap could stop short of its fixed point: it ran eight passes, enough for
  the shipped classes but not for a tight rating, where the peak overshot by
  0.03 %. It now runs until the peak is within 1e-12 of the cap. Profiles
  generated before move by less than one part in ten million.
- The correlation solver cached its answer by class *name*, so a class rebuilt
  under the same name with other numbers reused a stale solution. It now keys
  on the class itself, and on the heat and cold caps and calendars.
- A correlation asked below the floor, and a load factor the cap could not
  reach, were delivered differently without a word. Both now warn.
- The Rehfeldt et al. shares behind `heat_to_cold_range` were misread from
  their Fig. 16. Re-measured from the figure to about +-1 percentage point,
  food, beverages and tobacco has 11.8 % and 17.7 % cooling, not 8 % and 3 %,
  so its heat-to-cold ratio is 4.6 to 7.5, not 11.5 to 32.3. Chemicals is 6.6
  to 17.9, not 6.7 to 49; paper has cooling in one dataset (22.8), where none
  was reported; machinery and transport has none that can be read, where 49 was
  reported. The paper's text confirms the reading: ECUK gives food no space
  heating, which the old values did.
- Those ratios are final energy (fuel for heat, electricity for the chillers),
  and the uncertainty page used them as the delivered ratio `generate` takes.
  The docstrings now say so, and the new page gives the conversion. The
  uncertainty page's food plant now samples a delivered heat-to-cold ratio of
  1.0 to 3.4 (boiler efficiency 0.9, chiller COP 2 to 4) instead of 11.5 to
  32.3, and its peaks and figures are regenerated. The drift and its Sobol
  indices do not depend on the shares and are unchanged.
- The claim that three metered food plants fall outside their branch's range
  now compares like with like: on a delivered basis the branch spans 1.4 to
  2.2 and the plants 0.33 to 44, a factor of 135 against 1.6, not 2.8.
- The documentation build pins `pymdown-extensions` below 11: with 12.x,
  mkdocstrings fails on every page that renders a docstring.

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
- Figures on that page: each input swept on its own against each output, the
  sampled years and the spread of their outputs, and the drift against each
  input with its Sobol indices for several seeds.
  `examples/build_doc_figures.py` draws them into `docs/assets/figures/`. The
  usage page shows the tutorial's figures where they illustrate a section.

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
