# Choosing inputs

This page helps you set `loadcast`'s inputs for a site you have not metered:
first from what the site itself can tell you, then, where it cannot, from
published sources. It also points to sources for the temperatures your study
needs, which the generator does not carry.

!!! warning "A guide, worth what it is worth"
    The published values on this page are sector averages, and a sector average
    cannot place a single site. Of three metered food plants, none falls inside
    the published heat-to-cold range for its own branch: across them the ratio
    spans a factor of 135, against 1.6 for the branch range. Use these values to
    start a sweep, not to settle an input. Anything the site can tell you beats
    anything on this page.

## Count energy as the site receives it

`loadcast` generates **delivered energy**: the heat and the cold the process
receives, and the electricity it uses for everything else. That is the demand a
heat pump, a thermal store or a trigeneration unit has to meet. An energy bill
shows something else: the fuel and the electricity the site *buys*, with the
chillers' electricity inside the electricity. Convert the bill before you
generate:

$$Q_h = \eta_b\,F, \qquad Q_c = \mathrm{COP}\,E_c, \qquad E_e = E - E_c$$

where $F$ is the fuel bought in a year (MWh), $\eta_b$ the efficiency of the
boilers that burn it, $Q_h$ the heat they deliver, $E$ the electricity bought,
$E_c$ the part of it that drives the chillers, $\mathrm{COP}$ the chillers'
coefficient of performance (cold delivered per unit of electricity), $Q_c$ the
cold they deliver, and $E_e$ the electricity left for everything else. The
inputs then follow:

```python
annual_mwh   = Q_h + Q_c + E_e
heat_to_cold = Q_h / Q_c
elec_share   = E_e / annual_mwh
```

For example, a site that buys 8 GWh of gas and 3 GWh of electricity, of which
1 GWh drives chillers, with boilers at 90 % and chillers at a COP of 3:

```python
Q_h, Q_c, E_e = 0.9 * 8_000, 3.0 * 1_000, 3_000 - 1_000     # MWh
profiles = loadcast.generate(annual_mwh=Q_h + Q_c + E_e,      # 12 200
                             heat_to_cold=Q_h / Q_c,          # 2.4
                             elec_share=E_e / (Q_h + Q_c + E_e))   # 0.164
```

Take $\eta_b$ from the boilers' datasheet or their last test, and the COP from
the refrigeration plant's: it falls as the evaporator gets colder, so a freezer
runs at a lower COP than a chilled-water plant. Electric boilers and heat pumps
that already supply heat move from $E$ to $Q_h$ in the same way, with their own
efficiency or COP.

The basis matters most for the heat-to-cold ratio. With the numbers above, the
site *buys* 8 MWh of fuel per MWh of chiller electricity, but *receives* only
2.4 MWh of heat per MWh of cold: a factor of 3.3 between the two ratios. Some
published sources report the first, so check the basis of any ratio before
passing it to `generate`.

## What the site can tell you, and what to use when it cannot

| input | ask the site | published fallback | in `loadcast.reference` |
|---|---|---|---|
| `annual_mwh` | the energy bills, converted as above | none: it sets the scale of the site | - |
| `heat_to_cold` | fuel bought, and the chillers' electricity (a submeter, or rated power times running hours) | Rehfeldt et al., by subsector, in final energy | `heat_to_cold_range` |
| `elec_share` | the electricity bill, less the chillers | JERICHO-E-usage, all of industry | `industry_composition` |
| `process_class` | when the site runs: nights, weekends, campaigns, batches | none: see below | - |
| its calendar | the shift schedule, the load outside it, twelve monthly bills | the class's own | - |
| `rated_kw` | each carrier's peak demand: a bill's peak kW, the highest hourly gas flow | the class's load factor | - |
| `carrier_correlation`, `carrier_lag_h` | rarely answerable | none: sweep them | - |
| `waste_to_heat` | what the site rejects through its cooling towers, stacks and drains | the TNO dataset, four sectors | `waste_to_heat` |

### Heat-to-cold ratio

Rehfeldt et al. (2018) give the shares of heating and cooling in seven UK
subsectors, from two datasets, ECUK and FORECAST, which disagree. Their shares
are **final energy**: the heat is the fuel burnt for it, and the cooling the
electricity that drives the chillers. `heat_to_cold_range` returns their
ratio as published, so convert it to delivered energy first:

$$k_d = k_f\,\frac{\eta_b}{\mathrm{COP}}$$

where $k_f$ is the ratio of final energy for heat to final energy for cooling,
and $k_d$ the ratio of heat delivered to cold delivered, the one `generate`
takes. With $\eta_b = 0.9$ and a COP between 2 and 4:

