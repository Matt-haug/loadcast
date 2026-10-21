"""Draw the figures of the documentation's page on sweeps and uncertainty.

    python examples/build_doc_figures.py

Needs matplotlib and scipy, and takes a few minutes. Writes three PNGs to
docs/assets/figures/, in the tutorial notebook's palette and style, so the
documentation's figures read as one family:

    uncertainty_one_at_a_time.png   each input swept over its range, the others
                                    held at the middle of theirs
    uncertainty_samples.png         32 sampled years: a week of cold demand, and
                                    the spread of three outputs
    uncertainty_sensitivity.png     the drift against each sampled input, and its
                                    total Sobol indices for several seeds

The site, the ranges and the outputs are those of docs/uncertainty.md and
examples/02_uncertainty.py. The script prints the numbers the page quotes.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from numpy.polynomial import legendre  # noqa: E402
from scipy.stats import qmc  # noqa: E402

import loadcast  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "figures"

# The tutorial notebook's palette and style.
C = {"heat": "#eb6834", "cold": "#2a78d6", "elec": "#1baf7a", "waste": "#4a3aa7"}
INK, MUTED, WASH = "#1f1f1f", "#6b6b6b", "#d9d9d6"
plt.rcParams.update({
    "figure.dpi": 110, "figure.figsize": (9, 3.2),
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.6,
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "legend.frameon": False,
})

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
           "drift": ("24-hour drift (h)", INK)}
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
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=150, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print(f"wrote {OUT / name}.png")


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

    fig, axes = plt.subplots(3, 4, figsize=(9, 6.2), sharex="col", sharey="row")
    for column, name in enumerate(INPUTS):
        table = results[name].groupby("value")
        for row, (key, (label, colour)) in enumerate(OUTPUTS.items()):
            ax = axes[row, column]
            median, low, high = (table[key].median(), table[key].min(),
                                 table[key].max())
            ax.fill_between(median.index, low, high, color=colour, alpha=0.15,
                            lw=0)
            ax.plot(median.index, median.values, color=colour, lw=1.8,
                    solid_capstyle="round")
            # The point every other column holds this input at.
            ax.axvline(MIDDLE[name], color=MUTED, lw=0.6, ls=":")
            if column == 0:
                ax.set_ylabel(label)
            if row == 2:
                ax.set_xlabel(LABELS[name])
        if name == "carrier_correlation":
            floor = loadcast.correlation_floor(CLASS)
            for row in range(3):
                axes[row, column].axvspan(0.40, floor, color=WASH, lw=0)
                axes[row, column].set_xlim(0.40, 0.92)
            axes[0, column].text(0.405, 0.97, "below\nfloor", color=MUTED,
                                 fontsize=7, va="top",
                                 transform=axes[0, column].get_xaxis_transform())
    fig.suptitle("Each input swept over its range, the others held at the "
                 "dotted middle; band: 5 seeds", x=0.01, ha="left",
                 fontsize=10, fontweight="bold")
    fig.tight_layout()
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

    # --- Figure 2: what sampling does to the demand, and to the outputs.
    fig = plt.figure(figsize=(9, 3.0))
    grid = fig.add_gridspec(1, 6, wspace=0.9)
    ax = fig.add_subplot(grid[0, :3])
    week = slice("2025-03-03", "2025-03-09")
    lines = np.array([frame["cold_kw"].loc[week].to_numpy() for frame in frames])
    hours = frames[0]["cold_kw"].loc[week].index
    for line in lines:
        ax.plot(hours, line, color=C["cold"], lw=0.6, alpha=0.35)
    ax.plot(hours, np.median(lines, axis=0), color=C["cold"], lw=1.8)
    ax.set_ylabel("cold demand (kW)")
    ax.set_title("One week of cold demand", loc="left")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%a"))
    fig.text(0.13, -0.04, "thin: each of the 32 samples; thick: their median",
             color=MUTED, fontsize=7.5)
    rng = np.random.default_rng(0)
    for position, (key, (label, colour)) in enumerate(OUTPUTS.items()):
        ax = fig.add_subplot(grid[0, 3 + position])
        values = table[key].to_numpy()
        ax.scatter(rng.uniform(-0.18, 0.18, len(values)), values, s=16,
                   color=colour, edgecolor="white", linewidth=0.6, zorder=3)
        for q, width in ((0.05, 0.25), (0.5, 0.4), (0.95, 0.25)):
            ax.hlines(np.quantile(values, q), -width, width, color=INK,
                      lw=1.2 if q == 0.5 else 0.8, zorder=4)
        ax.set_xlim(-0.5, 0.5)
        ax.set_xticks([])
        ax.grid(axis="x", visible=False)
        ax.set_title(label, loc="left", fontsize=8, fontweight="normal")
    fig.text(0.53, -0.04, "lines: 5th percentile, median, 95th percentile",
             color=MUTED, fontsize=7.5)
    save(fig, "uncertainty_samples")

    # --- Figure 3: the drift against each input, and the indices per seed.
    runs = {f"seed {seed}": sampled([seed] * len(SAMPLES))[0]["drift"].to_numpy()
            for seed in (1, 2, 3, 4)}
    runs["a new seed per sample"] = sampled(
        list(range(101, 101 + len(SAMPLES))))[0]["drift"].to_numpy()
    fitted = {label: total_sobol(y) for label, y in runs.items()}

    fig = plt.figure(figsize=(9, 5.0))
    grid = fig.add_gridspec(2, 4, height_ratios=[1.1, 1.0], hspace=0.55)
    for column, name in enumerate(INPUTS):
        ax = fig.add_subplot(grid[0, column],
                             sharey=None if column == 0 else fig.axes[0])
        ax.scatter(SAMPLES[:, column], table["drift"], s=18, color=INK,
                   edgecolor="white", linewidth=0.6, zorder=3)
        ax.set_xlabel(LABELS[name])
        if column == 0:
            ax.set_ylabel("24-hour drift (h)")
        else:
            ax.tick_params(labelleft=False)
    fig.axes[0].set_title("The drift of each of the 32 samples, against each "
                          "input (seed 1)", loc="left")

    ax = fig.add_subplot(grid[1, :])
    positions = np.arange(len(INPUTS))[::-1]
    for label, (loo, indices) in fitted.items():
        if label.startswith("seed"):
            ax.scatter(indices, positions, s=42, color=INK, edgecolor="white",
                       linewidth=0.8, zorder=3,
                       label=("the same seed in every sample (seeds 1-4)"
                              if label == "seed 1" else None))
        else:
            # A larger hollow ring, so it shows around the filled dots.
            ax.scatter(indices, positions, s=130, facecolor="none",
                       edgecolor=INK, linewidth=1.4, zorder=4,
                       label="a new seed per sample")
    ax.set_yticks(positions, [LABELS[name] for name in INPUTS])
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("total Sobol index of the 24-hour drift")
    ax.set_title("Which inputs matter: one dot per study", loc="left")
    ax.legend(loc="upper center")
    save(fig, "uncertainty_sensitivity")

    print("\nSampled outputs (seed 1): P05 / median / P95")
    print(table.quantile([0.05, 0.5, 0.95]).T.round(2))
    print("\nLeave-one-out error and total Sobol indices of the drift")
    for label, (loo, indices) in fitted.items():
        print(f"  {label:22s} LOO {loo:.4f}  ", dict(zip(INPUTS,
                                                        np.round(indices, 3))))


if __name__ == "__main__":
    one_at_a_time()
    samples_and_sensitivity()
