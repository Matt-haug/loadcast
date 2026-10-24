<p align="center" markdown>
![loadcast](assets/loadcast-lockup.svg#only-light){ width="440" }
![loadcast](assets/loadcast-lockup-dark.svg#only-dark){ width="440" }
</p>

**A parametric generator of hourly industrial energy demand, for comparing
technologies on a common demand, parametric and sensitivity analyses, and
uncertainty propagation.**

`loadcast` turns a few numbers an engineer can get from a site visit or an
energy bill into a year of hourly heat, cold and electricity demand. Those
numbers are the annual energy, the ratio of heat to cold, the electricity
share, and whether the process runs continuously, in shifts, in campaigns or in
batches. A year takes about a second, which makes the generator an *input* for
design studies of anything that serves an industrial site, such as a heat pump,
a thermal store or a trigeneration unit. Because a handful of numbers defines
the demand, a study that reports them lets anyone regenerate it. Different
technologies can then be assessed against the same demand, or against the same
range of demands, which is what a sweep or an uncertainty propagation needs.

One input sets it apart: the relationship between carriers. Published
multi-carrier industrial data builds each carrier as a fixed multiple of one
shared profile, so the carriers are correlated at exactly 1 by algebra rather
than by measurement. That matters for anything with storage, because a store
exists to bridge the hours when a site wants one carrier and not another. In
`loadcast`, `carrier_correlation` sets how tightly the carriers move together
and `carrier_lag_h` how many hours apart they are offset. No public archive
meters process heat and refrigeration at one site, so neither can be fitted:
they are inputs to sweep, and a result should be reported as it holds across
the swept range.

```python
import loadcast

profiles = loadcast.generate(
    annual_mwh=10_000,
    heat_to_cold=7.4,
    elec_share=0.20,
    process_class="semi_continuous",
    carrier_correlation=0.75,
    carrier_lag_h={"cold": 6},
)
```

```bash
pip install loadcast
```

A shipped process class gives a first result with nothing to tune. Everything
else is yours to set when you know it: the site's calendar (from its shift
schedule, a week of metering or twelve monthly bills), how often it stops, each
carrier's rated capacity, and a calendar of its own for a carrier that keeps
other hours.

The annual energy, the heat-to-cold ratio, the electricity share and the load
factor come out exact; spread and persistence land near their targets.
Whatever cannot be delivered as asked draws a warning that says why. The
generator does not model temperature, and it makes no claim about any real
site: the inputs are yours to choose.

- [Usage](usage.md): from the one-liner to a class built from your own
  measurements, and how to check what you got.
- [Choosing inputs](inputs.md): how to read the inputs off an energy bill, and
  published values by sector, temperatures included, for when the site cannot
  answer. A guide, with the source and the limits of every number.
- [Sweeps and uncertainty](uncertainty.md): one input at a time, sampled
  inputs, and which inputs matter.
- [Examples](examples.md): the figures of the tutorial notebook, each with what
  it shows.
- [Mathematics](mathematics.md): every formula derived, with worked numbers and
  every symbol defined. Each derivation has a matching test.
- [API reference](api.md): every public function and class.

Does your study need hourly electricity prices as well as demand? Its sister
project, [`pricecast`](https://pricecast.readthedocs.io/en/latest/), by the
same authors, turns hourly load, solar and wind generation into a year of
hourly day-ahead prices, with future years built from ENTSO-E's TYNDP
scenarios.
