# The mathematics

Every step below is checked by a test in `tests/test_identities.py`. Where a
formula is exact, the test is tight; where it is exact only in expectation, the
test says so and gives the tolerance.

## Nomenclature

| symbol | meaning | units |
|---|---|---|
| $t$ | hour index | h |
| $m$ | carrier, one of heat, cold, electricity | — |
| $P_m(t)$ | demand for carrier $m$ at hour $t$ | kW |
| $L_m$ | level of carrier $m$ | kW |
| $S(t)$ | calendar factor, mean one | — |
| $M_m(t)$ | on/off state, 1 running or $\lambda$ idle | — |
| $R_m(t)$ | residual fluctuation, mean one | — |
| $z_m(t)$ | latent Gaussian process behind $R_m$ | — |
| $\tau_m$ | lag of carrier $m$ | h |
| $\sigma$ | log-space spread of the residual | — |
| $\phi$ | lag-1 coefficient of the latent | — |
| $\rho$ | cross-carrier correlation of the latents (the knob) | — |
| $\rho_R$ | cross-carrier correlation of the residuals | — |
| $\alpha$ | fraction of hours in the off state | — |
| $\lambda$ | load in the off state, relative to running | — |
| $\eta$ | load factor: mean over peak | — |
| $E$ | annual energy | MWh |
| $k$ | heat:cold ratio | — |
| $s_h, s_c, s_e$ | annual shares of heat, cold, electricity | — |
| $\mathrm{CV}[X]$ | coefficient of variation, $\operatorname{sd}[X]/\mathbb{E}[X]$ | — |
| $\gamma(\ell)$ | cross-correlation of two carriers at lag $\ell$ | — |

---

## 1. Why the generator is a product

$$
P_m(t) = L_m \cdot S(t) \cdot M_m(t-\tau_m) \cdot R_m(t-\tau_m)
$$

where $L_m$ is the level, $S$ the calendar, $M_m$ the on/off state, $R_m$ the
residual and $\tau_m$ the lag of carrier $m$.

The factors *multiply* rather than add because a multiplicative factor is
dimensionless. "Plus or minus 50 kW" means something different at a 200 kW site
and a 20 MW one, so additive noise has to be retuned for every plant — and it
can drive the load negative, which several published generators do.

Every factor on the right has mean one, so $L_m$ alone carries the level. That
is what makes the annual energy exact rather than approximate: nothing
downstream of $L_m$ can drift it.

## 2. The residual, and its two constants

The residual is a Gaussian autoregression, exponentiated:

$$
z(t) = \phi\,z(t-1) + \varepsilon(t), \qquad
\varepsilon \sim \mathcal{N}\!\big(0,\ \sigma^2(1-\phi^2)\big)
$$

$$
R(t) = \exp\!\Big(z(t) - \tfrac{1}{2}\sigma^2\Big)
$$

where $\phi \in [0,1)$ sets how long an excursion lasts and $\sigma$ how wide it
is. The two constants are not cosmetic.

**The factor $\sqrt{1-\phi^2}$ on the innovation.** An AR(1) driven by
innovations of variance $s^2$ settles at stationary variance $s^2/(1-\phi^2)$.
Choosing $s^2 = \sigma^2(1-\phi^2)$ makes the stationary variance exactly
$\sigma^2$, and drawing $z(0)$ from that same distribution removes the burn-in
entirely. Without it the series starts at zero variance and grows into its
spread; at $\phi = 0.97$ that is several hundred hours of a year quietly wrong.

**The term $-\sigma^2/2$ in the exponent.** For $z \sim \mathcal{N}(0,\sigma^2)$,

$$
\mathbb{E}[e^{z}] = e^{\sigma^2/2}
$$

which is greater than one and grows with the spread. Subtracting $\sigma^2/2$
gives $\mathbb{E}[R] = 1$ exactly, so widening the noise cannot inflate the
annual energy.

