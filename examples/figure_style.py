"""One look for every figure of loadcast's documentation and tutorial.

The tutorial notebook and `build_doc_figures.py` both import this module, so
their figures read as one family:

    import figure_style as fs
    fs.apply()
    fig, ax = plt.subplots(figsize=fs.size(rows=1))
    ...
    fs.title(fig, "What the figure shows")
    fs.save(fig, folder, "name")

The rules it encodes:

    colour      a carrier keeps one colour everywhere; variants of one carrier
                are shades of it, light to dark; anything that is not a
                carrier is ink or grey
    titles      one bold title per figure, at the left; panel titles smaller,
                also at the left; no captions inside the image -- the page
                carries them
    axes        horizontal grid only, no top or right spine, light ticks
    time        day names at midnight, weekends shaded, hours of the day on
                spans of a few days
    legends     frameless, above the plot at the right, or labels at the lines

It uses DejaVu Sans, which ships with matplotlib, so the figures come out the
same on any machine.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cycler import cycler
from matplotlib.colors import to_hex, to_rgb
from matplotlib.ticker import FuncFormatter

# Carriers: distinguishable to a colour-blind reader; waste is also dashed, so
# it never relies on hue alone.
CARRIER = {"heat": "#e4632d", "cold": "#2a73c4", "elec": "#16a275",
           "waste": "#5a48b0"}
INK = "#222222"       # text, and series that are not carriers
GREY = "#7a7a76"      # secondary series, reference lines
LIGHT = "#b8b8b3"     # faint reference lines
WASH = "#ececea"      # weekend shading, bands
GRID = "#e6e6e3"

WIDTH = 9.0           # inches: every figure has the same width
ROW = 2.1             # inches per row of panels


def apply() -> None:
    """Set matplotlib's defaults to the house style."""
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 160,
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "figure.constrained_layout.use": True,
        "figure.constrained_layout.h_pad": 0.06,
        "figure.constrained_layout.w_pad": 0.06,
        "font.family": "DejaVu Sans", "font.size": 9,
        "text.color": INK,
        "figure.titlesize": 11, "figure.titleweight": "bold",
        "axes.titlesize": 9.5, "axes.titleweight": "semibold",
        "axes.titlelocation": "left", "axes.titlepad": 7,
        "axes.titlecolor": INK,
        "axes.labelsize": 9, "axes.labelcolor": INK,
        "axes.edgecolor": GREY, "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "axes.axisbelow": True,
        "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.prop_cycle": cycler(color=[CARRIER["heat"], CARRIER["cold"],
                                         CARRIER["elec"], CARRIER["waste"],
                                         INK]),
        "xtick.color": GREY, "ytick.color": GREY,
        "xtick.labelcolor": INK, "ytick.labelcolor": INK,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "xtick.major.size": 3, "ytick.major.size": 0,
        "ytick.major.pad": 4,
        "legend.frameon": False, "legend.fontsize": 8.5,
        "legend.handlelength": 1.8, "legend.columnspacing": 1.4,
        "legend.borderaxespad": 0.2,
        "lines.linewidth": 1.4, "lines.solid_capstyle": "round",
        "lines.markersize": 4.5,
        "scatter.edgecolors": "white",
    })


def size(rows: int = 1, height: float | None = None) -> tuple[float, float]:
    """Figure size for `rows` rows of panels, at the house width."""
    return (WIDTH, height if height is not None else 0.7 + ROW * rows)


def ramp(colour: str, n: int, light: float = 0.62, dark: float = 0.3,
         ) -> list[str]:
    """`n` shades of one colour, light to dark, for variants of one carrier.

    `colour` is a carrier's name or any matplotlib colour.
    """
    base = np.array(to_rgb(CARRIER.get(colour, colour)))
    if n == 1:
        return [to_hex(base)]
    shades = []
    for t in np.linspace(-light, dark, n):
        mixed = base + (1 - base) * -t if t < 0 else base * (1 - t)
        shades.append(to_hex(np.clip(mixed, 0, 1)))
    return shades


def title(fig, text: str) -> None:
    """The figure's one bold title, at the left."""
    fig.suptitle(text, x=0.0, ha="left")


def legend(ax, ncol: int | None = None, **kwargs):
    """A frameless legend above the plot, at the right."""
    handles, labels = ax.get_legend_handles_labels()
    return ax.legend(handles, labels, loc="lower right",
                     bbox_to_anchor=(1.0, 1.0),
                     ncol=ncol or len(labels), **kwargs)


def label_lines(ax, x: float, lines: dict[str, tuple], dx: float = 0.0,
                **kwargs) -> None:
    """Write each series' name at its line, right of `x`, in its colour.

    `lines` maps a label to ``(y, colour)``.
    """
    for text, (y, colour) in lines.items():
        ax.annotate(text, (x, y), xytext=(4 + dx, 0), textcoords="offset points",
                    va="center", ha="left", color=colour, fontsize=8.5,
                    **kwargs)


def reference(ax, y: float, label: str | None = None, style: str = "--",
              colour: str = GREY) -> None:
    """A horizontal reference line, thin and grey."""
    ax.axhline(y, color=colour, lw=0.9, ls=style, label=label, zorder=1)


def weekends(ax, index: pd.DatetimeIndex) -> None:
    """Shade the Saturdays and Sundays of `index`."""
    first, last = index[0].normalize(), index[-1]
    for day in pd.date_range(first, last, freq="D"):
        if day.dayofweek >= 5:
            ax.axvspan(day, day + pd.Timedelta(days=1), color=WASH, lw=0,
                       zorder=0)


def days(ax, index: pd.DatetimeIndex | None = None,
         weekly: bool = False) -> None:
    """Day names at midnight; on a span of three days or fewer, hours too.

    `weekly` labels Mondays only, with the date, for narrow panels holding a
    fortnight or more.
    """
    span = None if index is None else (index[-1] - index[0])
    if weekly:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_minor_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b"))
    elif span is not None and span <= pd.Timedelta(days=3):
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))

        def fmt(value, _):
            stamp = mdates.num2date(value)
            return stamp.strftime("%a") if stamp.hour == 0 else stamp.strftime("%H:%M")
        ax.xaxis.set_major_formatter(FuncFormatter(fmt))
    else:
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a"))
    if index is not None:
        ax.set_xlim(index[0], index[-1] + (index[1] - index[0]))


def save(fig, folder: Path | str, name: str, close: bool = True) -> Path:
    """Write `name`.png into `folder`, trimmed to its content."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", pad_inches=0.1)
    if close:
        plt.close(fig)
    return path
