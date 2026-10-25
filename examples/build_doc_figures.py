"""Draw the documentation's figures.

    python examples/build_doc_figures.py

Needs matplotlib and scipy, and takes a few minutes. Writes eight PNGs to
docs/assets/figures/, in the house style of `figure_style.py`, which the
tutorial notebook shares, so every figure reads as one family. Each figure's
message is the first sentence of its caption on the page. Four for the page on
sweeps and uncertainty:

    uncertainty_one_at_a_time.png   each input swept over its range, the others
                                    held at the middle of theirs
    uncertainty_samples.png         32 sampled years: a week of cold demand, and
                                    the spread of three outputs
    uncertainty_sensitivity.png     the drift against each sampled input, and its
                                    total Sobol indices for several seeds
    uncertainty_structure.png       the calendar, the share of hours stopped
                                    and the heat rating, each swept on its own

and four for the usage page's section on fitting a class to a site:

    usage_calendar.png              one plant on three calendars
    usage_stops.png                 the same plant, stopped more often
    usage_cap.png                   the cap from the class, a load factor, a rating
    usage_own_calendar.png          cold rooms on a calendar of their own

The site, the ranges and the outputs are those of docs/uncertainty.md and
examples/02_uncertainty.py. The script prints the numbers the pages quote.
The text is set in Manrope when matplotlib can find it; see figure_style.py.
"""

from __future__ import annotations

import itertools
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from numpy.polynomial import legendre  # noqa: E402
from scipy.stats import qmc  # noqa: E402

import figure_style as fs  # noqa: E402
import loadcast  # noqa: E402
from loadcast import Calendar, custom_class  # noqa: E402

fs.apply()
OUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "figures"
C = fs.CARRIER

# The example site: a semi-continuous food plant, four uncertain inputs.
CLASS = "semi_continuous"
INPUTS = ["heat_to_cold", "elec_share", "carrier_correlation", "cold_lag_h"]
LABELS = {"heat_to_cold": "heat-to-cold ratio",
          "elec_share": "electricity share",
          "carrier_correlation": "carrier correlation",
          "cold_lag_h": "cold lag (h)"}
LOW = np.array([1.0, 0.14, 0.45, 0.0])
HIGH = np.array([3.4, 0.28, 0.90, 12.0])
MIDDLE = dict(zip(INPUTS, (LOW + HIGH) / 2))
OUTPUTS = {"heat_peak": ("heat peak (kW)", C["heat"]),
           "cold_peak": ("cold peak (kW)", C["cold"]),
           "drift": ("24-hour drift (h)", fs.INK)}
SEEDS = (1, 2, 3, 4, 5)


def generate(heat_to_cold, elec_share, carrier_correlation, cold_lag_h, seed):
    return loadcast.generate(
        annual_mwh=10_000, heat_to_cold=heat_to_cold, elec_share=elec_share,
        process_class=CLASS, carrier_correlation=carrier_correlation,
        carrier_lag_h={"cold": int(round(cold_lag_h))}, seed=seed)


def outputs(profiles) -> dict[str, float]:
    heat, cold = profiles["heat_kw"], profiles["cold_kw"]
    return {"heat_peak": float(heat.max()), "cold_peak": float(cold.max()),
            "drift": loadcast.integrated_drift(heat, cold, window_h=24)}


def save(fig, name: str) -> None:
    print(f"wrote {fs.save(fig, OUT, name)}")


def band(ax, x, table, key, colour, marker=None) -> None:
    """Median over seeds as a line, the range over seeds as a band."""
    median = table[key].median().to_numpy()
    low, high = table[key].min().to_numpy(), table[key].max().to_numpy()
    ax.fill_between(x, low, high, color=colour, alpha=0.14, lw=0)
    ax.plot(x, median, color=colour, marker=marker)


# =============================================================================
# 1. One input at a time
# =============================================================================


def sweep_values(name: str) -> np.ndarray:
    low, high = LOW[INPUTS.index(name)], HIGH[INPUTS.index(name)]
    if name == "cold_lag_h":
        return np.arange(0, 13, 2, dtype=float)
    return np.linspace(low, high, 7)


