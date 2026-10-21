# The mathematics

This page derives every formula the generator uses, in the order the generator
applies them. A test in `tests/test_identities.py` checks each step. Where a
formula is exact, the test is tight; where it holds only on average over many
draws, the test says so and gives its tolerance.

Nothing on this page is new time-series theory. The building blocks are
textbook ones: a first-order autoregression, its exponential, correlated
Gaussian series, and the cutting of a Gaussian series into an on/off one. Box
et al. (2015) treat the autoregression and its correlation structure at length.
What `loadcast` adds is the way these pieces are put together, so that the
statistics a user chooses (load factor, spread, persistence, coupling between
carriers) come out as asked.

## Nomenclature

| symbol | meaning | units |
|---|---|---|
| $t$ | time step index (an hour, unless stated) | h |
| $m$ | carrier: heat, cold or electricity | — |
| $P_m(t)$ | demand for carrier $m$ at step $t$ | kW |
| $L_m$ | level of carrier $m$, which sets its annual energy | kW |
| $S(t)$ | calendar factor, mean one | — |
| $M_m(t)$ | on/off state: 1 when running, $\lambda$ when idle | — |
| $R_m(t)$ | residual fluctuation, mean one | — |
| $z_m(t)$ | latent series behind $R_m$: a hidden Gaussian series the generator draws, then transforms | — |
| $w_m(t)$ | latent series behind $M_m$ | — |
| $\varepsilon(t)$ | random shock that drives the latent series | — |
| $\tau_m$ | lag of carrier $m$ | h |
| $\sigma$ | spread of the latent series (its standard deviation) | — |
| $\phi$ | persistence of the latent series: its lag-1 coefficient | — |
| $\rho$ | correlation between the carriers' latent series, which the generator sets | — |
| $\rho_R(u)$ | correlation of the residuals $u$ steps apart | — |
| $q$ | shorthand for $\rho_R\,\mathrm{CV}_R^2$, the residuals' covariance | — |
| $\alpha$ | fraction of hours in the off state | — |
| $q_\alpha(w)$ | the $\alpha$-quantile of $w$ | — |
| $\lambda$ | load in the off state, relative to running | — |
| $\eta$ | load factor: mean demand over peak demand | — |
| $E$ | annual energy | MWh |
| $k$ | ratio of annual heat to annual cold | — |
| $s_h, s_c, s_e$ | annual shares of heat, cold and electricity | — |
| $\mathrm{CV}[X]$ | coefficient of variation, $\operatorname{sd}[X]/\mathbb{E}[X]$ | — |
| $\mathrm{CV}_S, \mathrm{CV}_R, \mathrm{CV}_{\text{tot}}$ | coefficient of variation of the calendar, the residual and the finished profile | — |
| $\gamma(\ell)$ | correlation of two finished carriers $\ell$ steps apart | — |
| $a_S(\ell)$ | correlation of the calendar with itself $\ell$ steps apart | — |
| $\ell$, $u$ | offsets, in steps | — |
| $T$ | storage window | h |
| $d(t)$ | mismatch between heat and cold, each divided by its mean | — |
| $C_d(u)$ | autocovariance of the mismatch at offset $u$ | — |
| $h$ | length of one step | h |
| $N$ | number of steps in the year (8760 for hourly steps) | — |
| $i$ | iteration of the cap | — |

---

## 1. Why the generator is a product

$$
P_m(t) = L_m \cdot S(t) \cdot M_m(t-\tau_m) \cdot R_m(t-\tau_m)
$$

where $L_m$ is the level, $S$ the calendar, $M_m$ the on/off state, $R_m$ the
residual and $\tau_m$ the lag of carrier $m$.

The factors multiply rather than add, because a multiplicative factor has no
unit. "Plus or minus 50 kW" means something different at a 200 kW site and at a
20 MW one, so additive noise must be retuned for every plant; it can also drive
the load negative, which several published generators allow.

Every factor on the right has mean one, so $L_m$ alone carries the level. That
makes the annual energy exact rather than approximate: nothing applied after
$L_m$ can shift it.

## 2. The residual, and its two constants

The residual is a first-order autoregression, AR(1), passed through an
exponential. In an AR(1), each step keeps a fraction $\phi$ of the previous
step's value and adds a random shock:

$$
z(t) = \phi\,z(t-1) + \varepsilon(t), \qquad
\varepsilon \sim \mathcal{N}\!\big(0,\ \sigma^2(1-\phi^2)\big)
$$

$$
R(t) = \exp\!\Big(z(t) - \tfrac{1}{2}\sigma^2\Big)
$$

