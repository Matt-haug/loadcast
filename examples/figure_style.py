"""One look for every figure of loadcast's documentation and tutorial.

The tutorial notebook and `build_doc_figures.py` both import this module, so
their figures read as one family. The rules follow Jean-luc Doumont's advice on
graphs:

    message     stated as a sentence in the caption on the page; the image
                carries no title
    labels      curves are named directly, in their own colour and clear of
                every line, not in a legend; the y label is written
                horizontally, above its axis
    ink         no frame and no grid; the axes stand a little apart from the
                data and from each other; ticks point inwards, and each axis
                starts and ends on a tick
    lines       solid: series are told apart by colour, never by dashes;
                reference lines are thin and light grey
    colour      a carrier keeps one colour everywhere; variants of one carrier
                are shades of it, light to dark; anything that is not a
                carrier is ink or grey
    time        day names at midnight, weekends shaded

    import figure_style as fs
    fs.apply()
    fig, ax = plt.subplots(figsize=fs.size(rows=1))
    ...
    fs.heading(ax, "heat demand (kW)")
    fs.frame(ax)
    fs.save(fig, folder, "name")

The text is set in Manrope, the face of the documentation, when matplotlib can
find it: installed on the system, or in a folder named by the environment
variable LOADCAST_FIGURE_FONTS. Otherwise matplotlib's default face is used,
and the figures are otherwise the same.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cycler import cycler
from matplotlib.collections import PathCollection
from matplotlib.colors import to_hex, to_rgb
from matplotlib.ticker import FixedLocator, FuncFormatter

CARRIER = {"heat": "#e4632d", "cold": "#2a73c4", "elec": "#16a275",
           "waste": "#5a48b0"}
INK = "#222222"       # text, and series that are not carriers
GREY = "#8c8c87"      # a second series that is not a carrier; the axes
LIGHT = "#c4c4bf"     # reference lines
WASH = "#eeeeec"      # weekend shading, bands

WIDTH = 9.0           # inches: every figure has the same width
ROW = 2.2             # inches per row of panels
FACE = "Manrope"
OFFSET = 14           # points between the data and each axis
LABEL_PAD = 5         # points between a direct label and any line


def _font() -> str:
    """Manrope if matplotlib can find it, else its default face."""
    folder = os.environ.get("LOADCAST_FIGURE_FONTS")
    if folder:
        for path in sorted(Path(folder).glob("*.ttf")):
            font_manager.fontManager.addfont(str(path))
    names = {entry.name for entry in font_manager.fontManager.ttflist}
    return FACE if FACE in names else plt.rcParamsDefault["font.family"][0]


def apply() -> None:
    """Set matplotlib's defaults to the house style."""
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 170,
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "figure.constrained_layout.use": True,
        "figure.constrained_layout.h_pad": 0.08,
        "figure.constrained_layout.w_pad": 0.08,
        "font.family": _font(), "font.size": 9.5,
        "text.color": INK,
        # The axes' title slot carries the horizontal y label, so it is quiet.
        "axes.titlesize": 9.5, "axes.titleweight": "normal",
        "axes.titlelocation": "left", "axes.titlepad": 11,
        "axes.titlecolor": INK,
        "axes.labelsize": 9.5, "axes.labelcolor": INK,
        "axes.edgecolor": GREY, "axes.linewidth": 1.0,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": False, "axes.axisbelow": True,
        "axes.prop_cycle": cycler(color=[CARRIER["heat"], CARRIER["cold"],
                                         CARRIER["elec"], CARRIER["waste"],
                                         INK]),
        "xtick.direction": "in", "ytick.direction": "in",
        "xtick.major.size": 4, "ytick.major.size": 4,
        "xtick.major.width": 1.0, "ytick.major.width": 1.0,
        "xtick.minor.visible": False, "ytick.minor.visible": False,
        "xtick.major.pad": 5, "ytick.major.pad": 5,
        "xtick.color": GREY, "ytick.color": GREY,
        "xtick.labelcolor": INK, "ytick.labelcolor": INK,
        "xtick.labelsize": 9, "ytick.labelsize": 9,
        "legend.frameon": False, "legend.fontsize": 9,
        "lines.linewidth": 2.0, "lines.solid_capstyle": "round",
        "lines.linestyle": "-", "lines.markersize": 5,
        "scatter.edgecolors": "white",
    })


def size(rows: int = 1, height: float | None = None) -> tuple[float, float]:
    """Figure size for `rows` rows of panels, at the house width."""
    return (WIDTH, height if height is not None else 0.6 + ROW * rows)


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


def heading(ax, label: str = "", subtitle: str | None = None) -> None:
    """The y label, written horizontally above the axis; a subtitle above it."""
    ax.set_ylabel("")
    lines = [line for line in (subtitle, label) if line]
    ax.set_title("\n".join(lines), linespacing=1.55)


def say(ax, x, y, text: str, colour: str, ha: str = "left",
        va: str = "center", dx: float = 8, dy: float = 0, **kwargs) -> None:
    """A direct label, in its series' colour, instead of a legend entry."""
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points",
                ha=ha, va=va, color=colour, fontweight="semibold",
                annotation_clip=False, **kwargs)