## 3. Reading $\sigma$ and $\phi$ off a measurement

This is the step that makes it a demand generator rather than a signal
generator. For $R = \exp(z)$ with $z$ a stationary Gaussian AR(1):

$$
\mathrm{CV}[R] = \sqrt{e^{\sigma^2} - 1},
\qquad
\rho_R(1) = \frac{e^{\phi\sigma^2} - 1}{e^{\sigma^2} - 1}
$$

where $\rho_R(1)$ is the lag-1 autocorrelation of the *series*, not of the
latent. Both invert in closed form:

$$
\boxed{\ \sigma^2 = \ln\!\big(1 + \mathrm{CV}^2\big),
\qquad
\phi = \frac{\ln\!\big(1 + \rho_R(1)\,(e^{\sigma^2}-1)\big)}{\sigma^2}\ }
$$

So you supply two things a meter tells you — how variable the load is, and how
long its excursions last — and the generator parameters follow with no
optimiser, no starting guess and no local minimum.

*Worked example.* A site with $\mathrm{CV} = 0.40$ and $\rho_R(1) = 0.85$ gives
$\sigma^2 = \ln(1.16) = 0.1484$, so $\sigma = 0.385$, and
$\phi = \ln(1 + 0.85 \times 0.1600)/0.1484 = 0.861$. Note $\phi > \rho_R(1)$:
the exponential compresses correlation, so the latent must be *more* persistent
than the series you observe.

The same transform applies to any correlation, not just the lag-1 one:

$$
\rho_R = \frac{e^{\rho\sigma^2} - 1}{e^{\sigma^2} - 1}
$$

with $\rho$ the correlation of the latents. Setting $\rho = \phi$ recovers the
formula above; a general $\rho$ gives the cross-carrier case in §6.

## 4. Spread does not add — it multiplies

The calendar carries variance of its own, and it multiplies with the residual's.
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

**One plus the squared coefficient of variation is what multiplies.** So the
residual only has to supply the spread the calendar has not already produced:

$$
\mathrm{CV}_R = \sqrt{\frac{1 + \mathrm{CV}_{\text{tot}}^2}{1 + \mathrm{CV}_S^2} - 1}
$$

*Worked example.* The `semi_continuous` class has a calendar spread
$\mathrm{CV}_S = 0.315$ and a target total of $\mathrm{CV}_{\text{tot}} = 0.478$.
The residual needs $\mathrm{CV}_R = \sqrt{1.2285/1.0992 - 1} = 0.343$, hence
$\sigma = 0.334$. Fitting the residual directly on the measured series instead —
feeding 0.478 straight in — would land the finished profile near 0.57, about
20% too wide, because the calendar's spread would be counted twice.

## 5. The on/off mask, and the capacity cap

**The mask.** A batch process is bimodal: spread alone cannot make a profile
*off* rather than merely low. A second latent $w_m$, sharing $\phi$ and $\rho$,
is thresholded at its own empirical quantile:

$$
M_m(t) =
\begin{cases}
1 & w_m(t) > q_\alpha(w_m)\\
\lambda & \text{otherwise}
\end{cases}
$$

where $\alpha$ is the off fraction and $\lambda$ the idle level. Using the
*empirical* quantile makes the realised off fraction exactly $\alpha$.

This is a Gaussian copula rather than an explicit Markov chain, and that is the
point: thresholding a persistent, cross-correlated latent yields a binary state
that inherits both the persistence and the cross-carrier correlation for free,
with no transition matrix to estimate. $\lambda > 0$ because real plants idle
rather than stop.

**The cap.** A plant cannot draw more than it has installed, so its load
duration curve has a hard ceiling; a lognormal has none. Cap and restore the
energy alternately:

$$
\tilde P^{(k)} = \min\!\left(P^{(k)},\ \frac{\overline{P^{(k)}}}{\eta}\right),
\qquad
P^{(k+1)} = \tilde P^{(k)}\cdot\frac{E}{\sum_t \tilde P^{(k)}(t)}
$$

