"""Render the archived Figure 1 curves and intervals using the paper layout."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from analyze import ROOT, check_manifest, load
from matplotlib import font_manager


def available_font():
    return (
        "Inter"
        if any(f.name == "Inter" for f in font_manager.fontManager.ttflist)
        else "DejaVu Sans"
    )


METHODS = {
    "frozen_harness": {
        "label": "Frozen Harness",
        "color": "#385E8D",
        "linestyle": (0, (4, 2.2)),
        "zorder": 2,
    },
    "boxbox": {"label": "BOXBOX", "color": "#2D7D70", "linestyle": "solid", "zorder": 3},
    "harness_scaling": {
        "label": "Harness Scaling",
        "color": "#A8894E",
        "linestyle": (0, (1.5, 1.5)),
        "zorder": 2.5,
    },
    "harness_evolution": {
        "label": "Harness Evolution",
        "color": "#7E8996",
        "linestyle": "-.",
        "zorder": 2.2,
    },
}


def configure_style() -> None:
    for filename in (
        "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
        "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
    ):
        path = Path(filename)
        if path.exists():
            font_manager.fontManager.addfont(path)
    mpl.rcParams.update(
        {
            "font.family": available_font(),
            "font.size": 8.2,
            "axes.labelsize": 8.5,
            "axes.labelcolor": "#18202B",
            "axes.edgecolor": "#AEB7C2",
            "axes.linewidth": 0.7,
            "xtick.color": "#667085",
            "ytick.color": "#667085",
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.5,
            "text.color": "#18202B",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _style_axes(ax: Any) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#D8DEE8", linewidth=0.65)
    ax.tick_params(length=3, width=0.7)
    ax.set_axisbelow(True)


def _save(fig: Any, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", pad_inches=0.025)
    plt.close(fig)


def _draw_method(ax, method_id, method, x, y):
    style = METHODS[method_id]
    ax.plot(
        x,
        y,
        color=style["color"],
        linestyle=style["linestyle"],
        linewidth=2.25 if method_id == "boxbox" else 1.8,
        label=method["label"],
        zorder=style["zorder"],
    )
    ax.scatter(
        x[-1], y[-1], s=18, color=style["color"], edgecolor="white", linewidth=0.7, zorder=4
    )


def build_snapshot():
    methods = {}
    for key, rows in CURVES.items():
        data = np.asarray(rows, dtype=float)
        assert np.isfinite(data).all()
        assert np.all(np.diff(data[:, 0]) >= -1e-10)
        assert np.all(np.diff(data[:, 1]) >= -1e-10)
        assert np.all(np.diff(data[:, 2]) >= -1e-10)
        methods[key] = {
            "label": METHODS[key]["label"],
            "endpoint_speedup": rows[-1][2],
            "average_cumulative_cost_usd": rows[-1][1],
            "points": [
                {"task_minutes": t, "average_cumulative_cost_usd": c, "speedup": y}
                for t, c, y in rows
            ],
        }
    methods["harness_evolution"] = {
        "label": "Harness Evolution",
        "endpoint_speedup": HE_TIME[-1][1],
        "average_cumulative_cost_usd": HE_COST,
        # All accepted evaluations after 240 min in the source are final deliveries.
        "points": [{"task_minutes": min(t, 240.0), "speedup": y} for t, y in HE_TIME],
    }
    return {"methods": methods}


def render(snapshot):
    import matplotlib.pyplot as plt
    import numpy as np

    configure_style()
    METHODS["harness_evolution"] = {
        "label": "Harness Evolution",
        "color": "#7E8996",
        "linestyle": "-.",
        "zorder": 2.2,
    }
    order = ("frozen_harness", "harness_evolution", "harness_scaling", "boxbox")
    ylim = (
        0.98,
        max(1.72, max(snapshot["methods"][k]["endpoint_speedup"] for k in order) * 1.055),
    )
    ylim = (ylim[0], max(ylim[1], max(max(r[2] for r in rows) for rows in BANDS.values()) + 0.035))
    for cost_axis in (False, True):
        fig, ax = plt.subplots(figsize=(3.45, 2.45))
        for key in order:
            method = snapshot["methods"][key]
            minutes = np.array([p["task_minutes"] for p in method["points"]])
            speedup = np.array([p["speedup"] for p in method["points"]])
            intervals = np.asarray(BANDS[key])
            btime, lower, upper = intervals.T
            if cost_axis:
                rows = np.asarray(HE_COST_CURVE if key == "harness_evolution" else CURVES[key])
                bx = np.interp(btime, rows[:, 0], rows[:, 1])
            else:
                bx = btime / 60
            ax.fill_between(
                bx, lower, upper, color=METHODS[key]["color"], alpha=0.10, linewidth=0, zorder=1
            )
            if key == "harness_evolution":
                if cost_axis:
                    cost_data = np.asarray(HE_COST_CURVE)
                    _draw_method(ax, key, method, cost_data[:, 1], cost_data[:, 2])
                else:
                    ax.step(
                        minutes / 60,
                        speedup,
                        where="post",
                        color=METHODS[key]["color"],
                        linestyle=METHODS[key]["linestyle"],
                        linewidth=1.8,
                        label=method["label"],
                        zorder=2.2,
                    )
                    ax.scatter(
                        [minutes[-1] / 60],
                        [speedup[-1]],
                        s=18,
                        color=METHODS[key]["color"],
                        edgecolor="white",
                        linewidth=0.7,
                        zorder=4,
                    )
                continue
            x = (
                np.array([p["average_cumulative_cost_usd"] for p in method["points"]])
                if cost_axis
                else minutes / 60
            )
            _draw_method(ax, key, method, x, speedup)
        _style_axes(ax)
        ax.axhline(1, color="#AEB7C2", linewidth=0.75, linestyle=(0, (2, 2)))
        ax.set_ylim(*ylim)
        ax.set_ylabel("Speedup (×)")
        if cost_axis:
            max_cost = max(snapshot["methods"][k]["average_cumulative_cost_usd"] for k in order)
            ax.set_xlim(0, math.ceil(max_cost / 5) * 5)
            ax.set_xlabel("Model cost ($)")
        else:
            ax.set_xlim(0, 4.7)
            ax.axvline(4, color="#AEB7C2", linewidth=0.75, linestyle=(0, (3, 3)), zorder=1)
            ax.set_xticks([0, 1, 2, 3, 4])
            ax.set_xlabel("Task time (h)")
            ax.legend(
                frameon=False,
                loc="upper left",
                handlelength=2.5,
                labelspacing=0.25,
                borderpad=0.2,
                bbox_to_anchor=(0, 1.025),
            )
        for key in order:
            m = snapshot["methods"][key]
            cost, y = m["average_cumulative_cost_usd"], m["endpoint_speedup"]
            dx, dy = 5, 0
            if cost_axis:
                label = f"${cost:.2f}"
            else:
                label = f"{y:.3f}×"
            annotation = ax.annotate(
                label,
                xy=(cost if cost_axis else m["points"][-1]["task_minutes"] / 60, y),
                xytext=(dx, dy),
                textcoords="offset points",
                ha="left",
                va="center",
                color=METHODS[key]["color"],
                fontsize=7.2 if cost_axis else 7.4,
                fontweight="semibold",
            )
            if cost_axis:
                annotation.set_in_layout(False)
        fig.tight_layout(pad=0.45)
        if cost_axis:
            ax.set_xlim(0, 30)
            ax.set_xticks([0, 5, 10, 15, 20, 25, 30])
        path = OUTPUTS[int(cost_axis)]
        _save(fig, path)


def main():
    global CURVES, BANDS, HE_TIME, HE_COST, HE_COST_CURVE, OUTPUTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "generated")
    args = parser.parse_args()
    check_manifest(ROOT)
    data = load(ROOT / "results/main/figure.json.gz")
    CURVES, BANDS, HE_TIME, HE_COST, HE_COST_CURVE = (
        data[key] for key in ("CURVES", "BANDS", "HE_TIME", "HE_COST", "HE_COST_CURVE")
    )
    OUTPUTS = (
        args.output / "boxbox-speedup-vs-time.pdf",
        args.output / "boxbox-speedup-vs-cost.pdf",
    )
    render(build_snapshot())
    for path in OUTPUTS:
        print(path)


if __name__ == "__main__":
    main()
