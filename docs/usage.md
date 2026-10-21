# Usage

This page goes from the one-line call to a process class built from your own
measurements, then shows how to check what the generator produced. Sweeping
and sampling the inputs has its own page,
[Sweeps and uncertainty](uncertainty.md).

## The quickest thing that works

```python
import loadcast

profiles = loadcast.generate(annual_mwh=10_000, heat_to_cold=7.4,
                             elec_share=0.20)
```

`profiles` is an hourly `DataFrame` of 8760 rows, with the columns `heat_kw`,
`cold_kw`, `elec_kw` and `waste_kw`. The year is 2025 unless you pass `year=`.

The energies are delivered: the heat and cold the process receives, and the
electricity it uses for everything else. [Choosing inputs](inputs.md) shows how
to read them off an energy bill, and what to use when the site cannot say.

## Choosing a process class

A process class is the rhythm the demand follows: a calendar of how it varies
by month, weekday and hour, and how widely and for how long it strays from that
calendar. Choose it from what you know of the site's process, not by trying each
class and keeping the one that gives the answer you expected.

| class | what it looks like | measured on |
|---|---|---|
| `continuous` | runs around the clock, with modest excursions | drying, continuous mineral processing |
| `semi_continuous` | weekday shifts, with a weekend trough | brewing, burners |
| `campaign` | long runs separated by real shutdowns | chemical campaigns |
| `batch` | strongly bimodal, with most hours near zero | roasting, batch kilns |

![A fortnight of heat demand in each of the four process classes](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/06_process_classes.png)

*Two weeks of heat demand in each class, at the same annual energy. LF is the
load factor, CV the coefficient of variation and idle the share of hours below
5% of the peak.*

```python
for name in loadcast.available_classes():
    process = loadcast.get_class(name)
    print(name, process.description, process.target_load_factor)
```

## A site with only some carriers

A site with no cooling takes `heat_to_cold=None`; a site with no heat takes
`heat_to_cold=0`:

```python
loadcast.generate(annual_mwh=5_000, heat_to_cold=None, elec_share=0.3)  # no cold
loadcast.generate(annual_mwh=5_000, heat_to_cold=0.0,  elec_share=0.3)  # no heat
```

For any other subset, give the shares of the carriers the site has, summing to
one, through `DemandSpec.from_shares`:

```python
spec = loadcast.DemandSpec.from_shares({"cold": 0.7, "elec": 0.3},
                                       annual_mwh=5_000)
profiles = loadcast.generate(spec)
```

The frame keeps every column; the carriers left out are zero.

## Setting the coupling between carriers

Two inputs set how the carriers relate, and they do different things:

```python
# how tightly the carriers move together, once lined up at their best match
loadcast.generate(..., carrier_correlation=0.75)

# how many hours apart they are offset: cold demand trails heat by six hours
loadcast.generate(..., carrier_lag_h={"cold": 6})
```

The correlation has a floor. The carriers share a calendar, so they all dip on
Sundays and in July, and they are correlated even when their fluctuations are
independent:

```python
>>> loadcast.correlation_floor("semi_continuous")
0.434
```

No setting delivers less. The floor is the share of each carrier's variance
that the calendar contributes, so where it is high, the carriers move together
mainly because the factory is open or shut.

The lag cannot be measured. No public archive meters process heat and
refrigeration at the same industrial site, so no heat-to-cold lag can be
estimated from data: sweep it, and report how your conclusion moves. While
sweeping it, hold `carrier_correlation` fixed. The correlation is defined at
the offset where the carriers match best, so the sweep then changes their
timing only:

![Correlation between heat and cold at each offset, for lags of 0 to 24 hours](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/08_lag.png)

*Correlation between heat and cold at each offset, for cold lags τ of 0 to 24
hours. The peak moves to τ, while the value at zero offset falls towards the
calendar floor.*

[Sweeps and uncertainty](uncertainty.md) shows what such a sweep does to a
design's outputs.

## Waste heat

Waste heat is what the site rejects, not what it buys, so it takes no share of
`annual_mwh`. It is sized from the heat demand instead, with `waste_to_heat`,
and can trail it like any other carrier:

```python
profiles = loadcast.generate(annual_mwh=10_000, heat_to_cold=7.4, elec_share=0.2,
                             waste_to_heat=0.8, carrier_lag_h={"waste": 2})
```

Here the site rejects 0.8 MWh of waste heat per MWh of heat it uses.
`loadcast.reference.waste_to_heat(sector)` gives indicative values for four
sectors.

![Heat demand and the waste heat rejected, the waste trailing by two hours](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/11_waste.png)

## Sub-hourly steps

Pass any pandas frequency as `freq`:

```python
profiles = loadcast.generate(annual_mwh=10_000, heat_to_cold=7.4,
                             elec_share=0.2, freq="15min")   # 35 040 rows
```