def _points_per_unit(ax) -> tuple[float, float]:
    """Points per data unit along x and y, once the figure is laid out."""
    ax.figure.canvas.draw()
    box = ax.get_window_extent()
    scale = 72.0 / ax.figure.dpi
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    return box.width * scale / (x1 - x0), box.height * scale / (y1 - y0)


def label_ends(ax, items: dict[str, tuple], gap: float = 14.0,
               dx: float = 9) -> None:
    """Name each line just past its right end, nudged apart so none touch.

    `items` maps a label to ``(x, y, colour)``, the end of its line. Labels
    closer than `gap` points are spread apart vertically, keeping their order.
    """
    if not items:
        return
    _, per_y = _points_per_unit(ax)
    rows = sorted(([text, x, y, colour] for text, (x, y, colour)
                   in items.items()), key=lambda row: float(row[2]))
    heights = [float(row[2]) * per_y for row in rows]
    placed = []
    for height in heights:
        placed.append(height if not placed else max(height, placed[-1] + gap))
    shift = np.mean(heights) - np.mean(placed)
    for row, height, level in zip(rows, heights, placed):
        say(ax, row[1], row[2], row[0], row[3], dx=dx,
            dy=level + shift - height)


def _dense(points: np.ndarray, step: float = 2.0) -> np.ndarray:
    """The polyline through `points` (pixels), sampled every `step` pixels."""
    points = points[np.isfinite(points).all(axis=1)]
    if len(points) < 2:
        return points
    pieces = [points[:1]]
    for a, b in zip(points[:-1], points[1:]):
        n = max(1, int(np.hypot(*(b - a)) // step))
        t = np.linspace(0.0, 1.0, n + 1)[1:, None]
        pieces.append(a + t * (b - a))
    return np.vstack(pieces)


def _clearance(points: np.ndarray, box: tuple) -> float:
    """Smallest distance, in pixels, from `points` to the rectangle `box`."""
    if not len(points):
        return np.inf
    x0, y0, x1, y1 = box
    dx = np.maximum.reduce([x0 - points[:, 0], np.zeros(len(points)), points[:, 0] - x1])
    dy = np.maximum.reduce([y0 - points[:, 1], np.zeros(len(points)), points[:, 1] - y1])
    return float(np.hypot(dx, dy).min())


def label_best(ax, curves: dict[str, tuple], fontsize: float = 9.5) -> None:
    """Name each curve beside itself, where the label keeps furthest from the rest.

    `curves` maps a label to ``(x, y, colour)``, the curve's points. Every
    candidate box sits `LABEL_PAD` points above the curve, or below it, across
    the label's own width; the label goes where the nearest other line, text or
    axes edge is furthest away, above the curve when that is as good.
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    pad = LABEL_PAD * fig.dpi / 72.0
    frame_box = ax.get_window_extent(renderer)
    lines = [(line, _dense(line.get_transform().transform(
        np.asarray(line.get_xydata(), dtype=float)))) for line in ax.lines]
    for name, (x, y, colour) in curves.items():
        own = ax.transData.transform(np.column_stack(
            [np.asarray(x, dtype=float), np.asarray(y, dtype=float)]))
        own = own[np.argsort(own[:, 0])]
        dense_own = _dense(own)
        others = [pts for line, pts in lines
                  if not (len(line.get_xydata()) == len(own) and np.allclose(
                      np.sort(line.get_transform().transform(
                          np.asarray(line.get_xydata(), dtype=float)), axis=0),
                      np.sort(own, axis=0), atol=0.5))]
        obstacles = np.vstack(others) if others else np.empty((0, 2))
        texts = [t.get_window_extent(renderer) for t in ax.texts
                 if t.get_visible() and t.get_text().strip()]
        probe = ax.text(0, 0, name, fontsize=fontsize, fontweight="semibold")
        size = probe.get_window_extent(renderer)
        probe.remove()
        width, height = size.width, size.height
        best, best_score = None, None
        for centre in np.linspace(frame_box.x0 + width / 2, frame_box.x1 - width / 2, 200):
            span = (dense_own[:, 0] >= centre - width / 2) & (dense_own[:, 0] <= centre + width / 2)
            if not span.any() or not (own[0, 0] <= centre <= own[-1, 0]):
                continue
            for side, preference in (("above", 1), ("below", 0)):
                if side == "above":
                    bottom = dense_own[span, 1].max() + pad
                    box = (centre - width / 2, bottom, centre + width / 2, bottom + height)
                else:
                    top = dense_own[span, 1].min() - pad
                    box = (centre - width / 2, top - height, centre + width / 2, top)
                edge = min(box[0] - frame_box.x0, frame_box.x1 - box[2],
                           box[1] - frame_box.y0, frame_box.y1 - box[3])
                if edge < 0:
                    continue
                room = min(_clearance(obstacles, box), 2.0 * edge + pad)
                for other in texts:
                    room = min(room, float(np.hypot(
                        max(other.x0 - box[2], box[0] - other.x1, 0.0),
                        max(other.y0 - box[3], box[1] - other.y1, 0.0))))
                score = (min(room, 3.0 * height), preference, room)
                if best_score is None or score > best_score:
                    best, best_score = box, score
        if best is None:
            continue
        x_data, y_data = ax.transData.inverted().transform(
            ((best[0] + best[2]) / 2, best[1]))
        ax.annotate(name, (x_data, y_data), ha="center", va="bottom",
                    color=colour, fontweight="semibold", fontsize=fontsize,
                    annotation_clip=False)
        fig.canvas.draw()


def reference(ax, y: float, label: str | None = None,
              colour: str = LIGHT) -> None:
    """A thin, light horizontal reference line, named at its right end."""
    ax.axhline(y, color=colour, lw=1.1, zorder=1)
    if label:
        ax.annotate(label, (1.0, y), xycoords=("axes fraction", "data"),
                    xytext=(0, LABEL_PAD), textcoords="offset points",
                    ha="right", va="bottom", color=GREY)


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


def _data_range(ax, axis: str) -> tuple[float, float]:
    """The range the data of `ax`, and of the axes sharing this axis, cover."""
    group = (ax.get_shared_x_axes() if axis == "x" else ax.get_shared_y_axes())
    siblings = group.get_siblings(ax)
    lows, highs = [], []
    for sibling in siblings:
        box = sibling.dataLim
        low, high = (box.x0, box.x1) if axis == "x" else (box.y0, box.y1)
        if np.isfinite(low) and np.isfinite(high):
            lows.append(low)
            highs.append(high)
    return min(lows), max(highs)


def frame(ax, x: bool = True, y: bool = True) -> None:
    """Stand the axes apart from the data, each starting and ending on a tick.

    Both axis lines move `OFFSET` points out from the plotting area, so they
    meet neither the data nor each other. The limits widen to the nearest tick
    below the data and the nearest above it, so each axis line carries a tick
    mark at both ends. Ticks set by hand keep their positions, and the axis
    runs from the first to the last; a time axis keeps the limits `days` gave
    it. Call it once the data and any ticks are in place -- for axes that
    share an axis, once every one of them holds its data.
    """
    for side in ("left", "bottom"):
        ax.spines[side].set_position(("outward", OFFSET))
    for axis, wanted in (("x", x), ("y", y)):
        if not wanted:
            continue
        which = ax.xaxis if axis == "x" else ax.yaxis
        locator = which.get_major_locator()
        if isinstance(locator, (mdates.DateLocator, mdates.RRuleLocator)):
            continue
        low, high = _data_range(ax, axis)
        setter = ax.set_xlim if axis == "x" else ax.set_ylim
        if isinstance(locator, FixedLocator):
            ticks = np.sort(np.asarray(locator.locs, dtype=float))
            setter(min(ticks[0], low), max(ticks[-1], high))
            continue
        # Widening the limits can change the tick step, so widen until the
        # ticks stop moving, then pin them: the ends stay on ticks.
        tolerance = 1e-9 * max(abs(low), abs(high), 1.0)
        start, stop = low, high
        for _ in range(6):
            ticks = np.asarray(locator.tick_values(start, stop), dtype=float)
            below = ticks[ticks <= low + tolerance]
            above = ticks[ticks >= high - tolerance]
            new = (below.max() if below.size else ticks.min(),
                   above.min() if above.size else ticks.max())
            if np.allclose(new, (start, stop)):
                break
            start, stop = new
        setter(start, stop)
        inside = ticks[(ticks >= start - tolerance) & (ticks <= stop + tolerance)]
        which.set_major_locator(FixedLocator(inside))
    _unclip(ax)


def _unclip(ax) -> None:
    """Draw in full the markers and line ends that sit on a limit.

    The limits enclose the data, so nothing spills past the axes; without this,
    a marker on the edge of the plotting area shows only its inner half.
    """
    (x0, x1), (y0, y1) = sorted(ax.get_xlim()), sorted(ax.get_ylim())
    for artist in [*ax.lines, *ax.collections]:
        if isinstance(artist, plt.Line2D):
            if artist.get_transform() != ax.transData:
                continue
            points = np.asarray(artist.get_xydata(), dtype=float)
        elif isinstance(artist, PathCollection) and artist.get_offset_transform() == ax.transData:
            points = np.asarray(artist.get_offsets(), dtype=float)
        else:
            continue
        points = points[np.isfinite(points).all(axis=1)] if points.size else points
        if points.size and (points[:, 0].min() >= x0 and points[:, 0].max() <= x1
                            and points[:, 1].min() >= y0 and points[:, 1].max() <= y1):
            artist.set_clip_on(False)


def save(fig, folder: Path | str, name: str, close: bool = True) -> Path:
    """Write `name`.png into `folder`, trimmed to its content."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", pad_inches=0.12)
    if close:
        plt.close(fig)
    return path