def one_at_a_time() -> None:
    results = {}
    for name in INPUTS:
        rows = []
        for value in sweep_values(name):
            for seed in SEEDS:
                point = {**MIDDLE, name: value}
                rows.append({"value": value, "seed": seed,
                             **outputs(generate(**point, seed=seed))})
        results[name] = pd.DataFrame(rows)

    fig, axes = plt.subplots(3, 4, figsize=fs.size(3), sharex="col",
                             sharey="row")
    for column, name in enumerate(INPUTS):
        table = results[name].groupby("value")
        x = np.asarray(list(table.groups), float)
        for row, (key, (label, colour)) in enumerate(OUTPUTS.items()):
            ax = axes[row, column]
            band(ax, x, table, key, colour)
            # The point every other column holds this input at.
            ax.axvline(MIDDLE[name], color=fs.LIGHT, lw=1.1, zorder=1)
            if column == 0:
                fs.heading(ax, label)
            if row == 2:
                ax.set_xlabel(LABELS[name])
        if name == "carrier_correlation":
            floor = loadcast.correlation_floor(CLASS)
            for row in range(3):
                axes[row, column].axvspan(0.40, floor, color=fs.WASH, lw=0,
                                          zorder=0)
            axes[0, column].text(0.405, 0.98, "below\nthe floor",
                                 color=fs.GREY, fontsize=8, va="top",
                                 transform=axes[0, column].get_xaxis_transform())
    for ax in axes.flat:
        fs.frame(ax)
    save(fig, "uncertainty_one_at_a_time")

    print("\nOne at a time: median over seeds at each end of each range")
    for name in INPUTS:
        ends = results[name].groupby("value").median().iloc[[0, -1]]
        spread = results[name].groupby("value")["drift"].agg(np.ptp).max()
        print(f"  {name:20s}", ends[["heat_peak", "cold_peak", "drift"]]
              .round(2).to_dict("list"), f"widest seed band of the drift {spread:.2f}")


# =============================================================================
# 2 and 3. Sampled inputs, and which of them matter
# =============================================================================

SAMPLES = qmc.scale(qmc.Sobol(d=4, seed=1).random(32), LOW, HIGH)
ALPHAS = [a for a in itertools.product(range(3), repeat=4) if sum(a) <= 2]


def legendre_basis(x: np.ndarray) -> np.ndarray:
    """Orthonormal Legendre polynomials of total degree up to 2."""
    u = 2 * (x - LOW) / (HIGH - LOW) - 1
    columns = []
    for alpha in ALPHAS:
        column = np.ones(len(x))
        for j, degree in enumerate(alpha):
            column = column * legendre.legval(u[:, j], [0] * degree + [1]) \
                * np.sqrt(2 * degree + 1)
        columns.append(column)
    return np.column_stack(columns)


def total_sobol(y: np.ndarray) -> tuple[float, np.ndarray]:
    """Leave-one-out error and total Sobol indices of a degree-2 expansion."""
    basis = legendre_basis(SAMPLES)
    coefficients, *_ = np.linalg.lstsq(basis, y, rcond=None)
    hat = basis @ np.linalg.pinv(basis)
    residuals = (y - basis @ coefficients) / (1 - np.diag(hat))
    loo = float(np.mean(residuals**2) / np.var(y))
    variance = np.sum(coefficients[1:]**2)
    indices = np.array([sum(c**2 for c, a in zip(coefficients, ALPHAS) if a[j])
                        for j in range(len(INPUTS))]) / variance
    return loo, indices


def sampled(seeds) -> tuple[pd.DataFrame, list]:
    rows, frames = [], []
    for x, seed in zip(SAMPLES, seeds):
        profiles = generate(*x, seed=seed)
        frames.append(profiles)
        rows.append(outputs(profiles))
    return pd.DataFrame(rows), frames