where $\phi \in [0,1)$ sets how long an excursion lasts and $\sigma$ how wide it
is. Two constants in these formulas keep the series right from its first hour
and keep its mean at one.

**The factor $\sqrt{1-\phi^2}$ on the shock.** An AR(1) driven by shocks of
variance $s^2$ settles at a variance of $s^2/(1-\phi^2)$. Choosing
$s^2 = \sigma^2(1-\phi^2)$ makes that settled variance exactly $\sigma^2$, and
drawing $z(0)$ from the same distribution removes the warm-up altogether.
Without it the series starts at zero variance and grows into its spread; at
$\phi = 0.97$ that leaves several hundred hours of the year too calm.

**The term $-\sigma^2/2$ in the exponent.** For $z \sim \mathcal{N}(0,\sigma^2)$,

$$
\mathbb{E}[e^{z}] = e^{\sigma^2/2}
$$

which exceeds one and grows with the spread. Subtracting $\sigma^2/2$ gives
$\mathbb{E}[R] = 1$ exactly, so widening the residual cannot inflate the annual
energy.

## 3. Reading $\sigma$ and $\phi$ off a measurement

A meter gives the spread and the persistence of the demand, not $\sigma$ and
$\phi$. For $R = \exp(z)$, with $z$ a stationary Gaussian AR(1), the two are
linked by

$$
\mathrm{CV}[R] = \sqrt{e^{\sigma^2} - 1},
\qquad
\rho_R(1) = \frac{e^{\phi\sigma^2} - 1}{e^{\sigma^2} - 1}
$$

where $\rho_R(1)$ is the lag-1 autocorrelation of the residual itself, not of
its latent series. Both invert in closed form:

$$
\boxed{\ \sigma^2 = \ln\!\big(1 + \mathrm{CV}^2\big),
\qquad
\phi = \frac{\ln\!\big(1 + \rho_R(1)\,(e^{\sigma^2}-1)\big)}{\sigma^2}\ }
$$

So you supply two things a meter tells you, how variable the load is and how
long its excursions last, and the generator's parameters follow with no
optimiser, no starting guess and no local minimum.

*Worked example.* A site with $\mathrm{CV} = 0.40$ and $\rho_R(1) = 0.85$ gives
$\sigma^2 = \ln(1.16) = 0.1484$, so $\sigma = 0.385$, and
$\phi = \ln(1 + 0.85 \times 0.1600)/0.1484 = 0.861$. Note that
$\phi > \rho_R(1)$: the exponential weakens correlation, so the latent series
must be more persistent than the series you observe.

The same transform applies to any correlation, not only the lag-1 one:

$$
\rho_R = \frac{e^{\rho\sigma^2} - 1}{e^{\sigma^2} - 1}
$$

with $\rho$ the correlation of the latent series. Setting $\rho = \phi$
recovers the formula above; a general $\rho$ gives the correlation between
carriers in §6.

## 4. Spreads multiply, they do not add

The calendar has a spread of its own, and it multiplies with the residual's.
With $S$ and $R$ independent and $\mathbb{E}[R] = 1$:

$$
\mathbb{E}[SR] = \mathbb{E}[S],
\qquad
\mathbb{E}[(SR)^2] = \mathbb{E}[S^2]\,\mathbb{E}[R^2]
$$

Dividing the second by $\mathbb{E}[S]^2$ and using
$\mathbb{E}[R^2] = 1 + \mathrm{CV}_R^2$:

$$
\boxed{\ 1 + \mathrm{CV}_{\text{tot}}^2
= \big(1 + \mathrm{CV}_S^2\big)\big(1 + \mathrm{CV}_R^2\big)\ }
$$

**One plus the squared coefficient of variation is what multiplies.** The
residual therefore has to supply only the spread the calendar has not already
produced:

$$
\mathrm{CV}_R = \sqrt{\frac{1 + \mathrm{CV}_{\text{tot}}^2}{1 + \mathrm{CV}_S^2} - 1}
$$

*Worked example.* The `semi_continuous` class has a calendar spread
$\mathrm{CV}_S = 0.315$ and a target total of $\mathrm{CV}_{\text{tot}} = 0.478$.
The residual needs $\mathrm{CV}_R = \sqrt{1.2285/1.0992 - 1} = 0.343$, hence
$\sigma = 0.334$. Fitting the residual on the measured series instead, feeding
0.478 straight in, would land the finished profile near 0.57, about 20% too
wide, because the calendar's spread would be counted twice.

## 5. The on/off state, and the cap on the peak