The annual energy, the load factor and the persistence measured in hours stay
the same at every step length. The process classes were calibrated on hourly
meters, though, so a 15-minute profile spreads hourly behaviour over a finer
grid; it adds no measured sub-hourly detail.

![Two days of heat demand at hourly, 30-minute and 15-minute steps](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/10_resolution.png)

The diagnostics below read the step length from the frame's index, so their
offsets, windows and energies are in hours at any step length:
`max_lag=12` spans twelve hours, and `window_h=24` a day. Only `lag1` in
`summary_table` is per step, as the generator's persistence is; on 15-minute
steps, raise it to the power 4 for the value one hour later. For a bare array
with no time index, pass `hours_per_step`.

## Generating from your own measurements

If you have a metered series, or even three numbers from an annual bill, build
a class from them:

```python
from loadcast import class_from_observations, register_class

mine = class_from_observations(
    "my_plant",
    load_factor=0.45,      # mean demand over peak demand
    cv=0.60,               # coefficient of variation: standard deviation over mean
    lag1=0.90,             # correlation of the series with itself one hour later
    calendar_from="semi_continuous",   # the closest shift pattern
)
register_class(mine)

profiles = loadcast.generate(process_class="my_plant", annual_mwh=5_000,
                             heat_to_cold=3.0, elec_share=0.15)
```

The calendar comes from the class you name, because measuring one takes a full
year of metering, which a user rarely has. Everything else comes from your
numbers, through closed-form formulas.

If your process stops rather than merely running low, pass `off_fraction`, the
share of hours it is off. Spread alone makes a profile low, never off:

```python
class_from_observations("my_batch", 0.25, 1.1, 0.85, off_fraction=0.40)
```

Feed it measurements, never statistics taken from generated profiles: the last
section of the [mathematics](mathematics.md) page shows how that loop degrades
a class.

## Checking what you got

```python
loadcast.summary_table(profiles)
```

|  | mean_kw | peak_kw | load_factor | cv | lag1 | idle_fraction | annual_mwh |
|---|---|---|---|---|---|---|---|
| heat_kw | 804.5 | 2006.3 | 0.401 | 0.46 | 0.86 | 0.00 | 7047.6 |
| cold_kw | 108.7 | 271.1 | 0.401 | 0.46 | 0.86 | 0.00 | 952.4 |
| elec_kw | 228.3 | 569.4 | 0.401 | 0.47 | 0.87 | 0.00 | 2000.0 |
| waste_kw | 0.0 | 0.0 | 0.000 | 0.00 | 0.00 | 0.00 | 0.0 |

The idle fraction is the share of hours below 5% of the peak.

### The load duration curve

The load duration curve is the year's demand sorted from the highest hour to the
lowest. It is often the only thing a site can supply about itself, and it shows
the load factor, the peak and the idle fraction at once, so it is the right
thing to compare against.

```python
curve = loadcast.duration_curve(profiles["heat_kw"])
```

![Load duration curves of the four process classes](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/06_duration_curves.png)

*Load duration curves of the four process classes, as a share of the peak. The
flat top is the cap that holds the load factor; the drop to near zero is the
on/off state of the campaign and batch classes.*

### The cross-correlogram

The cross-correlogram is the correlation between two carriers at each offset in
hours:

```python
correlogram = loadcast.cross_correlogram(profiles["heat_kw"],
                                         profiles["cold_kw"], max_lag=48)
```

Read where it peaks, not only how high. At zero offset, a lag and a weak
coupling look the same.

### Integrated drift

```python
loadcast.integrated_drift(profiles["heat_kw"], profiles["cold_kw"],
                          window_h=24)
```

The integrated drift is what a store responds to. A store does not see the
mismatch between two carriers hour by hour; it accumulates it, so what sizes it
is the mismatch summed over the storage window. Each carrier is divided by its
own mean first, so the drift measures timing, not size, in hours of mean
demand. The correlation is one point of this picture, and two carrier pairs
with the same correlation can differ severalfold here.

## Seeds and reproducibility

The same inputs and `seed` always give the same profiles. Another seed gives
another draw of the same site:

```python
draws = [loadcast.generate(seed=s, annual_mwh=10_000, heat_to_cold=2.0,
                           elec_share=0.2) for s in range(20)]
```

Report results across seeds, not from one draw.

## Reporting results

The inputs are yours to choose, and the package does not claim to know where
any real site sits. The defaults are indicative values with a stated source,
not predictions.

State a conclusion as it holds **across the range of inputs you swept**, not at
one assumed point. A finding that survives the whole range of plausible
correlations and lags does not depend on values nobody can measure; a finding
that holds at one setting is a statement about that setting.

Carry one limit explicitly. No site in the calibration archive meters
refrigeration, so the cold carrier's annual quantity is whatever you specify,
but its hourly shape rests on the same calendar and coupling as the other
carriers, and nothing independent confirms it.