| subsector | $k_f$, ECUK | $k_f$, FORECAST | $k_d$ at $\eta_b$ 0.9, COP 2 to 4 |
|---|---|---|---|
| Food, beverages and tobacco | 7.5 | 4.6 | 1.0 to 3.4 |
| Chemicals | 6.6 | 17.9 | 1.5 to 8.1 |
| Paper | no cooling | 22.8 | 5.1 or more, or no cooling |
| Machinery and transport | no cooling | at most 1 % cooling | no cooling |
| Iron and steel, non-ferrous metals | no cooling | no cooling | no cooling |
| Non-metallic minerals | no cooling | at most 1 % cooling | no cooling |
| Other industry | no cooling | at most 1 % cooling | no cooling |

```python
low, high = loadcast.reference.heat_to_cold_range("Food, beverages and tobacco")
low * 0.9 / 4, high * 0.9 / 2          # (1.0, 3.4) delivered
```

"At most 1 % cooling" marks a hairline in the published figure that is too
thin to read. A site with no cooling at all takes `heat_to_cold=None`.

### Electricity share

JERICHO-E-usage (Priesmann et al., 2021) is the one peer-reviewed source that
splits industrial energy into heat, cold and electricity on a delivered
(useful-energy) basis. It covers German industry in 2019 as a whole: heat 0.738,
cold 0.049 and electricity 0.213, with no sector detail.

```python
loadcast.reference.industry_composition()   # {'heat': 0.738, 'cold': 0.049, 'elec': 0.213, ...}
```

For a sector, two sources go further, each with a step to take first:

- Eurostat's complete energy balances (dataset `nrg_bal_c`) give every
  industry sector's final energy by fuel, for every EU country and year.
  Electricity's share there is of *final* energy, and it includes the chillers
  and any electric heating: take them out before you use it.
- Naegler et al. (2015, Fig. 2) split the final energy of German industrial
  branches in 2012 by end use: process heat, space heat, process and space
  cooling, mechanical energy, information and communication, and lighting. The
  last three are the electricity `elec_share` counts, before any conversion.

### Process class

Choose the class from how the site runs, not from its sector. No published
source links a sector to a rhythm, and each class rests on one metered site:

| if the site... | class | calibrated on |
|---|---|---|
| runs around the clock, all week | `continuous` | pasta and mineral drying |
| runs shifts on weekdays and slows down at weekends | `semi_continuous` | brewing, phosphate burners |
| runs for weeks, then stops for days or weeks | `campaign` | a phosphate burner |
| starts and stops between batches, idle most hours | `batch` | coffee roasting |

