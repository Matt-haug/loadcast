# Usage

## The quickest thing that works

```python
import loadcast

profiles = loadcast.generate(annual_mwh=10_000, heat_to_cold=7.4,
                             elec_share=0.20)
```

`profiles` is an 8760-row hourly `DataFrame` with `heat_kw`, `cold_kw` and
`elec_kw`. Pass `year=` for a different year.

## Choosing a process class

Pick from the *process description* of the site you are modelling, not by trying
each and keeping the one that fits an answer you already have.

| class | what it looks like | anchored on |
|---|---|---|
| `continuous` | runs around the clock, modest excursions | drying, continuous mineral processing |
| `semi_continuous` | weekday shifts, weekend trough | brewing, burners |
| `campaign` | long runs separated by genuine shutdowns | chemical campaigns |
| `batch` | strongly bimodal, most hours near zero | roasting, batch kilns |

```python
for name in loadcast.available_classes():
    process = loadcast.get_class(name)
    print(name, process.description, process.target_load_factor)
```

## A site with no cooling, or no heat

```python
loadcast.generate(annual_mwh=5_000, heat_to_cold=None, elec_share=0.3)  # no cold
loadcast.generate(annual_mwh=5_000, heat_to_cold=0.0,  elec_share=0.3)  # no heat
```

## Setting the coincidence between carriers

This is the reason the package exists. Two knobs, doing different things.

```python
# how tightly the carriers move together, at peak alignment
loadcast.generate(..., carrier_correlation=0.75)

# how far apart they are offset: cold demand trails heat by six hours
loadcast.generate(..., carrier_lag_h={"cold": 6})
```

There is a floor on the correlation, because carriers share a calendar and every
one of them dips on a Sunday and in July:

```python
>>> loadcast.correlation_floor("semi_continuous")
0.434
```

Asking for less than that cannot be delivered by any non-negative knob. The
floor is the share of total variance the calendar contributes, so where it is
high the carriers move together mainly because the factory is open or shut.

### Sweeping the lag

The lag is an **exogenous design parameter**. No public archive meters process
heat and refrigeration at the same industrial site, so no heat-to-cold lag can
be estimated from data. Sweep it and report how your conclusion moves:

```python
for tau in (0, 3, 6, 12, 24):
    frame = loadcast.generate(annual_mwh=10_000, heat_to_cold=2.0,
                              elec_share=0.2, carrier_correlation=0.75,
                              carrier_lag_h={"cold": tau})
    drift = loadcast.integrated_drift(frame["heat_kw"], frame["cold_kw"], 24)
    print(tau, round(drift, 2))
```

`carrier_correlation` is defined at *peak* alignment, so this sweep changes
timing only. If it were defined at lag zero, every step would quietly change the
coupling strength as well and the result could not be attributed to the offset.

## Generating from your own measurements

If you have a metered series, or even three numbers off an annual bill:

```python
from loadcast import class_from_observations, register_class

mine = class_from_observations(
    "my_plant",
    load_factor=0.45,      # mean over peak
    cv=0.60,               # coefficient of variation of the hourly series
    lag1=0.90,             # lag-1 autocorrelation
    calendar_from="semi_continuous",   # closest shift pattern
)
register_class(mine)

profiles = loadcast.generate(process_class="my_plant", annual_mwh=5_000,
                             heat_to_cold=3.0, elec_share=0.15)
```

The calendar rhythm is borrowed, because a month-by-hour shape needs a full year
of measurement and is usually the part a user does not have. Everything else
comes from your numbers, through a closed-form inversion.

If your process genuinely stops rather than merely running low, pass
`off_fraction`. A spread alone makes a profile *low*, not *off*:

```python
class_from_observations("my_batch", 0.25, 1.1, 0.85, off_fraction=0.40)
```

## Checking what you got

```python
loadcast.summary_table(profiles)
```

|  | load_factor | cv | lag1 | idle_fraction | annual_mwh |
|---|---|---|---|---|---|
| heat_kw | 0.401 | 0.46 | 0.86 | 0.00 | 7047.6 |
| cold_kw | 0.401 | 0.46 | 0.86 | 0.00 | 952.4 |
| elec_kw | 0.401 | 0.46 | 0.86 | 0.00 | 2000.0 |

### The load duration curve

Often the only thing a site can actually supply about itself, and it encodes
load factor, peak and idle fraction at once — so it is the right thing to tune
against.

```python
curve = loadcast.duration_curve(profiles["heat_kw"])
```

### The correlogram

```python
correlogram = loadcast.cross_correlogram(profiles["heat_kw"],
                                         profiles["cold_kw"], max_lag=48)
```

Read the **position** of the peak, not only its height. A lag and a weak
coupling look identical at lag zero.

### Integrated drift

```python
loadcast.integrated_drift(profiles["heat_kw"], profiles["cold_kw"],
                          window_h=24)
```

What a store actually responds to. A buffer does not sample a mismatch, it
integrates one, so what sizes it is the area under the mismatch autocovariance
across the storage window. Correlation is one point of that. Two carrier pairs
with identical correlation can differ severalfold here.

## Reproducibility

The same `seed` and spec always give the same profiles. Change the seed to get
another draw from the same process:

```python
draws = [loadcast.generate(seed=s, annual_mwh=10_000, heat_to_cold=2.0,
                           elec_share=0.2) for s in range(20)]
```

Report results across seeds, not from one draw.

## Using it honestly

The parameters are yours to choose, and the package does not claim to know where
any real site sits. Defaults are indicative values with a stated provenance, not
predictions.

The consequence for how results should be reported: state conclusions as they
hold **across a swept space**, not at a single assumed point. A finding that
survives the whole range of plausible correlations and lags does not depend on
knowing values nobody can measure. A finding that holds only at one setting is a
statement about that setting.

One limit to carry explicitly: no site in the calibration archive meters
refrigeration. The cold carrier's annual quantity is whatever you specify, but
its hourly *shape* rests on the same calendar and correlation assumptions as the
other carriers, and nothing independent confirms it.