def samples_and_sensitivity() -> None:
    table, frames = sampled([1] * len(SAMPLES))

    # --- What sampling does to the demand, and to the outputs.
    fig = plt.figure(figsize=fs.size(1, height=3.2))
    grid = fig.add_gridspec(1, 6)
    week_ax = fig.add_subplot(grid[0, :3])
    week = slice("2025-03-03", "2025-03-09 23:00")
    lines = np.array([frame["cold_kw"].loc[week].to_numpy() for frame in frames])
    hours = frames[0]["cold_kw"].loc[week].index
    fs.weekends(week_ax, hours)
    for line in lines:
        week_ax.plot(hours, line, color=C["cold"], lw=0.6, alpha=0.3)
    median = np.median(lines, axis=0)
    week_ax.plot(hours, median, color=C["cold"], lw=2.2)
    fs.heading(week_ax, "cold demand (kW)", subtitle="one week, in each sample")
    fs.days(week_ax, hours)
    fs.frame(week_ax)
    fs.say(week_ax, hours[-1], median[-1], "median", C["cold"])
    strips = []
    rng = np.random.default_rng(0)
    for position, (key, (label, colour)) in enumerate(OUTPUTS.items()):
        ax = fig.add_subplot(grid[0, 3 + position])
        values = table[key].to_numpy()
        ax.scatter(rng.uniform(-0.18, 0.18, len(values)), values, s=20,
                   color=colour, linewidth=0.6, zorder=3)
        for q in (0.95, 0.5, 0.05):
            ax.hlines(np.quantile(values, q), -0.3, 0.3, color=fs.INK,
                      lw=1.6 if q == 0.5 else 1.0, zorder=4)
        ax.set_xlim(-0.5, 0.5)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        fs.heading(ax, label)
        fs.frame(ax, x=False)
        strips.append((ax, values))
    ax, values = strips[-1]
    for name, q in (("P95", 0.95), ("median", 0.5), ("P5", 0.05)):
        fs.say(ax, 0.3, np.quantile(values, q), name, fs.INK)
    save(fig, "uncertainty_samples")

    # --- The drift against each input, and the indices per seed.
    runs = {f"seed {seed}": sampled([seed] * len(SAMPLES))[0]["drift"].to_numpy()
            for seed in (1, 2, 3, 4)}
    runs["a new seed per sample"] = sampled(
        list(range(101, 101 + len(SAMPLES))))[0]["drift"].to_numpy()
    fitted = {label: total_sobol(y) for label, y in runs.items()}

    fig = plt.figure(figsize=fs.size(2, height=5.2))
    grid = fig.add_gridspec(2, 4, height_ratios=[1.1, 1.0])
    top = []
    for column, name in enumerate(INPUTS):
        ax = fig.add_subplot(grid[0, column],
                             sharey=None if column == 0 else top[0])
        ax.scatter(SAMPLES[:, column], table["drift"], s=22, color=fs.INK,
                   linewidth=0.6, zorder=3)
        ax.set_xlabel(LABELS[name])
        if column == 0:
            fs.heading(ax, "24-hour drift (h)",
                       subtitle="each sample, against each input (seed 1)")
        else:
            ax.tick_params(labelleft=False)
        top.append(ax)
    for ax in top:
        fs.frame(ax)

    ax = fig.add_subplot(grid[1, :])
    positions = np.arange(len(INPUTS))[::-1]
    for label, (loo, indices) in fitted.items():
        if label.startswith("seed"):
            ax.scatter(indices, positions, s=50, color=fs.INK, linewidth=0.8,
                       zorder=3)
        else:
            # A larger hollow ring, so it shows around the filled dots.
            ax.scatter(indices, positions, s=150, facecolor="none",
                       edgecolor=fs.INK, linewidth=1.5, zorder=4)
    ax.set_yticks(positions, [LABELS[name] for name in INPUTS])
    ax.tick_params(axis="y", length=0, pad=14)    # clear of the dots at 0
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("total Sobol index of the 24-hour drift")
    fs.heading(ax, subtitle="each input's index, one dot per study")
    fs.frame(ax, y=False)
    row = positions[INPUTS.index("carrier_correlation")]
    dots = [fitted[f"seed {s}"][1][INPUTS.index("carrier_correlation")]
            for s in (1, 2, 3, 4)]
    ring = fitted["a new seed per sample"][1][INPUTS.index("carrier_correlation")]
    fs.say(ax, min(dots), row, "the same seed in every sample, seeds 1-4",
           fs.INK, ha="right", dx=-14)
    fs.say(ax, ring, row, "a new seed per sample", fs.INK, ha="center",
           va="bottom", dx=0, dy=15)
    save(fig, "uncertainty_sensitivity")

    print("\nSampled outputs (seed 1): P05 / median / P95")
    print(table.quantile([0.05, 0.5, 0.95]).T.round(2))
    print("\nLeave-one-out error and total Sobol indices of the drift")
    for label, (loo, indices) in fitted.items():
        print(f"  {label:22s} LOO {loo:.4f}  ", dict(zip(INPUTS,
                                                        np.round(indices, 3))))


# =============================================================================
# 4. The site's structure: calendar, stops, rating
# =============================================================================

STRUCTURE_CORRELATION = 0.85    # above the floor of every calendar swept
CALENDARS = {
    "1 shift": [("Mon-Fri", 6, 14)],
    "2 shifts": [("Mon-Fri", 6, 22)],
    "3 shifts": [("Mon-Fri", 0, 24)],
    "7 days": [("daily", 0, 24)],
}
OFF_FRACTIONS = (0.0, 0.1, 0.2, 0.3, 0.4)
HEAT_RATINGS = (800.0, 1000.0, 1200.0, 1400.0, 1600.0)
STRUCTURE_SITE = dict(annual_mwh=10_000, heat_to_cold=MIDDLE["heat_to_cold"],
                      elec_share=MIDDLE["elec_share"])