The load factor helps you decide: annual energy over the peak demand times
8760 hours. An electricity bill often states the peak demand. The classes'
load factors are 0.58 (`continuous`), 0.40 (`semi_continuous`), 0.50
(`campaign`) and 0.22 (`batch`). The class is a starting point: change what
you know with `custom_class`, or build a class from measured numbers with
`class_from_observations`, as the [usage page](usage.md#fitting-the-class-to-your-site)
shows.

### Calendar

A shipped class brings the calendar of the plant it was calibrated on. Yours
is easy to come by, and worth giving when it differs:

- **The week** from the shift schedule: which days, from which hour to which,
  and the load outside the shifts. Read that base load off a meter at night or
  at the weekend, as a fraction of the load during a shift: what keeps running
  when production stops (space heating, compressed air, cold rooms).
- **The months** from twelve monthly bills. A month's energy is not its
  activity alone, because months hold different numbers of working days;
  `with_monthly_energy` takes that out. A summer shutdown shows up on its own.
- **Both** from a metered series, if you have one: a week of quarter-hourly
  electricity from the grid operator gives the week; a full year gives the
  months as well.

```python
from loadcast import Calendar, custom_class

calendar = Calendar.from_schedule([("Mon-Fri", 6, 22)], base_load=0.25,
                                  monthly_energy=bills_mwh)
process = custom_class("semi_continuous", calendar=calendar)
```

The class keeps its fluctuation and adapts its spread and load factor to the
new calendar. A carrier that keeps other hours, such as cold rooms through the
weekend, takes a calendar of its own through `DemandSpec(calendars=...)`.

### Rated capacity

A carrier's peak demand fixes its load factor: mean demand over peak. Give it
as `rated_kw={"heat": ...}` and it becomes the cap on that carrier, in place of
the class's load factor; or give the load factor itself, as
`load_factor={"heat": ...}`, if that is the number you have. A carrier takes
one or the other: with its annual energy fixed, each implies the other. Where
to find the peak:

- **Electricity:** the peak demand on the bill, usually the highest
  quarter-hour of the month, less what the chillers draw at that moment: their
  electricity counts as cold here.
- **Heat:** the highest hourly gas flow times the boilers' efficiency, from the
  gas meter's hourly record.
- **Cold:** the chillers' cooling capacity, if they run flat out on the hottest
  production days.

A nameplate rating or a contracted capacity is only an upper bound. Boilers
are often installed with a spare unit or a margin, so a site may never draw its
full rating. Given a rating the profile never reaches, the cap does nothing,
the profile's own peaks stand, and the generator warns; give the measured peak
where you can, and sweep between the two where you cannot.

### Coupling between carriers

No public archive meters process heat and refrigeration at the same industrial
site, so no source gives `carrier_correlation` or `carrier_lag_h`. Ask the site
whether its cooling follows its heating, or trails it (a product cooled after it
is cooked), and sweep both inputs over the plausible range in any case. The
[sweeps and uncertainty page](uncertainty.md) shows how.

### Waste heat

The TNO dataset (Marina et al., 2021) gives the waste heat each sector rejects
per unit of process heat it uses, counting only streams between 15 and 200 °C:

| sector | `waste_to_heat` |
|---|---|
| Chemical | 0.95 |
| Food and Beverage | 0.50 |
| Paper | 0.65 |
| Refinery | 2.12 |

```python
loadcast.reference.waste_to_heat("Food and Beverage")   # 0.5
```

This waste heat is rejected above ambient temperature, so it is a source for a
heat pump. It is not a cooling demand, and it does not belong in
`heat_to_cold`.

## Temperatures

`loadcast` carries energy by carrier, with no temperature. Your study still
needs two temperatures: the temperature the heat must be delivered at, which
decides whether a machine can serve the process at all, and the temperature of
the waste heat, which is the cold end of a heat pump's lift. Three sources give
them by sector.

**Energy-weighted quartiles, four sectors.** The TNO dataset (Marina et al.,
2021) lists the process and waste heat streams of about 66 products in EU-28,
with their temperatures. Weighted by energy, they give:

| sector | process heat, 25 % | median | 75 % | waste heat, median |
|---|---|---|---|---|
| Chemical | 71 °C | 110 °C | 129 °C | 52 °C |
| Food and Beverage | 106 °C | 121 °C | 180 °C | 57 °C |
| Paper | 125 °C | 140 °C | 157 °C | 45 °C |
| Refinery | 173 °C | 275 °C | 309 °C | 90 °C |

The median is the temperature below which half of the sector's process heat is
needed. The per-product data are open on Mendeley Data, if your site makes one
of the products.

**Heat by temperature band, 13 branches.** Naegler et al. (2015, Fig. 3) split
the heat of German industrial branches in 2006 into space heat and hot water,
then process heat below 100 °C, 100 to 500 °C, 500 to 1000 °C and above
1000 °C. Shares in %:

| branch | space heat and hot water | below 100 °C | 100-500 °C | 500-1000 °C | above 1000 °C |
|---|---|---|---|---|---|
| Steel | 2.8 | 0.5 | 1.7 | 19.5 | 75.5 |
| NF-metals | 2.8 | 0.5 | 1.7 | 19.5 | 75.5 |
| Chemical | 7.3 | 13.8 | 21.5 | 46.2 | 11.2 |
| Minerals | 4.2 | 1.1 | 2.1 | 30.3 | 62.3 |
| Mining | 4.2 | 1.1 | 2.1 | 30.3 | 62.3 |
| Food | 25.6 | 33.4 | 41.0 | 0 | 0 |
| Textile | 41.2 | 58.8 | 0 | 0 | 0 |
| Paper and Print | 16.1 | 14.5 | 69.4 | 0 | 0 |
| Transport | 50.9 | 15.6 | 11.9 | 5.6 | 16.0 |
| Machinery | 50.8 | 15.3 | 11.8 | 6.3 | 15.8 |
| Wood | 13.1 | 69.3 | 17.6 | 0 | 0 |
| Construction | 15.8 | 7.8 | 25.6 | 16.6 | 34.2 |
| Other | 15.8 | 7.8 | 25.6 | 16.6 | 34.2 |

**Heating and cooling by band, seven subsectors.** Rehfeldt et al. (2018,
Fig. 16) give the same kind of split for UK subsectors, in final energy, with
cooling as a band of its own and two datasets kept apart: cooling, space
heating, then heat below 200 °C, 200 to 500 °C and above 500 °C. Its bands are
coarser, and ECUK's are end-use categories (low temperature, drying and
separation, high temperature) that Rehfeldt et al. map onto these temperatures.

```python
loadcast.reference.temperature_bands("naegler")
loadcast.reference.temperature_bands("rehfeldt")    # indexed by subsector and dataset
loadcast.reference.sector_temperatures()            # the TNO quartiles
```

