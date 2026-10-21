<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Matt-haug/loadcast/main/docs/assets/loadcast-lockup-dark.svg">
    <img alt="loadcast" src="https://raw.githubusercontent.com/Matt-haug/loadcast/main/docs/assets/loadcast-lockup.svg" width="440">
  </picture>
</p>

[![PyPI version](https://img.shields.io/pypi/v/loadcast?label=PyPI)](https://pypi.org/project/loadcast/)
[![Documentation Status](https://img.shields.io/readthedocs/loadcast)](https://loadcast.readthedocs.io/en/latest/)
[![Build Status](https://github.com/Matt-haug/loadcast/actions/workflows/tests.yml/badge.svg)](https://github.com/Matt-haug/loadcast/actions/workflows/tests.yml)
[![License](https://img.shields.io/github/license/Matt-haug/loadcast)](https://github.com/Matt-haug/loadcast/blob/main/LICENSE)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22961300-blue)](https://doi.org/10.5281/zenodo.22961300)


**A parametric generator of hourly industrial energy demand, for comparing
technologies on a common demand, parametric and sensitivity analyses, and
uncertainty propagation.**

`loadcast` generates a year of heat, cold and electricity demand for an
industrial site from a few numbers an engineer can get from a site visit or an
energy bill. The annual energy and the load factor (mean demand over peak
demand) of each carrier match the request exactly; its spread and persistence
(how long a high or low spell lasts) land near their targets. The relationship
between carriers is an input too: how tightly they move together, and how many
hours apart they are offset. A year takes about a second.

```python
import loadcast

profiles = loadcast.generate(
    annual_mwh=10_000,
    heat_to_cold=7.4,        # this site wants 7.4 times more heat than cold
    elec_share=0.20,         # a fifth of its energy is electricity
    process_class="semi_continuous",   # weekday shifts, weekend trough
    carrier_correlation=0.75,          # how tightly the carriers move together
    carrier_lag_h={"cold": 6},         # cold demand trails heat by six hours
)
```

`profiles` is a `DataFrame` with one row per time step (8760 for an hourly
year, 35 040 for a quarter-hourly one) and the columns `heat_kw`, `cold_kw`,
`elec_kw` and `waste_kw`, the last zero unless you ask for waste heat.

![Heat-cold cross-correlogram: the published disaggregated construction peaks at exactly 1.000; loadcast peaks at the 0.60 asked for](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/07_coincidence.png)

*Correlation between heat and cold demand at each offset in hours. Left: every
carrier as a fixed multiple of one shared profile, the construction behind
published disaggregated data, which correlates them at 1 by algebra. Right:
`loadcast` with `carrier_correlation=0.60`. More in the
[tutorial notebook](https://github.com/Matt-haug/loadcast/blob/main/examples/01_tutorial.ipynb).*

## What it is for

Use it when a design study needs the hourly demand of an industrial site and
has no metered series. You are sizing something that serves the site's heat,
cold or electricity: a heat pump, a thermal store, a trigeneration unit.
Metered industrial series are rarely published, so each study builds its demand
from whatever it can obtain: one metered plant, a sector average, a standard
load profile. Studies of different technologies then rarely rest on the same
demand, and their results are hard to compare.

Because a handful of numbers defines the demand, `loadcast` does three things a
borrowed series cannot:

- **Give studies a common demand.** A study that reports its inputs and random
  seed lets anyone regenerate its demand. A heat pump, a thermal store and a
  trigeneration unit can then be assessed against the same site, or against the
  same range of sites.
- **Sweep what no dataset measures.** Whether a site wants its carriers at the
  same hours decides how much storage it needs, and no public dataset resolves
  it. Here it is two inputs, `carrier_correlation` and `carrier_lag_h`, to vary
  like any other.
- **Propagate uncertainty.** Every input is a single number, so the generator
  suits parametric analyses, sensitivity analysis and uncertainty propagation.

It is **not a model of your site.** The inputs are yours to choose, and the
defaults are indicative values with a stated source, not predictions. Report a
conclusion as it holds across a range of inputs, not at one assumed point.

## Why the coupling between carriers is an input

A store exists to bridge the hours when a site wants one carrier and not
another. Sizing it therefore needs more than how much of each carrier the site
uses: it needs to know whether the site wants them at the same hours. No
existing source lets a user set that:

| source | approach | industrial | coupling between carriers settable? |
|---|---|---|---|
| demandlib / BDEW SLP | deterministic step profiles | yes | no: every carrier follows the same calendar |
| RAMP | bottom-up from appliances | no | no: it follows from user schedules |
| LoadProfileGenerator | behavioural simulation | no | no |
| EnTiSe | framework, pluggable methods | partly | no: a dependency between pipeline steps |
| JERICHO-E-usage | disaggregated national totals | yes | no: fixed at exactly 1 |

Published disaggregated datasets build each carrier as a fixed multiple of one
shared profile, $P_m(t) = \kappa_m\,p(t)$, where $P_m(t)$ is the demand for
carrier $m$ at hour $t$, $p(t)$ the shared profile and $\kappa_m$ a constant.
Under that construction the correlation between any two carriers is exactly 1:
an artefact of the method, not a measurement. A storage study fed with such
data has its answer built into its input.

## What you specify

Inputs you can answer from a site visit or an energy bill:

| input | meaning |
|---|---|
| `annual_mwh` | total annual energy across all carriers, as delivered to the process |
| `heat_to_cold` | ratio of annual heat to annual cold |
| `elec_share` | electricity as a fraction of the total |
| `process_class` | how the process runs: continuously, in shifts, in campaigns or in batches |
| `carrier_correlation` | how tightly the carriers move together, once lined up at their best match |
| `carrier_lag_h` | hours by which a carrier trails the others |
| `seed` | random seed: the same inputs and seed give the same profiles |

Every energy is *delivered*: the heat and cold the process receives, and the
electricity it uses for everything else, not the fuel and electricity on the
bill. The [choosing inputs](https://loadcast.readthedocs.io/en/latest/inputs/)
page shows how to convert a bill. Where the site cannot answer, it gives
published values by sector, temperatures included, each with its source and its
limits. It is a guide: a sector average cannot place a single site.

A process class is a rhythm calibrated on metered industrial sites: a calendar
of how demand varies by month, weekday and hour, plus a load factor, a spread
and a persistence. If none fits your site, build one from your own statistics:

```python
from loadcast import class_from_observations, register_class

mine = class_from_observations(
    "my_plant", load_factor=0.45, cv=0.60, lag1=0.90,
    calendar_from="semi_continuous",
)
register_class(mine)
profiles = loadcast.generate(process_class="my_plant", annual_mwh=5_000)
```

Here `cv` is the coefficient of variation of the hourly demand (standard
deviation over mean) and `lag1` its correlation with itself one hour later.
The calendar comes from the nearest shipped class, because measuring one takes
a full year of metering. Closed-form formulas turn the three statistics into
the generator's parameters, with no fitting; the
[mathematics](https://loadcast.readthedocs.io/en/latest/mathematics/) page
derives them.

## What it guarantees exactly

To floating-point precision:

- the annual energy equals `annual_mwh`;
- the heat-to-cold ratio equals `heat_to_cold`, and the electricity share
  `elec_share`;
- the load factor equals the process class's, because a cap on the peak holds
  it;
- every value is strictly positive.

Spread and persistence are aimed at, not imposed. The on/off states and the
cap act after them, so they land near their targets, with a bias the
[mathematics](https://loadcast.readthedocs.io/en/latest/mathematics/) page
reports for each class.

## Diagnostics

```python
loadcast.summary_table(profiles)                       # the four statistics
loadcast.duration_curve(profiles["heat_kw"])           # load duration curve
loadcast.cross_correlogram(profiles["heat_kw"], profiles["cold_kw"])
loadcast.integrated_drift(profiles["heat_kw"], profiles["cold_kw"], window_h=24)
```

The cross-correlogram gives the correlation between two carriers at each
offset in hours. Read where it peaks, not only how high. Offsetting two
carriers lowers their correlation at zero offset towards a floor set by their
shared calendar, which is where a weak coupling would put it too: at zero
offset, a lag and a weak coupling look the same.

The integrated drift is what a store responds to. A store does not see the
mismatch between two carriers hour by hour; it accumulates it. What sizes it is
therefore the mismatch summed over the storage window, and the correlation is
only one point of that picture.

## Sweeps and uncertainty

A year of demand takes about a second, so the uncertain inputs of a site can be
sampled rather than argued. For a semi-continuous food plant whose heat-to-cold
ratio, electricity share, coupling and lag between carriers are all uncertain:

```python
from scipy.stats import qmc        # scipy is not a loadcast dependency

samples = qmc.scale(qmc.Sobol(d=4, seed=1).random(32),
                    [1.0, 0.14, 0.45, 0.0], [3.4, 0.28, 0.90, 12.0])
years = [loadcast.generate(annual_mwh=10_000, heat_to_cold=k, elec_share=e,
                           process_class="semi_continuous", carrier_correlation=r,
                           carrier_lag_h={"cold": int(round(lag))}, seed=1)
         for k, e, r, lag in samples]
```

Feed each year to your design model, and fit a polynomial chaos expansion to
its outputs to rank the inputs. Keep the same seed in every sample: the
[uncertainty page](https://loadcast.readthedocs.io/en/latest/uncertainty/)
shows why, where each range comes from, and what to check before reading the
result.

## What it deliberately does not do

- **No temperature.** It carries energy by carrier. Whether a machine can reach
  a process's temperature is a separate question, answered from the machine's
  own limits. The [choosing inputs](https://loadcast.readthedocs.io/en/latest/inputs/)
  page points to published process and waste heat temperatures by sector.
- **No validated cold shape.** No site in the calibration archive meters
  refrigeration. The cold carrier's annual quantity is whatever you specify,
  but its hourly shape rests on the same calendar and coupling as the other
  carriers, and nothing independent confirms it. Every cold result carries
  this caveat.

## Install

```bash
pip install loadcast
```

Requires Python 3.9+, numpy and pandas. Nothing else.

## Documentation

The [documentation](https://loadcast.readthedocs.io/en/latest/) has six parts:

- [Usage](https://loadcast.readthedocs.io/en/latest/usage/): from the one-liner
  to a class built from your own measurements, and how to check what you got.
- [Choosing inputs](https://loadcast.readthedocs.io/en/latest/inputs/): how to
  read the inputs off an energy bill, and published values by sector,
  temperatures included, for when the site cannot answer.
- [Sweeps and uncertainty](https://loadcast.readthedocs.io/en/latest/uncertainty/):
  one input at a time, sampled inputs, and which inputs matter.
- [Examples](https://loadcast.readthedocs.io/en/latest/examples/): the figures
  of the tutorial notebook, each with what it shows.
- [Mathematics](https://loadcast.readthedocs.io/en/latest/mathematics/): every
  formula derived, with worked numbers and every symbol defined.
- [API reference](https://loadcast.readthedocs.io/en/latest/api/): every public
  function and class.

The [`examples/`](https://github.com/Matt-haug/loadcast/tree/main/examples)
folder holds the tutorial notebook and a sampled food plant.

## Calibration data

The process classes are calibrated on metered industrial sites that cannot be
redistributed. What ships is derived statistics and calendar factors: group
means that carry no identifying information. The raw series are not part of
this repository.

## Sister project

Does your study need hourly electricity prices as well as demand?
[`pricecast`](https://pricecast.readthedocs.io/en/latest/), by the same
authors, turns hourly load, solar and wind generation into a year of hourly
day-ahead prices, with future years built from ENTSO-E's TYNDP scenarios. It
follows the same idea: a few stated inputs give a year of hourly data, fast
enough to sweep and to sample.

## Citing

Use the "Cite this repository" button or
[`CITATION.cff`](https://github.com/Matt-haug/loadcast/blob/main/CITATION.cff).
Every release is archived on Zenodo:
[10.5281/zenodo.22961300](https://doi.org/10.5281/zenodo.22961300).

## Contributing

Issues and pull requests are welcome; see
[CONTRIBUTING.md](https://github.com/Matt-haug/loadcast/blob/main/CONTRIBUTING.md)
for the scope, what a test looks like here, and what support to expect. Reports
of generated profiles that disagree with a site you have measured are
especially useful: the calibration archive is small, and that is the package's
main limitation. This project follows the
[Contributor Covenant](https://github.com/Matt-haug/loadcast/blob/main/CODE_OF_CONDUCT.md).
Generative AI was used in building it; see
[AI_USAGE.md](https://github.com/Matt-haug/loadcast/blob/main/AI_USAGE.md).

## Licence

MIT; see [LICENSE](https://github.com/Matt-haug/loadcast/blob/main/LICENSE).
Changes are recorded in
[CHANGELOG.md](https://github.com/Matt-haug/loadcast/blob/main/CHANGELOG.md).