def structure_outputs(seed, process=CLASS, rated_kw=None):
    profiles = loadcast.generate(
        **STRUCTURE_SITE, process_class=process,
        carrier_correlation=STRUCTURE_CORRELATION,
        carrier_lag_h={"cold": int(MIDDLE["cold_lag_h"])},
        rated_kw=rated_kw or {}, seed=seed)
    return outputs(profiles)


def structure_sweeps() -> None:
    columns = {
        "calendar": [(label, custom_class(
            CLASS, calendar=Calendar.from_schedule(shifts, base_load=0.25)),
            None) for label, shifts in CALENDARS.items()],
        "share of hours stopped": [(off, custom_class(CLASS, off_fraction=off),
                                    None) for off in OFF_FRACTIONS],
        "heat rating (kW)": [(rating, CLASS, {"heat": rating})
                             for rating in HEAT_RATINGS],
    }
    results = {}
    with warnings.catch_warnings():
        # The tightest rating trims the spread, and says so; the page explains.
        warnings.simplefilter("ignore", loadcast.TargetMissedWarning)
        for title, points in columns.items():
            rows = []
            for value, process, rated in points:
                for seed in SEEDS:
                    rows.append({"value": value, "seed": seed,
                                 **structure_outputs(seed, process, rated)})
            results[title] = pd.DataFrame(rows)

    heat_mean = (loadcast.DemandSpec(**STRUCTURE_SITE)
                 .annual_mwh_by_carrier()["heat"] * 1000 / 8760)
    fig, axes = plt.subplots(3, 3, figsize=fs.size(3), sharey="row")
    for column, (title, table) in enumerate(results.items()):
        grouped = table.groupby("value", sort=False)
        labels = list(grouped.groups)
        x = np.arange(len(labels)) if column == 0 else np.asarray(labels, float)
        for row, (key, (label, colour)) in enumerate(OUTPUTS.items()):
            ax = axes[row, column]
            band(ax, x, grouped, key, colour, marker="o")
            if column == 0:
                fs.heading(ax, label)
                ax.set_xticks(x, [str(v) for v in labels])
            if row < 2:
                ax.tick_params(labelbottom=False)
            if row == 2:
                ax.set_xlabel(title)
    # Only once every panel holds its data: the rows share their y axes.
    for ax in axes.flat:
        fs.frame(ax)
    # The rating as the load factor it implies, along the top of its column.
    top = axes[0, 2].secondary_xaxis(
        "top", functions=(lambda p: heat_mean / np.maximum(p, 1e-9),
                          lambda f: heat_mean / np.maximum(f, 1e-9)))
    top.set_xticks([heat_mean / r for r in HEAT_RATINGS],
                   [f"{heat_mean / r:.2f}" for r in HEAT_RATINGS])
    top.tick_params(direction="in", labelsize=8.5, labelcolor=fs.GREY)
    top.spines["top"].set_position(("outward", fs.OFFSET))
    top.set_xlabel("as a load factor", fontsize=8.5, color=fs.GREY)
    save(fig, "uncertainty_structure")

    print("\nStructure sweeps: median over seeds")
    for title, table in results.items():
        print(f"  {title}")
        print(table.groupby("value", sort=False)[list(OUTPUTS)].median()
              .round(2).to_string())


# =============================================================================
# 5. The usage page: fitting a class to a site
# =============================================================================

USAGE_SITE = dict(annual_mwh=10_000, heat_to_cold=2.2, elec_share=0.21, seed=3)
WEEK = slice("2025-03-03", "2025-03-09 23:00")
FORTNIGHT = slice("2025-03-03", "2025-03-16 23:00")


