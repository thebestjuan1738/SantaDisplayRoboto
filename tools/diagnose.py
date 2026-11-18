"""Reproduce the two controlled iterations recorded in docs/EXPERIMENT_LOG.md.

Each experiment changes ONE config value from the current tuning, reruns the
same nominal initial condition, and compares the same metrics.

  python tools/diagnose.py            # writes runs/diagnosis/diagnosis.md + plot
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from santabot.layout import ROOT, load_config  # noqa: E402
from santabot.sim import SantaTrial  # noqa: E402

EXPERIMENTS = [
    (
        "E1 friction creep",
        "Hypothesis: the large gift sinks through the grip because MuJoCo's default pyramidal friction cone "
        "(impratio 1) lets a squeezed contact creep. Prediction: an elliptic cone with impratio 10 holds the "
        "carry height and lets the large gift be placed.",
        [("physics.cone", "pyramidal"), ("physics.impratio", 1.0)],
    ),
    (
        "E2 forearm toe-in",
        "Hypothesis: with the forearms parallel (no toe-in) the pads touch only the gift's front edge, so the "
        "lift slides the pads over the gift instead of raising it. Prediction: 2 cm toe-in concentrates the "
        "squeeze at the wrists, near mid-depth, and the small gift is lifted and carried.",
        [("manipulation.toe_in_m", 0.0)],
    ),
]


def setp(cfg, dotted, value):
    keys = dotted.split(".")
    d = cfg
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = value


def summarise(tr, res):
    L = tr.log
    t = np.asarray(L["t"])
    gp = np.asarray(L["gift_pos"])
    hold = np.asarray(L["holding"])
    phase = np.asarray(L["phase"])
    out = {"success": res.success, "first_failure": res.first_failure or "-"}
    for k, g in enumerate(tr.layout.gifts):
        # carrying = held, after the lift and before the lowering starts
        moving = np.array([p.startswith(("back off", "carry", "step in place")) for p in phase])
        carrying = (hold == g.name) & moving
        z = gp[:, 3 * k + 2]
        if carrying.any():
            zc = z[carrying]
            out[f"{g.name} height lost while carrying (cm)"] = round(float(zc[0] - zc.min()) * 100, 1)
        else:
            out[f"{g.name} height lost while carrying (cm)"] = "never carried"
        out[f"{g.name} final error (cm)"] = round(res.gifts[g.name]["xy_error_m"] * 100, 1)
    return out, t, gp


def main():
    out = ROOT / "runs" / "diagnosis"
    out.mkdir(parents=True, exist_ok=True)
    base = load_config()
    lines = ["# Controlled iterations (reproduced by tools/diagnose.py)", ""]
    fig, axes = plt.subplots(1, len(EXPERIMENTS), figsize=(11, 3.6), dpi=150)
    for ax, (name, hyp, changes) in zip(axes, EXPERIMENTS):
        before = copy.deepcopy(base)
        for k, v in changes:
            setp(before, k, v)
        rows = {}
        for label, cfg in (("before", before), ("after (current)", base)):
            tr = SantaTrial(cfg)
            res = tr.run()
            s, t, gp = summarise(tr, res)
            rows[label] = s
            gi = 1 if "E1" in name else 0
            g = tr.layout.gifts[gi]
            ax.plot(t, gp[:, 3 * gi + 2] - tr.layout.table_height - g.size / 2, lw=1.3, label=label,
                    color="#b3261e" if label == "before" else "#1b6e3a")  # fmt: skip
            ax.set_title(f"{name}: {g.name.replace('_', ' ')} height", fontsize=9)
        ax.axhline(0, color="#888", lw=0.7, ls=":")
        ax.set_xlabel("time (s)")
        ax.set_ylabel("gift bottom above table (m)")
        ax.legend(fontsize=7, frameon=False)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        lines += [f"## {name}", "", hyp, "", "Change: " + ", ".join(f"`{k}` = {v}" for k, v in changes) + " (before)", ""]
        keys = list(rows["before"])
        lines += ["| metric | before | after (current) |", "|---|---|---|"]
        lines += [f"| {k} | {rows['before'][k]} | {rows['after (current)'][k]} |" for k in keys]
        lines.append("")
        print(name, rows)
    fig.tight_layout()
    fig.savefig(out / "diagnosis.png")
    (out / "diagnosis.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out / 'diagnosis.md'}")


if __name__ == "__main__":
    main()
