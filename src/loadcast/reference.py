"""Indicative starting values, from peer-reviewed sources, with their caveats.

Nothing here predicts your site. These are published aggregates, reported *with
what is wrong with them* so that they do not become assumptions unnoticed. The
documentation's page "Choosing inputs" shows how to use them.

Four sources, each used only for what it resolves:

============  ==========================================  ====================
source        used for                                    lacks
============  ==========================================  ====================
JERICHO       the only three-carrier split that exists    sector detail
Rehfeldt      heating and cooling by temperature band,    electricity
              7 UK subsectors, two datasets
Naegler       heat by temperature level, 13 branches      cooling, electricity
TNO / Marina  process and waste heat temperatures         electricity, cooling
============  ==========================================  ====================

Energy basis
------------
`generate` takes *delivered* energy: the heat and cold the process receives, and
the electricity it uses for everything else. JERICHO reports useful energy, which
is that basis. Rehfeldt reports *final* energy: the fuel burnt for heat and the
electricity that drives the chillers. Its heat:cold is therefore not the ratio
`generate` takes; convert it first,

    delivered heat:cold = final heat:cold * boiler efficiency / chiller COP

which at an efficiency of 0.9 and a COP of 3 divides it by about 3.3.

Why JERICHO is used here and nowhere near a time series
-------------------------------------------------------
JERICHO is the one peer-reviewed source giving heat, cooling *and* electricity
as useful energy, which is exactly what a three-carrier composition needs. Its
annual totals are what it was built to produce and are used for that alone.

Its hourly series must not be used, and neither must any spatial variation in
it. Both carry the same artefact: every carrier is a fixed scalar times one
shared profile. In time that makes the correlation between any two carriers
1.000000 to six decimals. In space it makes the composition identical across all
38 NUTS2 regions to four parts in 100 million -- while the regions' *scale*
varies by a factor of 17.9. So the dataset contains exactly one composition,
repeated, and reporting it as 38 regional observations would be reporting one
number 38 times.

Why the subsector ranges are wide
---------------------------------
Rehfeldt reports two datasets for the same subsectors, and they disagree by more
than some subsectors differ from one another: for chemicals, heat:cold is 6.6 in
one and 17.9 in the other, a range that overlaps food's (4.6 to 7.5). That
spread is reported rather than averaged away, because a point estimate here
would be false precision.

And a warning that matters more than the numbers: **branch aggregates cannot
place a site.** Of three metered food plants, none falls inside the published
range for its own branch. On a delivered basis (efficiency 0.9, COP 3) the
branch spans 1.4 to 2.2, while the plants sit at 0.33, 7.4 and 44 -- a spread
of a factor of 135 within the branch, against 1.6 for the branch range. Use
these to start a sweep, never to finish one.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

__all__ = ["sources", "citation", "industry_composition", "subsectors",
           "heat_to_cold_range", "temperature_bands", "sector_temperatures",
           "waste_to_heat", "reference_table"]


_BANDS = {
    "naegler": ["space_heat_hot_water", "process_below_100c", "process_100_500c",
                "process_500_1000c", "process_above_1000c"],
    "rehfeldt": ["cooling", "space_heating", "heat_below_200c", "heat_200_500c",
                 "heat_above_500c"],
}


@lru_cache(maxsize=1)
def _data() -> dict:
    source = resources.files("loadcast.data").joinpath("reference.json")
    return json.loads(source.read_text(encoding="utf-8"))


def sources() -> "pd.DataFrame":
    """Every source behind this module, with scope and what is wrong with it."""
    import pandas as pd

    rows = []
    for key, entry in _data()["sources"].items():
        rows.append({
            "source": key,
            "peer_reviewed": entry["peer_reviewed"],
            "scope": entry["scope"],
            "used_for": entry["kind"],
            "caveat": entry["caveat"],
        })
    return pd.DataFrame(rows).set_index("source")


def citation(source: str) -> str:
    """Full citation for one source."""
    entries = _data()["sources"]
    if source not in entries:
        raise KeyError(f"unknown source {source!r}; have {sorted(entries)}")
    return entries[source]["citation"]


def industry_composition() -> dict[str, float]:
    """Industry-wide useful-energy split, from JERICHO.

    German industry, 2019. One composition for all of industry -- the dataset
    resolves no sector or regional variation, so this is a single anchor point
    and not a distribution. Useful energy is the delivered basis `generate`
    takes, so these shares can be passed to it as they are.
    """
    return dict(_data()["compositions"]["industry_aggregate"])


def subsectors() -> list[str]:
    """Subsectors with Rehfeldt's heating and cooling shares."""
    return sorted(_data()["temperature_bands"]["rehfeldt"])


