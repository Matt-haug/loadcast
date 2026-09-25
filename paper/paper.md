---
title: 'loadcast: a synthetic multi-carrier industrial energy demand generator with controllable cross-carrier structure'
tags:
  - Python
  - energy demand
  - load profiles
  - synthetic data
  - industrial energy
  - time series
authors:
  - name: Matteo Hauglustaine
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Institute of Mechanics, Materials and Civil Engineering, UCLouvain, Belgium
    index: 1
date: 25 September 2026
bibliography: paper.bib
---

# Summary

Sizing any energy system that serves an industrial site requires hourly demand
for each carrier the site consumes — process heat, refrigeration and
electricity. Such data is rarely available: metered industrial series are
commercially sensitive, and published datasets resolve annual quantities by
sector rather than hours at a plant.

`loadcast` generates them. From a small set of inputs an engineer can answer
from a site visit or an energy bill — annual energy, the ratio of heat to
cold, the electricity share, and whether the process runs continuously, in
shifts or in batches — it produces an hourly profile for each carrier whose
load factor, spread, persistence and annual energy match what was asked for.

Its distinguishing feature is that the *relationship between carriers* is an
explicit input. `carrier_correlation` sets how tightly the carriers move
together and `carrier_lag_h` sets how far apart they are offset in time. For any
system with storage this is the decisive property: a store exists precisely to
bridge the hours when one carrier is wanted and another is not, so a demand
model that fixes the coincidence between carriers fixes the answer to the
storage question before it is asked.

# Statement of need

Two classes of public data describe multi-carrier industrial demand, and both
impose the same structure: each carrier is a fixed scalar multiplying one shared
temporal profile, $P_m(t) = \kappa_m\,p(t)$ [@jericho; @sandhaas]. Under that
construction the correlation between any two carriers is

$$\operatorname{corr}(P_m, P_n) = \operatorname{corr}(\kappa_m p, \kappa_n p) = 1$$

identically, for every pair. This is not a property of industry that was
measured; it is an artefact of the disaggregation. Verified on the JERICHO-E-usage
regional series, the correlation between carriers is 1.000000 to six decimal
places across every region and carrier pair, and the cooling-to-heat ratio is
constant to one part in $10^{8}$ across 8760 hours.

A study of thermal storage, heat pumping, trigeneration or sector coupling that
inherits this structure will conclude that a perfectly matched host is
achievable, because in its input data the carriers never disagree.

`loadcast` replaces the fixed scalar with a generative model in which the
coincidence is a parameter. It targets researchers who need plausible industrial
demand to drive a design or dispatch study, and who need to test how sensitive
their conclusions are to assumptions about coincidence that no dataset resolves.

# State of the field

Several open tools generate energy demand time series, and each occupies a
distinct position.

`RAMP` [@ramp] simulates demand bottom-up from user behaviour: the modeller
declares appliances, when they are used and for how long, and stochasticity
supplies what the description omits. It is aimed at contexts where metered data
does not exist, and has been applied from households to continents. It does not
target industrial process demand, where enumerating appliances is not possible
— a paper machine or a distillation train is not a list of devices with duty
cycles — and the coupling between its carriers emerges from shared user
schedules rather than being set.

`LoadProfileGenerator` [@lpg] simulates residential demand from a behavioural
model grounded in German household survey data, with the same limitation for
industry.

`demandlib` [@demandlib] does cover industry, through an `IndustrialLoadProfile`
class and the BDEW standard load profiles. Its industrial profile is a
deterministic step function: workday start and end times, and six scaling
factors for day and night across weekdays, weekends and holidays. It therefore
has no stochastic component, no persistence, no capacity-limited tail and no
intermittency, and its load duration curve is a six-level staircase. Generating
two carriers from it yields two deterministic functions of the same calendar,
reproducing the perfect-coupling artefact with no parameter to change it.

`EnTiSe` [@entise] is a framework rather than a model: an extensible interface
for generating large numbers of time series, where "interdependent" denotes
data-flow dependency between generation steps — an occupancy profile derived
from an electricity profile — rather than a controllable statistical coupling.
Its application domain is building stocks, HVAC, domestic hot water and
mobility. `loadcast` is complementary and can be exposed through that interface.

To the author's knowledge, no available tool lets a user specify the
cross-carrier coincidence of industrial demand.

# Implementation

Each profile is a product of a calendar factor, an on/off state and a lognormal
AR(1) residual, capped at a rated capacity and rescaled:

$$P_m(t) = L_m \cdot S(t) \cdot M_m(t - \tau_m) \cdot R_m(t - \tau_m)$$

Every factor has mean one, so the level $L_m$ alone sets the energy and the
annual total is exact. The residual parameters are obtained from observable
statistics in closed form rather than by fitting: for a lognormal AR(1),
$\sigma^2 = \ln(1 + \mathrm{CV}^2)$ and
$\phi = \ln(1 + \rho(1)(e^{\sigma^2}-1))/\sigma^2$. Intermittency uses a
Gaussian copula — a persistent latent thresholded at its empirical quantile —
so the binary state inherits both persistence and cross-carrier correlation
without a transition matrix. A capacity cap applied as a fixed-point iteration
imposes the load factor exactly.

Because carriers share a calendar, the requested correlation is not the
generator's internal knob. The finished correlation has a floor

$$\gamma(0)\big|_{\rho=0} = \mathrm{CV}_S^2 / \mathrm{CV}_{\text{tot}}^2$$

equal to the share of total variance the shared calendar contributes, which for
the calibrated process classes ranges from 0.08 to 0.64. The knob delivering a
requested correlation is solved for.

A lag and a weak coupling are indistinguishable from the contemporaneous
correlation alone: as the offset grows, the lag-0 correlation decays towards
that floor, exactly where a small correlation would place it. A single reported
correlation therefore does not identify a multi-carrier demand model. The lag is
consequently exogenous — no public archive meters process heat and refrigeration
at one site, so it cannot be fitted — and the requested correlation is defined
at peak alignment so that a lag sweep changes timing without also changing
coupling strength.

Four process classes are calibrated on metered industrial sites. The sites
themselves are not redistributable; what ships is derived statistics and
calendar factors, which are group means carrying no identifying information.
Users can build a class from their own measurements.

# AI usage disclosure

Claude Code (Anthropic, Claude Opus 5) was used to restructure the author's
existing research code into this package, to write the test suite, to draft the
documentation and this paper, and to assist with the derivation and numerical
verification of the closed-form correlation transfer. The generator's method,
the calibration on metered industrial sites, and all design decisions are the
author's own prior work. The author reviewed, edited and validated all
AI-assisted output, independently verified every citation and every
characterisation of other software, and is responsible for the accuracy,
originality and licensing of all submitted material. No AI tool was used for
correspondence with editors or reviewers. The full disclosure is in
`AI_USAGE.md` in the repository.

# Acknowledgements

The metered series behind the calibrated process classes were made available by
their operators for research use.

# References