**The on/off state.** A batch process is bimodal: it runs or it stops, and
spread alone can make a profile low but never off. A second latent series
$w_m$, with the same $\phi$ and $\rho$, is cut at its own empirical quantile:

$$
M_m(t) =
\begin{cases}
1 & w_m(t) > q_\alpha(w_m)\\
\lambda & \text{otherwise}
\end{cases}
$$

where $\alpha$ is the off fraction and $\lambda$ the idle level. Cutting at the
quantile measured on the series itself makes the off fraction exactly $\alpha$.

Cutting a correlated Gaussian series to make a binary one is called a Gaussian
copula. The alternative is a Markov chain, a table of probabilities of switching
on or off from one hour to the next. The copula needs no such table: the binary
state inherits both the persistence of $w_m$ and its correlation with the other
carriers. $\lambda > 0$ because real plants idle rather than stop.

**The cap.** A plant cannot draw more than it has installed, so its load
duration curve has a hard ceiling, which a lognormal series lacks. The generator
caps the profile and restores its energy, in turn:

$$
\tilde P^{(i)} = \min\!\left(P^{(i)},\ \frac{\overline{P^{(i)}}}{\eta}\right),
\qquad
P^{(i+1)} = \tilde P^{(i)}\cdot\frac{E}{\sum_t \tilde P^{(i)}(t)}
$$

where $\eta$ is the target load factor, $E$ the annual energy and $i$ the
iteration. Capping lowers the mean, which lowers the cap, so the two steps must
repeat; each pass moves the profile less than the one before, and a few passes
converge. At the converged point, the fixed point of the iteration, the load
factor is $\eta$ and the energy is $E$, both exactly.

The cap is what gets the highest hours right. Without it the coefficient of
variation can be correct while the top of the load duration curve is badly
wrong, and that top is what sizes equipment.

## 6. The correlation you set is not the one you observe

Carriers share a calendar, so the finished profiles are correlated even when
their residuals are independent: every carrier dips on a Sunday and in July.
Writing $q = \rho_R\,\mathrm{CV}_R^2$, the finished correlation is

$$
\boxed{\ \gamma(0) =
\frac{\mathrm{CV}_S^2 + q + \mathrm{CV}_S^2\,q}{\mathrm{CV}_{\text{tot}}^2}\ }
$$

*Derivation.* With $P_m = L_m S R_m$ and $S$ independent of $R$,

$$
\frac{\operatorname{Cov}(P_h,P_c)}{\mathbb{E}[S]^2}
= \frac{\mathbb{E}[S^2]\,\mathbb{E}[R_hR_c]}{\mathbb{E}[S]^2} - 1
= (1+\mathrm{CV}_S^2)(1+q) - 1
$$

using $\mathbb{E}[R_hR_c] = 1 + \rho_R\mathrm{CV}_R^2$. Dividing by
$\operatorname{Var}(P_m)/\mathbb{E}[S]^2 = \mathrm{CV}_{\text{tot}}^2$ gives the
boxed result.

Set $q = 0$, residuals independent, and a floor appears:

$$
\boxed{\ \gamma(0)\big|_{\rho=0} = \frac{\mathrm{CV}_S^2}{\mathrm{CV}_{\text{tot}}^2}\ }
$$

**The correlation floor is the share of total variance that the shared
calendar contributes.** It is a statement about industry: where the floor is
high, carriers move together mainly because the factory is open or shut, not
because the processes are physically linked.

| class | $\mathrm{CV}_S$ | $\mathrm{CV}_{\text{tot}}$ | floor |
|---|---|---|---|
| `continuous` | 0.247 | 0.409 | 0.36 |
| `semi_continuous` | 0.315 | 0.478 | 0.43 |
| `campaign` | 0.146 | 0.527 | 0.08 |
| `batch` | 0.944 | 1.177 | 0.64 |

No non-negative $\rho$ reaches a correlation below the floor.

The closed form is exact without the on/off state and the cap; both shift it.
The generator therefore finds the $\rho$ that delivers `carrier_correlation` by
bisection, generating a year at each trial value, and uses this expression to
explain and diagnose.

## 7. The lag

Carrier $m$'s on/off state and residual are shifted by $\tau_m$ hours, while the
calendar is shared and **not** shifted: a factory's opening hours are common to
all its carriers, so only the process fluctuation is offset. The shift wraps
around the end of the year, so it only reorders the hours, and every statistic
of the shifted carrier taken on its own is unchanged. The lag acts only on how
the carriers relate.

The latent series' cross-correlogram is exactly $\rho\,\phi^{|\ell-\tau|}$, so
the finished profiles have

