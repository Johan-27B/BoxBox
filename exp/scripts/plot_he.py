"""Plot HE training and validation from the released per-run rewards."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from analyze import ROOT, check_manifest, load, summarize_he
from matplotlib import font_manager
from matplotlib.ticker import FormatStrFormatter
from plot_main import available_font


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/he-training-validation.pdf"
    )
    args = parser.parse_args()
    check_manifest(ROOT)
    scores = summarize_he(
        load(ROOT / "results/he/training.json"), load(ROOT / "results/he/validation.json")
    )
    TRAIN = [scores["iterations"][str(i)] for i in range(1, 25)]
    VALIDATION = [scores["validation"][f"h{i:02d}"] for i in (8, 16, 24)]
    EPOCH_SCORES = [scores["epochs"][str(i)] for i in (1, 2, 3)]
    OUTPUT = args.output
    for filename in ("Inter-Regular.otf", "Inter-SemiBold.otf"):
        path = Path("/usr/share/fonts/opentype/inter") / filename
        if path.exists():
            font_manager.fontManager.addfont(path)
    plt.rcParams.update(
        {
            "font.family": available_font(),
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.edgecolor": "#AEB7C2",
            "axes.linewidth": 0.7,
            "text.color": "#18202B",
            "axes.labelcolor": "#18202B",
            "xtick.color": "#667085",
            "ytick.color": "#667085",
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig, ax = plt.subplots(figsize=(6.6, 2.85))
    fig.subplots_adjust(left=0.095, right=0.98, top=0.86, bottom=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#E3E7ED", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_ylim(0.975, 1.405)
    ax.set_yticks((1.0, 1.1, 1.2, 1.3))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.set_xlim(0.5, 24.5)
    ax.set_xticks((4, 8, 12, 16, 20, 24))
    ax.set_xlabel("Training iteration", labelpad=5)
    ax.set_ylabel("Speedup")
    ax.tick_params(length=3, width=0.7)
    for epoch, fill in enumerate(("#EDF3FA", "#EDF6F2", "#FAF4E7")):
        # Half-integer boundaries assign iterations 1–8, 9–16, and 17–24
        # unambiguously to their respective shaded regions.
        left = 0.5 + 8 * epoch
        ax.axvspan(left, left + 8, facecolor=fill, edgecolor="none", zorder=0)
        ax.text(
            left + 4,
            1.380,
            f"Epoch {epoch + 1} ({1 + 8 * epoch}–{8 + 8 * epoch})",
            ha="center",
            va="center",
            color="#667085",
            fontsize=8,
        )
        ax.text(
            left + 4,
            1.346,
            f"{EPOCH_SCORES[epoch]:.3f}×",
            ha="center",
            va="center",
            color="#385E8D",
            fontsize=9.5,
            fontweight="semibold",
        )
    ax.plot(
        range(1, 25),
        TRAIN,
        color="#385E8D",
        linewidth=1.5,
        marker="o",
        markersize=3.6,
        markeredgecolor="white",
        markeredgewidth=0.5,
        label="Training",
        zorder=3,
    )
    ax.plot(
        (8, 16, 24),
        VALIDATION,
        color="#2D7D70",
        linewidth=1.6,
        linestyle=(0, (4, 2.5)),
        marker="D",
        markersize=5,
        markeredgecolor="white",
        markeredgewidth=0.6,
        label="Validation",
        zorder=4,
    )
    for xx, yy in zip((8, 16, 24), VALIDATION):
        ax.annotate(
            f"{yy:.3f}",
            (xx, yy),
            xytext=(-4 if xx == 24 else 0, 9),
            textcoords="offset points",
            ha="right" if xx == 24 else "center",
            color="#2D7D70",
            fontsize=9,
            fontweight="semibold",
        )
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.035),
        ncol=2,
        frameon=False,
        borderaxespad=0,
        handlelength=2.5,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, bbox_inches="tight", pad_inches=0.025)
    plt.close(fig)


if __name__ == "__main__":
    main()
