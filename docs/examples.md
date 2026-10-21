# Examples

Every figure below comes from the
[tutorial notebook](https://github.com/Matt-haug/loadcast/blob/main/examples/01_tutorial.ipynb),
which runs from top to bottom with no data to download. A script,
[`examples/build_notebook.py`](https://github.com/Matt-haug/loadcast/blob/main/examples/build_notebook.py),
writes the notebook, so its prose, code and figures stay in one file that can
be reviewed. To regenerate it:

```bash
python examples/build_notebook.py
```

For sampled inputs rather than figures, see
[`examples/02_uncertainty.py`](https://github.com/Matt-haug/loadcast/blob/main/examples/02_uncertainty.py)
and [Sweeps and uncertainty](uncertainty.md).

## Published data couples every carrier at exactly 1

![Cross-correlogram of heat and cold: the disaggregated construction peaks at exactly 1.000, loadcast at the 0.60 asked for](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/07_coincidence.png)

Published multi-carrier data builds every carrier as a fixed multiple of one
shared profile, $P_m(t) = \kappa_m\,p(t)$. The notebook rebuilds that
construction and measures its heat–cold correlation: 1.000000. `loadcast`
puts the peak where you ask.

![Delivered correlation against the requested internal correlation, with the floor set by the shared calendar](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/07_transfer.png)

The correlation you observe is not the one the generator sets. The carriers
share a calendar, so they stay correlated even when their fluctuations are
independent. The generator sets the correlation of those fluctuations, and a
closed-form formula maps it to the correlation of the finished profiles.

## Each profile is a product of four factors

![One week of heat, cold and electricity](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/01_one_week.png)

![The profile decomposed into level, calendar, modulation and residual](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/02_decomposition.png)

Each carrier is the product
$P_m(t) = L_m \cdot S(t) \cdot M_m(t-\tau_m) \cdot R_m(t-\tau_m)$ of a level, a
calendar, an on/off state and a residual fluctuation. Every factor except the
level has mean 1, so the level alone sets the annual energy.

## Two constants keep the residual right

![AR(1) paths with and without the stationary variance factor, and the residual mean with and without the lognormal correction](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/03_two_constants.png)

Left: without the $\sqrt{1-\phi^2}$ factor, the residual takes several hundred
hours to reach its own spread. Right: without the $-\sigma^2/2$ correction, the
residual's mean grows with its spread, so widening the fluctuations would add
annual energy.

## The cap flattens the top; the on/off state makes the tail

![A fortnight of each of the four process classes](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/06_process_classes.png)

![Load duration curves for the four process classes](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/06_duration_curves.png)

The flat top of each duration curve is the cap on the peak, which holds the
load factor exactly. The on/off state gives the campaign and batch classes their
long tail of near-zero hours, which spread alone cannot produce.

## A lag looks like a weak coupling at zero offset

![Cross-correlograms as the lag between carriers grows](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/08_lag.png)

As the lag $\tau$ grows, the correlation at zero offset falls towards the
calendar floor, which is also where a weak coupling would put it. To tell the
two apart, look at where the correlogram peaks, not only how high.

## The step length does not change the site

![Two days at hourly, 30-minute and 15-minute resolution](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/10_resolution.png)

Energy, load factor and persistence measured in hours are the same on every
grid. The process classes were calibrated on hourly meters, so detail below the
hour is drawn, not measured.

## Waste heat trails the heat it comes from

![Heat demand and waste heat rejected, with the waste trailing by two hours](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/11_waste.png)

Waste heat is a by-product the site rejects, not energy it buys, so
`waste_to_heat` sizes it from the heat demand. It has its own residual and can
take its own lag; here it trails the heat by two hours.

## Refitting on generated output degrades a class

![Persistence ratcheting up and spread decaying over repeated refits, while the load factor stays flat](https://raw.githubusercontent.com/Matt-haug/loadcast/main/examples/figures/12_degeneration.png)

Refit a class on its own generated output, round after round, and its
persistence climbs towards a fixed point while its spread drains away. The load
factor is imposed, so it stays flat and gives no warning.