$$
\gamma(\ell) =
\frac{\mathrm{CV}_S^2\,a_S(\ell) + q(\ell-\tau)
+ \mathrm{CV}_S^2\,a_S(\ell)\,q(\ell-\tau)}{\mathrm{CV}_{\text{tot}}^2}
$$

where $a_S(\ell)$ is the calendar's own autocorrelation at offset $\ell$ and
$q(u) = \mathrm{CV}_R^2\,\rho_R(u)$ decays like $\phi^{|u|}$.

**A single correlation cannot tell a lag from a weak coupling.** Evaluate at
$\ell = 0$, the number anyone would report:

$$
\gamma(0) = \frac{\mathrm{CV}_S^2 + q(\tau) + \mathrm{CV}_S^2 q(\tau)}
{\mathrm{CV}_{\text{tot}}^2},
\qquad q(\tau) \propto \phi^{\tau}
$$

As $\tau$ grows, $\gamma(0)$ falls towards the calendar floor, exactly where a
small $\rho$ would also put it. A single reported correlation therefore does not
identify a multi-carrier demand model; only the correlogram separates the two.

The package acts on two consequences:

1. The lag is an **input, not a fitted value**. No public archive meters heat and
   refrigeration at one industrial site, so no heat-to-cold lag can be fitted,
   and the lag must be swept.
2. `carrier_correlation` is defined at **peak alignment**, the offset where the
   carriers match best, and $\rho$ is solved at zero lag. A lag sweep then
   changes timing only, without changing the coupling strength at the same time.

Measured on generated output, with $\rho$ chosen for a peak of 0.75:

| $\tau$ | peak position | peak $\gamma$ | $\gamma(0)$ |
|---|---|---|---|
| 0 h | +0 h | 0.747 | 0.747 |
| 3 h | +3 h | 0.711 | 0.588 |
| 6 h | +6 h | 0.683 | 0.507 |
| 12 h | +12 h | 0.622 | 0.435 |

At $\tau = 12$ h the correlation at zero offset has fallen to 0.435, against a
predicted floor of 0.434.

## 8. A store responds to the area, not the point

Take a store sized on the mismatch between heat and cold,
$d(t) = P_h(t)/\bar P_h - P_c(t)/\bar P_c$, where $P_h$ and $P_c$ are the heat
and cold demands and $\bar P_h$, $\bar P_c$ their means. What matters to it is
not the gap in one hour but the gap summed over its window:

$$
\operatorname{Var}\!\left(\sum_{t=1}^{T} d(t)\right)
= \sum_{|u| < T} (T - |u|)\; C_d(u)
$$

where $C_d(u)$ is the autocovariance of the mismatch at offset $u$ and $T$ the
storage window. The right-hand side weighs the whole autocovariance, more
heavily near zero offset; the correlation between the carriers enters only
through $C_d(0)$, a single point of it.

Two carrier pairs with the same correlation can therefore need very different
amounts of storage, and the lag is the most direct handle on the difference.
`loadcast.integrated_drift` reports the summed mismatch directly.

## 9. The composition

Three shares summing to one form a composition, so only two of them are free.
Given the heat-to-cold ratio $k$ and the electricity share $s_e$:

$$
s_c = \frac{1 - s_e}{1 + k}, \qquad s_h = k\,s_c, \qquad s_h + s_c + s_e = 1
$$

exactly, by construction. A ratio and a share are easier to answer from a site
visit than three shares, and they cannot be inconsistent. The level of each
carrier is then

$$
L_m = \frac{1000\,E\,s_m}{N}\cdot\frac{1}{\overline{P_m^{\text{shape}}}}
\qquad\Longrightarrow\qquad
\sum_t P_m(t)\,h = 1000\,E\,s_m
$$

for hourly steps ($h$ = 1 h), where $\overline{P_m^{\text{shape}}}$ is the mean
of the product of the other factors, and the 1000 converts MWh to kWh; §10
gives the general case.

`DemandSpec.from_composition` refuses a composition that does not sum to one
rather than rescaling it. A silent rescaling moves the point, and the case you
solved is then not the case you plotted.

## 10. Resolution: hourly, half-hourly, quarter-hourly

The step length changes how a site is drawn, not the site itself. Three things
must therefore survive a change of step, and one cannot.

**Persistence must be rescaled.** $\phi$ applies per *step*, but persistence is
a property of time. An AR(1) correlation decays as $\phi^n$ over $n$ steps, so a
series sampled every $h$ hours needs

$$
\phi_{\text{step}} = \phi_{\text{hourly}}^{\,h}
$$

