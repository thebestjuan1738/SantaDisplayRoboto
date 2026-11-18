"""Two diagnostic plots per evaluated trial (Stage 2 asks for two)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

INK = "#1f2430"
C1, C2, C3 = "#b3261e", "#1b6e3a", "#c9a227"


def _spans(ax, t, holding, color="#000000"):
    on = np.asarray(holding) != ""
    edges = np.flatnonzero(np.diff(on.astype(int)))
    starts = [0] if on[0] else []
    starts += [e + 1 for e in edges if not on[e]]
    ends = [e + 1 for e in edges if on[e]] + ([len(on) - 1] if on[-1] else [])
    for a, b in zip(starts, ends):
        ax.axvspan(t[a], t[b], color=color, alpha=0.06, lw=0)


def diagnostic_plots(trial, out: Path, tag: str):
    L = trial.log
    t = np.asarray(L["t"])
    pose = np.asarray(L["pose"])
    gp = np.asarray(L["gift_pos"])
    lay = trial.layout

    # 1) top view: the base path (commanded = assist frame when assisted) and gift paths
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    w, d = lay.table_length, lay.table_depth
    ax.add_patch(plt.Rectangle((-w, 0), 2 * w, d, color="#d9b48f", alpha=0.5, lw=0))
    ax.plot([0, 0], [0, d], color="#8a6a4a", lw=1)
    ax.plot(pose[:, 0], pose[:, 1], color=INK, lw=1.6, label="pelvis path")
    for k, g in enumerate(lay.gifts):
        c = (C1, C2)[k % 2]
        ax.plot(gp[:, 3 * k], gp[:, 3 * k + 1], color=c, lw=1.4, label=f"{g.name.replace('_', ' ')} path")
        ax.add_patch(plt.Rectangle(g.goal[:2] - g.size / 2, g.size, g.size, fill=False, ec=c, ls="--", lw=1))
    ax.add_patch(plt.Circle(lay.tree_pos[:2], lay.tree_radius, color=C2, alpha=0.35, lw=0))
    ax.plot(*lay.home[:2], marker="s", color=INK, ms=6, ls="none", label="home")
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Top view: pelvis and gift trajectories; dashed squares are the goals", fontsize=10)
    ax.legend(fontsize=7, loc="lower left", frameon=False, ncol=2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / f"{tag}_topview.png", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)

    # 2) grip: squeeze force, gift heights, IK residual over time
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.5, 4.6), dpi=150, sharex=True)
    a1.plot(t, L["grip_force"], color=INK, lw=1.2)
    a1.set_ylabel("pad normal force (N)")
    _spans(a1, t, L["holding"])
    for k, g in enumerate(lay.gifts):
        a2.plot(t, gp[:, 3 * k + 2] - lay.table_height - g.size / 2, color=(C1, C2)[k % 2], lw=1.3,
                label=f"{g.name.replace('_', ' ')}")  # fmt: skip
    a2.axhline(0, color="#888888", lw=0.8, ls=":")
    a2.set_ylabel("gift bottom above table (m)")
    a2.set_xlabel("time (s)")
    a2.legend(fontsize=7, frameon=False)
    _spans(a2, t, L["holding"])
    for a in (a1, a2):
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    a1.set_title("Squeeze force while holding (shaded) and gift height", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / f"{tag}_grip.png", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
