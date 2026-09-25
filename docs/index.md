# loadcast

Synthetic multi-carrier industrial energy demand, with the coincidence between
carriers as an explicit input.

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

## Where to go

- **[Usage](usage.md)** — recipes, from the one-liner to fitting your own site.
- **[Mathematics](mathematics.md)** — every formula derived, with worked
  numbers and a nomenclature table. Each derivation has a matching test.

## The idea in one paragraph

Designing anything with storage against an industrial site needs to know not
only how much of each carrier the site wants, but whether it wants them at the
same hours — a store exists to bridge the gap when it does not. Published
multi-carrier industrial data cannot answer that, because it builds each carrier
as a fixed multiple of one shared profile, under which the carriers are
correlated at exactly 1 by algebra rather than by measurement. `loadcast` makes
that relationship a parameter you set and sweep.

## What is exact

- annual energy, the heat:cold ratio and the electricity share
- the load factor, via a capacity-cap fixed point
- positivity of every value

## What is exogenous

The correlation and the lag between carriers. No public archive meters process
heat and refrigeration at one industrial site, so neither can be fitted for that
pair. They are inputs, and results should be reported as they hold across a
swept range rather than at one assumed setting.