def heat_to_cold_range(subsector: str) -> tuple[float | None, float | None]:
    """Low and high heat:cold for a subsector, across Rehfeldt's two datasets.

    **Final energy, not the delivered ratio `generate` takes.** The heat is the
    fuel burnt for it and the cold the electricity that drives the chillers.
    Convert before generating::

        delivered = final * boiler_efficiency / chiller_cop

    The ratio counts space heating as heat, as Rehfeldt does.

    ``None`` as the high value means at least one dataset reports no cooling for
    the subsector, so the ratio is unbounded above; ``(None, None)`` means
    neither does -- a site with no cooling demand, for which
    ``heat_to_cold=None`` is the right spec.
    """
    entries = _data()["temperature_bands"]["rehfeldt"]
    if subsector not in entries:
        raise KeyError(
            f"unknown subsector {subsector!r}; have {subsectors()}")
    values = []
    for shares in entries[subsector].values():
        cooling = shares["cooling"]
        values.append(round((100.0 - cooling) / cooling, 1) if cooling > 0
                      else None)
    present = [v for v in values if v is not None]
    if not present:
        return (None, None)
    high = max(present) if len(present) == len(values) else None
    return (min(present), high)


def temperature_bands(source: str = "naegler") -> "pd.DataFrame":
    """Shares of heat (and, for Rehfeldt, cooling) by temperature band, in %.

    ``"naegler"``: heat in German industry, 2006, by branch -- space heat and hot
    water, then process heat below 100, 100-500, 500-1000 and above 1000 C. The
    finer bands, with no cooling.

    ``"rehfeldt"``: heating *and cooling* in UK industry, by subsector, in two
    datasets (ECUK and FORECAST) kept apart -- cooling, space heating, then heat
    below 200, 200-500 and above 500 C. Final energy. ECUK's bands are end-use
    categories (low temperature, drying and separation, high temperature) that
    Rehfeldt maps onto these temperatures.

    Both are digitised from stacked-bar figures, to about +-1 percentage point.
    Each row sums to 100. Like `sector_temperatures`, these inform a choice the
    generator does not make: which temperature a machine must reach to serve a
    given share of a branch's heat.
    """
    import pandas as pd

    tables = _data()["temperature_bands"]
    if source not in tables:
        raise KeyError(f"unknown source {source!r}; have {sorted(tables)}")
    if source == "naegler":
        table = pd.DataFrame(tables["naegler"]).T
        table.index.name = "branch"
    else:
        rows = {(sub, dataset): shares
                for sub, sets in tables["rehfeldt"].items()
                for dataset, shares in sets.items()}
        table = pd.DataFrame(rows).T
        table.index.names = ["subsector", "dataset"]
    # The stored keys are sorted alphabetically; read the bands coldest first.
    return table[_BANDS[source]]


def sector_temperatures(sector: str | None = None):
    """Process and waste heat temperatures per sector, from the TNO dataset.

    Indicative, and energy-weighted: the median is the temperature that splits a
    sector's heat in half by energy, not by stream count.

    These inform a choice the generator does not make. `loadcast` carries energy
    by carrier and no temperature at all -- whether a machine can *reach* a
    process, or usefully lift a waste stream, is answered from the machine's own
    limits against numbers like these.
    """
    import pandas as pd

    table = pd.DataFrame(_data()["sector_temperatures"]).T
    table.index.name = "sector"
    if sector is None:
        return table.round(1)
    if sector not in table.index:
        raise KeyError(f"unknown sector {sector!r}; have {sorted(table.index)}")
    return table.loc[sector].round(1)


def waste_to_heat(sector: str) -> float:
    """Indicative waste heat rejected per unit of process heat, 15-200 C.

    Feeds `DemandSpec.waste_to_heat`. From the TNO dataset's own sector totals,
    so it counts only streams inside 15-200 C -- the range that dataset was
    built to cover.
    """
    entry = _data()["sector_temperatures"]
    if sector not in entry:
        raise KeyError(f"unknown sector {sector!r}; have {sorted(entry)}")
    return float(entry[sector]["waste_to_process"])


def reference_table() -> "pd.DataFrame":
    """Everything indicative, in one table, labelled by provenance.

    Read the `heat_to_cold_low`/`high` columns as the width of published
    disagreement, not as an uncertainty band around a true value -- and as final
    energy, to be converted before it is passed to `generate`.
    """
    import pandas as pd

    rows = []
    for name in subsectors():
        low, high = heat_to_cold_range(name)
        rows.append({
            "subsector": name,
            "heat_to_cold_low": low,
            "heat_to_cold_high": high,
            "spread": (None if not (low and high) else round(high / low, 1)),
            "heat_cold_source": "rehfeldt (final energy, digitised +-1 pp)",
            "elec_share_source": "jericho (industry-wide, no sector detail)",
        })
    table = pd.DataFrame(rows).set_index("subsector")
    table["elec_share_indicative"] = industry_composition()["elec"]
    return table