Read a band table as the share of a branch's heat that a machine can serve. A
heat pump that delivers up to 150 °C reaches all of Naegler's food heat below
100 °C, space heat included (59 %), and some unknown part of its 100–500 °C
band. The bands cannot say which part: that needs the per-product temperatures
of the TNO dataset, or better, the site's own.

All three band tables are read off published bar charts, to about ±1
percentage point. Naegler et al. take Germany as representative and carry its
2006 shares to every EU country; Rehfeldt et al.'s two datasets disagree by up
to 50 points on a band. Both are reasons to sweep a temperature, as you would
any other input.

## Further reading

- **Industrial heat pumps and the processes they serve:** Arpagaus et al.
  (2018) review the high-temperature heat pumps on the market, with sink
  temperatures up to about 160 °C, and the industrial processes they suit.
- **Waste heat by sector, temperature and country:** Papapetrou et al. (2018)
  estimate the waste heat of EU industry per sector, temperature level and
  country, with their factors open on Mendeley Data.
- **Process temperatures, branch by branch:** Lauterbach et al. (2012) list
  the processes of German industry with the temperatures they need, to assess
  where solar heat could serve them.

## References

- Arpagaus C, Bless F, Uhlmann M, Schiffmann J, Bertsch SS. High temperature
  heat pumps: market overview, state of the art, research status, refrigerants,
  and application potentials. *Energy* 152:985–1010, 2018.
  [doi:10.1016/j.energy.2018.03.166](https://doi.org/10.1016/j.energy.2018.03.166)
- Eurostat. Complete energy balances (`nrg_bal_c`).
  [ec.europa.eu/eurostat](https://ec.europa.eu/eurostat/databrowser/view/nrg_bal_c/default/table)
- Lauterbach C, Schmitt B, Jordan U, Vajen K. The potential of solar heat for
  industrial processes in Germany. *Renewable and Sustainable Energy Reviews*
  16(7):5121–5130, 2012.
  [doi:10.1016/j.rser.2012.04.032](https://doi.org/10.1016/j.rser.2012.04.032)
- Marina A, Spoelstra S, Zondag HA, Wemmers AK. An estimation of the European
  industrial heat pump market potential. *Renewable and Sustainable Energy
  Reviews* 139:110545, 2021.
  [doi:10.1016/j.rser.2020.110545](https://doi.org/10.1016/j.rser.2020.110545).
  Data: Industrial process and waste heat data for EU28, Mendeley Data, 2020.
  [doi:10.17632/gyxjmvzbx8.1](https://doi.org/10.17632/gyxjmvzbx8.1)
- Naegler T, Simon S, Klein M, Gils HC. Quantification of the European
  industrial heat demand by branch and temperature level. *International
  Journal of Energy Research* 39(15):2019–2030, 2015.
  [doi:10.1002/er.3436](https://doi.org/10.1002/er.3436)
- Papapetrou M, Kosmadakis G, Cipollina A, La Commare U, Micale G. Industrial
  waste heat: estimation of the technically available resource in the EU per
  industrial sector, temperature level and country. *Applied Thermal
  Engineering* 138:207–216, 2018.
  [doi:10.1016/j.applthermaleng.2018.04.043](https://doi.org/10.1016/j.applthermaleng.2018.04.043).
  Data: [doi:10.17632/84wj6x23vh.1](https://doi.org/10.17632/84wj6x23vh.1)
- Priesmann J, Nolting L, Kockel C, Praktiknjo A. Time series of useful energy
  consumption patterns for energy system modeling (JERICHO-E-usage).
  *Scientific Data* 8:148, 2021.
  [doi:10.1038/s41597-021-00907-w](https://doi.org/10.1038/s41597-021-00907-w)
- Rehfeldt M, Fleiter T, Toro F. A bottom-up estimation of the heating and
  cooling demand in European industry. *Energy Efficiency* 11:1057–1082, 2018.
  [doi:10.1007/s12053-017-9571-y](https://doi.org/10.1007/s12053-017-9571-y)

`loadcast.reference.sources()` lists the four sources the package ships values
from, with the scope and the caveat of each, and `loadcast.reference.citation`
gives each one's full citation.

## Nomenclature

| symbol | meaning | unit |
|---|---|---|
| $F$ | fuel bought in a year | MWh |
| $E$, $E_c$ | electricity bought in a year; the part that drives the chillers | MWh |
| $\eta_b$ | boiler efficiency: heat delivered per unit of fuel | - |
| $\mathrm{COP}$ | chillers' coefficient of performance: cold delivered per unit of electricity | - |
| $Q_h$, $Q_c$ | heat and cold delivered in a year | MWh |
| $E_e$ | electricity for everything other than the chillers | MWh |
| $k_f$, $k_d$ | heat-to-cold ratio in final energy; in delivered energy | - |
