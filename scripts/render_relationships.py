"""Render the documented method/asset relationships, not experimental equivalence."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "docs/paper-relations.json").read_text(encoding="utf-8"))
fig, ax = plt.subplots(figsize=(12, 5.2), layout="constrained")
ax.set(xlim=(0, 12), ylim=(0, 5.2))
ax.axis("off")
for item in data["nodes"]:
    x, y = item["position"]
    ax.add_patch(
        FancyBboxPatch(
            (x, y), 2.05, 0.82, boxstyle="round,pad=.1", edgecolor="#236d60", facecolor="#f0f7f4"
        )
    )
    ax.text(
        x + 1.025, y + 0.41, item["label"], ha="center", va="center", fontsize=11, color="#173d34"
    )
for item in data["edges"]:
    color = "#0072B2" if item["kind"] == "method" else "#B65C00"
    ax.add_patch(
        FancyArrowPatch(
            item["start"],
            item["end"],
            arrowstyle="-|>",
            mutation_scale=13,
            connectionstyle="arc3,rad=" + str(item.get("rad", 0)),
            color=color,
            linestyle="-" if item["kind"] == "method" else "--",
        )
    )
    ax.text(
        *item["label_position"],
        item["label"],
        fontsize=9,
        ha="center",
        color=color,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 2},
    )
ax.text(
    6,
    4.92,
    "Published research relationships",
    ha="center",
    fontsize=17,
    weight="bold",
    color="#173d34",
)
ax.add_patch(
    FancyBboxPatch(
        (0.25, 0.3), 11.4, 0.78, boxstyle="round,pad=.1", facecolor="#edf2f8", edgecolor="#597396"
    )
)
ax.text(
    5.95,
    0.72,
    "NEGOTIATOR (IJCAI 2024) → maintained 2.0 engine\nCurrent software integration: all six independent paper companions",
    ha="center",
    va="center",
    fontsize=11,
    color="#243d5a",
)
ax.text(
    6,
    0.03,
    "Solid blue: method lineage · Dashed orange: shared published assets/profiles · Shared code does not imply experimental equivalence",
    ha="center",
    fontsize=8,
)
output = ROOT / "docs/images"
output.mkdir(exist_ok=True)
for suffix in ("svg", "pdf", "png"):
    fig.savefig(output / f"paper-relations.{suffix}", dpi=170)
plt.close(fig)