where $\eta$ is the target load factor and $E$ the annual energy. Capping lowers
the mean, which lowers the cap, so it must iterate — but the map is a
contraction and converges in a few passes. At the fixed point the load factor is
$\eta$ and the energy is $E$, both exactly.

This is the step that makes the *extreme quantiles* right. Without it the
coefficient of variation can be correct while the top of the load duration curve
is badly wrong, which is exactly the region that sizes equipment.

## 6. The cross-carrier knob is not the observable

Carriers share a calendar, so the finished profiles are correlated even when
their residuals are independent — everything dips on a Sunday and in July.
Writing $q = \rho_R\,\mathrm{CV}_R^2$, the finished correlation is

$$
\boxed{\ \gamma(0) =
\frac{\mathrm{CV}_S^2 + q + \mathrm{CV}_S^2\,q}{\mathrm{CV}_{\text{tot}}^2}\ }
$$

*Derivation.* With $P_m = L_m S R_m$ and $S \perp R$,

$$
\frac{\operatorname{Cov}(P_h,P_c)}{\mathbb{E}[S]^2}
= \frac{\mathbb{E}[S^2]\,\mathbb{E}[R_hR_c]}{\mathbb{E}[S]^2} - 1
= (1+\mathrm{CV}_S^2)(1+q) - 1
$$

using $\mathbb{E}[R_hR_c] = 1 + \rho_R\mathrm{CV}_R^2$. Dividing by
$\operatorname{Var}(P_m)/\mathbb{E}[S]^2 = \mathrm{CV}_{\text{tot}}^2$ gives the
boxed result.

Set $q = 0$ — statistically independent residuals — and a floor appears:

$$
\boxed{\ \gamma(0)\big|_{\rho=0} = \frac{\mathrm{CV}_S^2}{\mathrm{CV}_{\text{tot}}^2}\ }
$$

**The correlation floor is the share of total variance the shared calendar
contributes.** Read as a statement about industry rather than as plumbing: where
the floor is high, carriers move together mainly because the factory is open or
shut, not because the processes are physically linked.

| class | $\mathrm{CV}_S$ | $\mathrm{CV}_{\text{tot}}$ | floor |
|---|---|---|---|
| `continuous` | 0.247 | 0.409 | 0.36 |
| `semi_continuous` | 0.315 | 0.478 | 0.43 |
| `campaign` | 0.146 | 0.527 | 0.08 |
| `batch` | 0.944 | 1.177 | 0.64 |

A correlation below the floor cannot be reached with any non-negative knob.

The closed form is exact for the unmasked model; the on/off mask and the
capacity cap shift it, so the production path solves for the knob by bisection
and uses this expression for explanation and diagnosis.

## 7. The lag

Carrier $m$'s stochastic part is shifted by $\tau_m$ hours, while the calendar
is shared and **not** shifted — a factory's opening hours are common to all its
carriers, so only the process fluctuation is offset. Because a circular shift is
a permutation, every marginal statistic of the shifted carrier is unchanged: the
lag is a pure cross-carrier knob.

The latent cross-correlogram is exactly $\rho\,\phi^{|\ell-\tau|}$, so the
finished profiles have

$$
\gamma(\ell) =
\frac{\mathrm{CV}_S^2\,a_S(\ell) + q(\ell-\tau)
+ \mathrm{CV}_S^2\,a_S(\ell)\,q(\ell-\tau)}{\mathrm{CV}_{\text{tot}}^2}
$$

where $a_S(\ell)$ is the calendar's own autocorrelation at lag $\ell$ and
$q(u) = \mathrm{CV}_R^2\,\rho_R(u)$ decays like $\phi^{|u|}$.

**The identifiability problem.** Evaluate at $\ell = 0$, the number anyone would
actually report:

$$
\gamma(0) = \frac{\mathrm{CV}_S^2 + q(\tau) + \mathrm{CV}_S^2 q(\tau)}
{\mathrm{CV}_{\text{tot}}^2},
\qquad q(\tau) \propto \phi^{\tau}
$$

As $\tau$ grows, $\gamma(0)$ decays towards the calendar floor — exactly where a
small $\rho$ would also put it. **A lag and a weak coupling are
indistinguishable from the contemporaneous correlation alone.** A single
reported correlation therefore does not identify a multi-carrier demand model;
only the correlogram separates them.

Two consequences, both of which the package acts on:

1. The lag is **exogenous**. No public archive meters heat and refrigeration at
   one industrial site, so no heat-to-cold lag can be fitted. Sweeping it is
   the honest treatment.
2. `carrier_correlation` is defined at **peak alignment**, and the knob is
   solved at zero lag. A lag sweep then changes timing only, rather than
   quietly changing coupling strength at the same time.

Measured on generated output at $\rho$ chosen for a peak of 0.75:

| $\tau$ | peak position | peak $\gamma$ | $\gamma(0)$ |
|---|---|---|---|
| 0 h | +0 h | 0.747 | 0.747 |
| 3 h | +3 h | 0.711 | 0.588 |
| 6 h | +6 h | 0.683 | 0.507 |
| 12 h | +12 h | 0.622 | 0.435 |

At $\tau = 12$ the contemporaneous correlation has fallen to 0.435 against a
predicted floor of 0.434.

## 8. Why a store cares about the area, not the point

For a buffer sized on the mismatch $m(t) = h(t)/\bar h - c(t)/\bar c$, what
matters is not the instantaneous gap but its running integral:

$$
\operatorname{Var}\!\left(\sum_{s=1}^{T} m(s)\right)
= \sum_{|u| < T} (T - |u|)\; C_m(u)
$$

where $C_m(u)$ is the autocovariance of the mismatch and $T$ the storage
window — a triangularly weighted sum over the whole correlogram. Correlation is
$C_m(0)$, a single point of it.

So two carrier pairs with identical contemporaneous correlation can demand very
different amounts of buffering, and the lag is the most direct handle on the
difference. `loadcast.integrated_drift` reports this quantity directly.

## 9. The composition

Three shares summing to one is a composition, so only two numbers are free.
Given the heat:cold ratio $k$ and the electricity share $s_e$:

$$
s_c = \frac{1 - s_e}{1 + k}, \qquad s_h = k\,s_c, \qquad s_h + s_c + s_e = 1
$$

exactly, by construction. Asking for $(k, s_e)$ rather than three shares is both
easier to answer from a site visit and impossible to make inconsistent. The
level of each carrier is then

$$
L_m = \frac{1000\,E\,s_m}{|T|}\cdot\frac{1}{\overline{P_m^{\text{shape}}}}
\qquad\Longrightarrow\qquad
\sum_t P_m(t)\,\Delta t = E\,s_m
$$

`DemandSpec.from_composition` refuses a composition that does not sum to one
rather than renormalising, because silently moving the point means the case you
solved is not the case you plotted.

## 10. Resolution: hourly, half-hourly, quarter-hourly

Resolution is a rendering choice, not a change of site, so three things must
survive it and one must not.

**Persistence must be rescaled.** $\phi$ is a per-*step* coefficient, but
persistence is a property of time. An AR(1) autocorrelation decays as $\phi^k$
over $k$ steps, so a series sampled every $h$ hours needs

$$
\phi_{\text{step}} = \phi_{\text{hourly}}^{\,h}
$$

to keep the same correlation at the same wall-clock separation. Without this a
quarter-hourly profile carries four times the memory in real time, and its
excursions last four times as long as the site it was calibrated on. Measured on
generated output, the hourly-equivalent persistence
$\rho(1)^{\,1/h}$ comes out 0.857, 0.861 and 0.859 at hourly, half-hourly and
quarter-hourly — the same site, three grids.

