"""Offline figures with fixed utility scales, explicit missingness and data tables."""

from pathlib import Path
from typing import Any


def session_figures(path: Path, record: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with plt.rc_context(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "figure.constrained_layout.use": True,
        }
    ):
        fig, ax = plt.subplots(figsize=(7.2, 4))
        offers = record["offers"]
        for actor, color, marker, style in [
            ("human", "#226b5a", "o", "-"),
            ("agent", "#76589a", "s", "--"),
        ]:
            actor_offers = [o for o in offers if o["actor"] == actor]
            ax.plot(
                [o["elapsed_seconds"] for o in actor_offers],
                [o["human_utility"] for o in actor_offers],
                color=color,
                marker=marker,
                linestyle=style,
                label=f"{actor.title()} offers",
            )
        ax.set(
            xlabel="Elapsed time (seconds)",
            ylabel=f"Human utility ({record['human_provenance']})",
            ylim=(-0.02, 1.02),
            title="Committed offers · one session",
        )
        ax.grid(alpha=0.18)
        if offers:
            ax.legend(loc="best")
        else:
            ax.text(0.5, 0.5, "No offers were committed", ha="center", transform=ax.transAxes)
        for ext in ("png", "svg", "pdf"):
            fig.savefig(
                path / f"trajectory.{ext}",
                dpi=180,
                metadata={"Title": "NEGOTIATOR committed utility trajectory"},
            )
        plt.close(fig)
        geometry = record["reference"]
        if geometry:
            fig, ax = plt.subplots(figsize=(5.5, 4.8))
            points = record["utility_space"]
            ax.scatter(
                [p[0] for p in points],
                [p[1] for p in points],
                s=12,
                color="#b5c5be",
                alpha=0.6,
                rasterized=True,
                label="Domain outcomes",
            )
            front = sorted(geometry["pareto"])
            ax.plot(
                [p[0] for p in front],
                [p[1] for p in front],
                "o--",
                color="#226b5a",
                label="Pareto reference",
                markersize=4,
            )
            agreement = record["outcome"].get("utilities") if record["outcome"] else None
            if agreement:
                ax.scatter(
                    [agreement["human"]],
                    [agreement["agent"]],
                    color="#a95a30",
                    marker="*",
                    s=130,
                    label="Agreement",
                    zorder=4,
                )
            ax.set(
                xlabel=f"Human utility ({record['human_provenance']})",
                ylabel="Agent utility (assigned)",
                xlim=(-0.02, 1.02),
                ylim=(-0.02, 1.02),
                title="Reference utility space",
            )
            ax.legend(loc="best")
            ax.grid(alpha=0.18)
            for ext in ("png", "svg", "pdf"):
                fig.savefig(path / f"utility-space.{ext}", dpi=180)
            plt.close(fig)
        observations = record["observations"]
        if observations:
            fig, ax = plt.subplots(figsize=(7.2, 3.8))
            for field, color, marker in [("valence", "#226b5a", "o"), ("arousal", "#ad623d", "s")]:
                # None becomes a plotted gap, never a fabricated zero observation.
                values = [
                    o.get(field) if o.get(field) is not None else float("nan") for o in observations
                ]
                ax.plot(
                    [o["elapsed_seconds"] for o in observations],
                    values,
                    marker=marker,
                    color=color,
                    label=field.title(),
                )
            ax.set(
                xlabel="Elapsed time (seconds)",
                ylabel="Reported value",
                ylim=(-1.05, 1.05),
                title="Observations · sources and missing reasons in observations.csv",
            )
            ax.legend()
            ax.grid(alpha=0.18)
            for ext in ("png", "svg", "pdf"):
                fig.savefig(path / f"observations.{ext}", dpi=180)
            plt.close(fig)
