"""loadcast -- a parametric generator of hourly industrial energy demand.

A year of hourly heat, cold and electricity demand for an industrial site, from
the few numbers an engineer can get from a site visit or an energy bill: the
annual energy, the ratio of heat to cold, the electricity share, and whether
the process runs continuously, in shifts, in campaigns or in batches. It is
built to be an *input* to design studies (heat pumps, thermal stores,
trigeneration units), not to describe any real site.

    import loadcast

    profiles = loadcast.generate(
        annual_mwh=10_000,
        heat_to_cold=7.4,
        elec_share=0.20,
        process_class="semi_continuous",
        carrier_correlation=0.75,          # how tightly the carriers move together
        carrier_lag_h={"cold": 6},         # cold trails heat by six hours
    )

What it is for
--------------
Because a handful of numbers defines the demand, a study that reports them lets
anyone regenerate it, so different technologies can be assessed against the
same demand. Each year takes about a second, and every input is a single
number, so the generator suits parametric analyses, sensitivity analysis and
uncertainty propagation.

One input sets it apart: the relationship between carriers. Published
multi-carrier data builds every carrier from one shared profile, so the
carriers move in lockstep -- an artefact of the construction, not a property of
industry. For anything with storage, whether the carriers peak together decides
how much storage is needed. Here `carrier_correlation` sets how tightly they
move together and `carrier_lag_h` how many hours apart they are offset, so a
study can sweep that relationship rather than inherit it.

What it is not
--------------
Not a model of temperature: it carries energy by carrier, and whether a machine
can reach a process's temperature is answered from the machine's own limits.
Not a model of your site: the inputs are yours to choose, and the defaults are
indicative values with a stated source, not predictions. Report a result as it
holds across a range of inputs, not at one assumed point.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

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

try:
    __version__ = _version("loadcast")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0+unknown"

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