to keep the same correlation at the same separation in time. Without it, a
quarter-hourly profile would remember four times longer in real time, and its
excursions would last four times as long as on the site it was calibrated on.
Measured on generated output, the persistence converted back to an hourly
basis, $\rho(1)^{\,1/h}$, comes out at 0.857, 0.861 and 0.859 for hourly,
half-hourly and quarter-hourly steps: the same site on three grids.

**Energy is power times elapsed hours**, not power times the number of steps:

$$
L_m = \frac{1000\,E\,s_m}{N\,h}\cdot\frac{1}{\overline{P_m^{\text{shape}}}}
$$

so the mean power is unchanged when the number of steps quadruples.

**A lag is given in hours** and converted to $\tau/h$ steps, so the correlogram
peaks at the same offset in time at any resolution.

**The calibration does not transfer.** The process classes were calibrated on
hourly meters, so their spread and persistence describe hourly behaviour.
Asking for 15-minute steps draws those hourly statistics on a finer grid; it
adds no measured sub-hourly structure, because none was measured. The calendar
likewise resolves only to the hour of day, so every step within an hour carries
the same calendar factor, and all sub-hourly variation comes from the residual.

## 11. What is imposed, what is aimed at, and why you must not iterate

Two of the four statistics are **imposed** by construction and come out exact:
the load factor, through the cap, and the annual energy, through the level. The
other two are **aimed at**: $\sigma$ and $\phi$ are chosen to produce a target
spread and persistence, but the on/off state and the cap both act after them,
so the finished profile lands near its targets rather than on them.

`loadcast.bias_report()` prints the gap, averaged over four seeds. It is
systematic, and its sign differs between classes:

| class | CV target | CV mean | CV bias | lag-1 target | lag-1 mean | lag-1 bias |
|---|---|---|---|---|---|---|
| `continuous` | 0.409 | 0.363 | −0.046 | 0.973 | 0.974 | +0.001 |
| `semi_continuous` | 0.478 | 0.466 | −0.012 | 0.793 | 0.866 | **+0.073** |
| `batch` | 1.177 | 1.409 | **+0.232** | 0.848 | 0.759 | **−0.089** |
| `campaign` | 0.527 | 0.525 | −0.002 | 0.957 | 0.792 | **−0.165** |

The sign of the persistence bias has a mechanism. The cap trims the peaks that
would otherwise break up a run, so a profile without an on/off state comes out
more persistent than asked; the on/off state chops runs into pieces, so a
profile with one comes out less persistent. The batch class also comes out a
fifth wider than its target spread.

### Why this forbids one particular loop

A systematic bias does no harm when applied once. It does harm when applied
repeatedly. Measure a generated profile, feed its statistics back into
`class_from_observations`, regenerate, and the offset compounds. Starting from
`semi_continuous`:

| round | load factor | CV | lag-1 |
|---|---|---|---|
| measured site | 0.401 | 0.478 | 0.793 |
| 1 | 0.401 | 0.462 | 0.861 |
| 2 | 0.401 | 0.454 | 0.911 |
| 3 | 0.401 | 0.437 | 0.936 |
| 4 | 0.401 | 0.431 | 0.952 |
| 6 | 0.401 | 0.428 | 0.969 |
| 8 | 0.401 | 0.422 | 0.970 |

Persistence climbs to a fixed point near 0.97 while the spread drains from 0.48
to 0.42: the profile grows smoother and more persistent every round, until it
has lost the hour-to-hour variability it was meant to have. The load factor
never moves, because it is imposed, and so it gives no warning that the other
statistics are drifting.

Any model retrained on its own output degrades this way, and the AR(1) is not
what fails. The process is stationary by construction: $\operatorname{Var}[z_t]
= \sigma^2$ for every $t$, started from that distribution, with $|\phi| < 1$. It
cannot drift or collapse over any horizon, at any resolution, and a test
asserts it. What degrades is the *estimation loop* wrapped around it.

The package never closes that loop. The shipped classes hold constants measured
once, and no code path writes generated statistics back into a class. Holding
the targets fixed and varying only the seed is stable, as it must be:

| seed | load factor | CV | lag-1 |
|---|---|---|---|
| 1 | 0.401 | 0.459 | 0.863 |
| 4 | 0.401 | 0.476 | 0.877 |
| 8 | 0.401 | 0.479 | 0.871 |

So vary the seed for another draw of the same site; never refit on the output.

## Reference

Box GEP, Jenkins GM, Reinsel GC, Ljung GM. *Time Series Analysis: Forecasting
and Control*, 5th edition. Wiley, Hoboken, NJ, 2015. ISBN 978-1-118-67502-1.
