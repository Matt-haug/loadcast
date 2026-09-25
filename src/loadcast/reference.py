"""Indicative starting values, from peer-reviewed sources, with their caveats.

Nothing here predicts your site. These are published aggregates, and the whole
point of this module is that they are reported *with what is wrong with them*
rather than as defaults that quietly become assumptions.

Three sources, each used only for what it resolves:

============  ==========================================  ====================
source        used for                                    conspicuously lacks
============  ==========================================  ====================
JERICHO       the only three-carrier split that exists    sector detail
Rehfeldt      heat:cold by subsector, as a range          electricity
TNO / Marina  process and waste heat temperatures         electricity, cooling
============  ==========================================  ====================

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

Why the subsector ranges are so wide
------------------------------------
Rehfeldt reports two datasets for the same subsectors, and they disagree by more
than the subsectors differ from one another: for food, heat:cold is 11.5 in one
and 32.3 in the other. That spread is reported rather than averaged away,
because a point estimate here would be false precision.

And a warning that matters more than the numbers: **branch aggregates cannot
place a site.** Of three metered food plants, none fell inside the published
range for its own branch -- the within-branch spread was a factor of 135 against
a branch range of 2.8. Use these to start a sweep, never to finish one.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

__all__ = ["sources", "citation", "industry_composition", "subsectors",
           "heat_to_cold_range", "sector_temperatures", "waste_to_heat",
           "reference_table"]


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
    and not a distribution.
    """
    return dict(_data()["compositions"]["industry_aggregate"])


def subsectors() -> list[str]:
    """Subsectors with a published heat:cold range."""
    return sorted(_data()["subsector_heat_to_cold"])


def heat_to_cold_range(subsector: str) -> tuple[float | None, float | None]:
    """Low and high heat:cold for a subsector, across Rehfeldt's two datasets.

    ``None`` means that dataset reports no cooling at all for the subsector, so
    the ratio is unbounded -- a site with no cooling demand, for which
    ``heat_to_cold=None`` is the right spec.
    """
    entries = _data()["subsector_heat_to_cold"]
    if subsector not in entries:
        raise KeyError(
            f"unknown subsector {subsector!r}; have {subsectors()}")
    values = [d["heat_to_cold"] for d in entries[subsector].values()]
    present = [v for v in values if v is not None]
    if not present:
        return (None, None)
    return (min(present), max(present))


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
    disagreement, not as an uncertainty band around a true value.
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
            "heat_cold_source": "rehfeldt (digitised, +-5pp)",
            "elec_share_source": "jericho (industry-wide, no sector detail)",
        })
    table = pd.DataFrame(rows).set_index("subsector")
    table["elec_share_indicative"] = industry_composition()["elec"]
    return table