def usage_figures() -> None:
    # --- Your own calendar: the same plant on three schedules.
    months = Calendar.of(CLASS).month
    schedules = {
        "the shipped semi_continuous calendar": None,
        "two shifts on weekdays and a Saturday morning, base load 25 %":
            [("Mon-Fri", 6, 22), ("Sat", 6, 14)],
        "one shift on weekdays, base load 25 %": [("Mon-Fri", 6, 14)],
    }
    fig, axes = plt.subplots(3, 1, figsize=fs.size(3, height=6.4), sharex=True,
                             sharey=True)
    for ax, (title, blocks) in zip(axes, schedules.items()):
        process = (CLASS if blocks is None else custom_class(
            CLASS, calendar=Calendar.from_schedule(blocks, base_load=0.25,
                                                   months=months)))
        heat = loadcast.generate(process_class=process, **USAGE_SITE)["heat_kw"]
        week = heat.loc[WEEK]
        fs.weekends(ax, week.index)
        ax.plot(week.index, week.values, color=C["heat"], lw=1.4)
        fs.heading(ax, "heat demand (kW)", subtitle=title)
    fs.days(axes[-1], week.index)
    for ax in axes:
        fs.frame(ax)
    save(fig, "usage_calendar")

    # --- Stops: the same plant, stopped more often.
    fig, axes = plt.subplots(3, 1, figsize=fs.size(3, height=6.4), sharex=True,
                             sharey=True)
    for ax, off in zip(axes, (0.0, 0.2, 0.4)):
        process = custom_class(CLASS, off_fraction=off) if off else CLASS
        heat = loadcast.generate(process_class=process, **USAGE_SITE)["heat_kw"]
        span = heat.loc[FORTNIGHT]
        fs.weekends(ax, span.index)
        ax.plot(span.index, span.values, color=C["heat"], lw=1.2)
        stats = loadcast.profile_statistics(heat)
        fs.heading(ax, "heat demand (kW)",
                   subtitle=f"stopped {off:.0%} of the hours: load factor "
                            f"{stats['load_factor']:.2f}, peak "
                            f"{stats['peak_kw']:.0f} kW")
    fs.days(axes[-1], span.index)
    for ax in axes:
        fs.frame(ax)
    save(fig, "usage_stops")

    # --- The cap: from the class's load factor, a load factor, or a rating.
    caps = {
        "class, 0.40": {},
        "load_factor = 0.50": {"load_factor": {"heat": 0.50}},
        "rated_kw = 1000": {"rated_kw": {"heat": 1000.0}},
    }
    shades = fs.ramp("heat", 3, light=0.38, dark=0.45)
    fig, (left, right) = plt.subplots(1, 2, figsize=fs.size(1, height=3.6),
                                      width_ratios=[1, 1.5], sharey=True)
    plateaus = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", loadcast.TargetMissedWarning)
        for (label, extra), colour in zip(caps.items(), shades):
            heat = loadcast.generate(**USAGE_SITE, **extra)["heat_kw"]
            curve = np.sort(heat.to_numpy())[::-1]
            left.plot(np.arange(1, len(curve) + 1), curve, color=colour)
            plateaus.append((label, curve[0], colour))
            week = heat.loc[WEEK]
            right.plot(week.index, week.values, color=colour, lw=1.3)
    left.set_xscale("log")
    left.set_xticks([1, 10, 100, 1000, 8760], ["1", "10", "100", "1000", "8760"])
    left.minorticks_off()
    left.set_xlabel("hours in the year at or above that demand")
    fs.heading(left, "heat demand (kW)", subtitle="the cap from the class's load "
                                                  "factor, a load factor, a rating")
    fs.frame(left)
    for label, level, colour in plateaus:
        fs.say(left, 1.3, level, label, colour, va="top", dx=0, dy=-fs.LABEL_PAD)
    fs.weekends(right, week.index)
    fs.days(right, week.index)
    right.tick_params(labelleft=False)
    fs.heading(right, "", subtitle="the same three caps, over one week")
    fs.frame(right)
    save(fig, "usage_cap")

    # --- A calendar for one carrier: cold rooms through the weekend.
    fig, axes = plt.subplots(2, 1, figsize=fs.size(2, height=5.0), sharex=True,
                             sharey=True)
    ends = []
    for ax, (title, calendars) in zip(axes, (
            ("heat and cold on the class's calendar", {}),
            ("cold on a calendar of its own, Calendar.flat()",
             {"cold": Calendar.flat()}))):
        spec = loadcast.DemandSpec(calendars=calendars, **USAGE_SITE)
        frame = loadcast.generate(spec)
        week = frame.loc[WEEK]
        fs.weekends(ax, week.index)
        last = {}
        for column, key in (("heat_kw", "heat"), ("cold_kw", "cold")):
            values = week[column] / frame[column].mean()
            ax.plot(week.index, values, color=C[key], lw=1.4)
            last[key] = (week.index[-1], values.iloc[-1], C[key])
        ends.append((ax, last))
        floor = loadcast.correlation_floor(spec)
        fs.heading(ax, "demand / its own mean",
                   subtitle=f"{title}; correlation floor {floor:.2f}")
    fs.days(axes[-1], week.index)
    for ax in axes:
        fs.frame(ax)
    for ax, last in ends:
        fs.label_ends(ax, last)
    save(fig, "usage_own_calendar")


if __name__ == "__main__":
    one_at_a_time()
    samples_and_sensitivity()
    structure_sweeps()
    usage_figures()
