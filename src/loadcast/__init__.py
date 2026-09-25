"""loadcast -- synthetic multi-carrier industrial energy demand.

Hourly heat, cold and electricity demand for an industrial site, from the
handful of numbers someone actually knows about a plant: how much energy it uses
in a year, roughly how much more heat than cold it wants, how much of the
total is electricity, and whether the process runs continuously, in shifts or in
batches.

    import loadcast

    profiles = loadcast.generate(
        annual_mwh=10_000,
        heat_to_cold=7.4,
        elec_share=0.20,
        process_class="semi_continuous",
    )

What makes it different
-----------------------
Existing tools either produce deterministic profiles or leave the relationship
between carriers to fall out of whatever drives them. Both give carriers that
move in lockstep, which is an artefact of the construction rather than a
property of industry -- and for anything with storage, *whether the carriers
peak together* is precisely what decides how much buffering is needed.

loadcast makes that relationship an explicit input. `carrier_correlation` sets
how tightly the carriers move together and `carrier_lag_h` sets how far apart
they are offset, so a study can sweep coincidence rather than inherit it.

What it does not do
-------------------
It carries energy by carrier, not temperature: whether a machine can *reach* a
given process is a separate question, answered from the machine's own limits.
And the parameters are yours to choose. Defaults are indicative values with a
stated provenance, not predictions about any real site -- results are meant to
be reported as they hold across a swept space, not at a single assumed point.
"""

from __future__ import annotations

from .classes import (
    ProcessClass,
    available_classes,
    get_class,
    load_classes,
    register_class,
)
from .fitting import (
    bias_report,
    class_from_observations,
    correlation_floor,
    correlation_transfer,
    phi_from_lag1,
    sigma_from_cv,
)
from . import reference
from .generator import (
    build_profiles,
    generate,
    rescale_persistence,
    solve_correlation_knob,
    step_hours,
)
from .spec import CARRIERS, DemandSpec
from .stats import (
    cross_correlogram,
    duration_curve,
    integrated_drift,
    profile_statistics,
    summary_table,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # what to generate
    "DemandSpec", "CARRIERS",
    # generating
    "generate", "build_profiles", "solve_correlation_knob",
    "step_hours", "rescale_persistence",
    # process classes
    "ProcessClass", "available_classes", "get_class", "load_classes",
    "register_class",
    # fitting to your own measurements
    "class_from_observations", "bias_report",
    "sigma_from_cv", "phi_from_lag1",
    "correlation_floor", "correlation_transfer",
    # diagnostics
    # indicative published values
    "reference",
    "profile_statistics", "summary_table", "duration_curve",
    "cross_correlogram", "integrated_drift",
]