**Energy is power times elapsed hours**, not power times step count:

$$
L_m = \frac{1000\,E\,s_m}{|T|\cdot h}
$$

so the mean power is unchanged when the step count quadruples.

**A lag is given in hours** and converted to $\tau/h$ steps, so the correlogram
peak sits at the same wall-clock offset at any resolution.

What does *not* transfer is the claim. The process classes were calibrated on
hourly meters, so their spread and persistence describe hourly behaviour. Asking
for 15-minute steps renders those hourly statistics on a finer grid; it does not
add measured sub-hourly structure, because none was measured. The calendar
likewise resolves only to hour-of-day, so every step within an hour carries the
same calendar factor and all sub-hourly variation is residual.

## 11. What is imposed, what is aimed at, and why you must not iterate

Two of the four statistics are **imposed** by construction and come out exact:
the load factor, through the capacity-cap fixed point, and the annual energy,
through the level. The other two are **aimed at**: $\sigma$ and $\phi$ are chosen
to produce a target spread and persistence, but the mask and the cap both act
after them, so the finished profile lands close and not on target.

`loadcast.bias_report()` prints the gap. It is systematic, and its sign differs
by class:

| class | CV target | CV mean | lag-1 target | lag-1 mean | lag-1 bias |
|---|---|---|---|---|---|
| `continuous` | 0.409 | — | 0.973 | 0.975 | +0.002 |
| `semi_continuous` | 0.478 | — | 0.793 | 0.868 | **+0.075** |
| `batch` | 1.177 | — | 0.848 | 0.759 | **−0.089** |
| `campaign` | 0.527 | — | 0.957 | 0.797 | **−0.160** |

The sign has a mechanism. The capacity cap trims the peaks that would otherwise
break a run, so an unmasked profile comes out *stickier* than asked; the on/off
mask chops runs into pieces, so a masked profile comes out *looser*.

### Why this forbids one particular loop

A systematic bias is harmless applied once. It is not harmless applied
repeatedly. If you measure a generated profile and feed those statistics back
into `class_from_observations`, then regenerate, the offset compounds. Starting
from `semi_continuous`:

| round | load factor | CV | lag-1 |
|---|---|---|---|
| measured site | 0.401 | 0.478 | 0.793 |
| 1 | 0.401 | 0.462 | 0.861 |
| 2 | 0.401 | 0.454 | 0.911 |
| 3 | 0.401 | 0.437 | 0.936 |
| 4 | 0.401 | 0.431 | 0.952 |
| 6 | 0.401 | 0.428 | 0.969 |
| 8 | 0.401 | 0.422 | 0.970 |

Persistence ratchets to a fixed point near 0.97 while the spread bleeds from
0.48 to 0.42: the profile grows smoother and stickier every round until it has
lost the high-frequency variability it was supposed to have. The load factor
never moves, because it is imposed — which is exactly why an imposed statistic
cannot warn you that the others are drifting.

This is the standard degeneration of any model retrained on its own output, and
the AR(1) is not what breaks. The process itself is stationary by construction:
$\operatorname{Var}[z_t] = \sigma^2$ for every $t$, started from that
distribution, with $|\phi| < 1$ — it cannot drift or collapse over any horizon,
at any resolution, and a test asserts it. What degenerates is the *estimation
loop* wrapped around it.

The package never closes that loop. The shipped classes hold constants measured
once, and no code path writes generated statistics back into a class. Holding
the targets fixed and varying only the seed is stable, as it must be:

| seed | load factor | CV | lag-1 |
|---|---|---|---|
| 1 | 0.401 | 0.459 | 0.863 |
| 4 | 0.401 | 0.476 | 0.877 |
| 8 | 0.401 | 0.479 | 0.871 |

So: vary the seed for another draw of the same site, never refit on the output.
