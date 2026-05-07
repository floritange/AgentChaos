# scripts/gen_figures.py — Generate README figures (paper style)
#
# Usage:  uv run python scripts/gen_figures.py
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
DOCS_DIR.mkdir(exist_ok=True)

# ── Global Config (paper style) ─────────────────────────────────
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "hatch.linewidth": 0.5,
        "hatch.color": "#444444",
    }
)

C_GRID = "#D0D0D0"
FONT_MAIN = 12
FONT_DATA = 9

# ── Data (from paper, Claude-Sonnet-4.5) ────────────────────────
SYSTEMS = ["AutoGen", "MAD", "MapCoder", "EvoMAC"]
SYSTEM_COLORS = ["#D8E8F8", "#D5E8D4", "#FFF2CC", "#F5D5C8"]

FTYPES = ["Error", "Timeout", "Empty", "Truncate", "Corrupt", "Schema"]
FTYPE_COLORS = ["#D8E8F8", "#D5E8D4", "#FFF2CC", "#F5D5C8", "#E8D4F8", "#E8E0D0"]

STRATEGIES = ["Single", "Burst", "Intermittent", "Persistent"]
STRAT_COLORS = ["#D8E8F8", "#D5E8D4", "#FFF2CC", "#F5D5C8"]

# Delta-pass@1 by fault type (content target, Claude-Sonnet-4.5)
DATA_FTYPE = {
    "AutoGen": [23.75, 28.21, 22.5, 21.25, -2.38, 21.69],
    "MAD": [37.5, 22.33, 38.46, 28.85, -1.92, 38.46],
    "MapCoder": [59.62, 64.42, 56.73, 58.65, 2.88, 57.69],
    "EvoMAC": [42.31, 45.19, 44.23, 40.38, 0, 43.27],
}

# Delta-pass@1 by injection strategy (Claude-Sonnet-4.5)
DATA_STRAT = {
    "AutoGen": [1.66, 0, -3.57, 57.41],
    "MAD": [22.33, 13.33, 8.47, 54.74],
    "MapCoder": [48.23, 46.81, -1.27, 62.39],
    "EvoMAC": [3.64, 34.78, 1.77, 47.64],
}

# Average delta-pass@1 (aggregated across all datasets)
DATA_SYSTEM = {
    "AutoGen": 14.15,
    "MAD": 21.66,
    "MapCoder": 42.06,
    "EvoMAC": 16.26,
    "Mini-SE": 0.87,
}


def _grouped_bar(ax, categories, data_dict, colors, ylabel, title, ylim=(-10, 75)):
    """Draw a grouped bar chart in paper style."""
    n_cat = len(categories)
    n_sys = len(data_dict)
    bar_w = 5 / n_cat
    group_w = n_cat * bar_w
    group_gap = 0.8
    group_step = group_w + group_gap

    systems = list(data_dict.keys())

    for ci, sys_name in enumerate(systems):
        values = data_dict[sys_name]
        group_left = ci * group_step
        for j, val in enumerate(values):
            x = group_left + j * bar_w
            ax.bar(x, val, bar_w, color=colors[j], edgecolor="black", linewidth=0.6, zorder=3, align="edge")
            xc = x + bar_w / 2
            if val >= 0:
                ax.text(xc, val + 1.2, f"{val:.1f}", ha="center", va="bottom", fontsize=FONT_DATA, fontweight="bold")
            else:
                ax.text(xc, val - 1.0, f"{val:.1f}", ha="center", va="top", fontsize=FONT_DATA, fontweight="bold")

    # x-axis: system labels
    sys_centers = [ci * group_step + group_w / 2 for ci in range(n_sys)]
    ax.set_xticks(sys_centers)
    ax.set_xticklabels(systems, fontsize=FONT_MAIN, fontweight="bold")
    ax.set_xlim(-0.3, n_sys * group_step - group_gap + 0.3)

    # y-axis
    ax.set_ylim(ylim[0] - 8, ylim[1] + 8)
    yticks = np.arange(ylim[0], ylim[1] + 1, 20)
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{int(v)}%" for v in yticks])
    ax.set_ylabel(ylabel, fontsize=FONT_MAIN, fontweight="bold", labelpad=0)
    ax.tick_params(axis="y", labelsize=FONT_MAIN - 1)

    # grid + spines
    ax.axhline(y=0, color="black", linewidth=0.8, zorder=2)
    ax.grid(True, axis="y", color=C_GRID, linewidth=0.5, alpha=0.4)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_linewidth(0.8)

    # legend
    legend_handles = [
        Patch(facecolor=colors[j], edgecolor="black", linewidth=0.8, label=categories[j]) for j in range(n_cat)
    ]
    ax.get_figure().legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.52, 1.04),
        ncol=min(n_cat, 6),
        fontsize=FONT_MAIN - 2,
        frameon=True,
        edgecolor="black",
        handlelength=2.0,
        handleheight=1.2,
        columnspacing=1.5,
        handletextpad=0.5,
        prop={"weight": "bold", "size": FONT_MAIN - 2},
    )


def fig_system_robustness():
    """Bar chart: average delta-pass@1 by agent system."""
    systems = list(DATA_SYSTEM.keys())
    values = list(DATA_SYSTEM.values())
    colors = ["#D8E8F8", "#D5E8D4", "#FFF2CC", "#F5D5C8", "#E8D4F8"]

    fig, ax = plt.subplots(figsize=(7, 2.5))
    bars = ax.bar(systems, values, color=colors, edgecolor="black", linewidth=0.6, width=0.6, zorder=3)
    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.8,
            f"{v:.1f}%",
            ha="center",
            fontsize=FONT_DATA,
            fontweight="bold",
        )

    ax.set_ylabel("\u0394pass@1 (%)", fontsize=FONT_MAIN, fontweight="bold")
    ax.set_ylim(0, 50)
    yticks = np.arange(0, 51, 10)
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{int(v)}%" for v in yticks])
    ax.tick_params(axis="x", labelsize=FONT_MAIN, labelrotation=0)
    ax.tick_params(axis="y", labelsize=FONT_MAIN - 1)
    ax.axhline(y=0, color="black", linewidth=0.8, zorder=2)
    ax.grid(True, axis="y", color=C_GRID, linewidth=0.5, alpha=0.4)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_linewidth(0.8)

    plt.tight_layout()
    path = DOCS_DIR / "fig_system_robustness.png"
    plt.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close()
    print(f"  saved: {path}")


def fig_fault_type_impact():
    """Grouped bar chart: delta-pass@1 by fault type (content target)."""
    fig, ax = plt.subplots(figsize=(7, 2.5))
    _grouped_bar(ax, FTYPES, DATA_FTYPE, FTYPE_COLORS, "\u0394pass@1 (%)", "Impact by Fault Type", ylim=(-10, 70))
    plt.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.12)
    path = DOCS_DIR / "fig_fault_type_impact.png"
    plt.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close()
    print(f"  saved: {path}")


def fig_strategy_impact():
    """Grouped bar chart: delta-pass@1 by injection strategy."""
    fig, ax = plt.subplots(figsize=(7, 2.5))
    _grouped_bar(ax, STRATEGIES, DATA_STRAT, STRAT_COLORS, "\u0394pass@1 (%)", "Impact by Strategy", ylim=(-10, 65))
    plt.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.12)
    path = DOCS_DIR / "fig_strategy_impact.png"
    plt.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close()
    print(f"  saved: {path}")


if __name__ == "__main__":
    print("Generating README figures (paper style)...")
    fig_fault_type_impact()
    fig_strategy_impact()
    print("Done.")
