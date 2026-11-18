"""Stage 2 evaluation: 5 nominal + 5 variation trials, a metrics table and plots.

  python run_eval.py                      # assisted, default config
  python run_eval.py --policy exports/walk
  python run_eval.py --variation-cm 3     # widen the declared variation

Nominal trials are deterministic (identical resets give identical rollouts),
so the variation trials move each gift's START by a uniform random offset of
up to +/- variation-cm in x and y. The controller is NOT told: it plans from
the nominal layout, the way the hardware will without object sensing.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from santabot.layout import ROOT, load_config


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy")
    ap.add_argument("--assist", choices=["auto", "full", "none"], default="auto")
    ap.add_argument("--config")
    ap.add_argument("--nominal", type=int, default=5)
    ap.add_argument("--variation", type=int, default=5)
    ap.add_argument("--variation-cm", type=float, default=2.0)
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    from santabot.plots import diagnostic_plots
    from santabot.sim import SantaTrial

    cfg = load_config(args.config)
    out = Path(args.out) if args.out else ROOT / "runs" / f"eval-{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    names = [g["name"] for g in cfg["scene"]["gifts"]]
    rows = []
    plan = [("nominal", i, None) for i in range(args.nominal)]
    for i in range(args.variation):
        rng = np.random.default_rng(100 + i)
        r = args.variation_cm / 100
        plan.append(("variation", i, {n: rng.uniform(-r, r, 2).round(4).tolist() for n in names}))

    for kind, i, perturb in plan:
        tag = f"{kind}{i + 1}"
        tr = SantaTrial(cfg, policy_dir=args.policy, assist=args.assist, perturb=perturb, seed=i)
        res = tr.run()
        tr.save(out, res, tag)
        L = tr.log
        # grip while CARRYING: held, between the lift and the start of the lowering
        carrying = (np.asarray(L["holding"]) != "") & np.array(
            [p.startswith(("back off", "carry", "step in place")) for p in L["phase"]]
        )
        grip = np.asarray(L["grip_force"])
        row = {
            "trial": tag,
            "perturb_cm": json.dumps({k: [round(x * 100, 1) for x in v] for k, v in perturb.items()}) if perturb else "",
            "success": res.success,
            "duration_s": round(res.duration_s, 1),
            "fell": res.fell,
            "max_tilt_deg": round(res.max_tilt_deg, 2),
            "min_carry_grip_N": round(float(grip[carrying].min()), 1) if carrying.any() else 0.0,
            "torque_sat_frac": round(res.saturated_frac, 4),
            "first_failure": res.first_failure or "",
        }
        for n, g in res.gifts.items():
            row[f"{n}_err_cm"] = round(g["xy_error_m"] * 100, 2)
            row[f"{n}_placed"] = g["placed"]
        rows.append(row)
        print(f"{tag:11s} success={res.success!s:5s} " + "  ".join(f"{n}={row[f'{n}_err_cm']}cm" for n in names))
        if i == 0:
            diagnostic_plots(tr, out, tag)

    with open(out / "metrics.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    md = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
    md += ["| " + " | ".join(str(v) for v in r.values()) + " |" for r in rows]
    (out / "metrics.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    ok = sum(r["success"] for r in rows)
    print(f"\n{ok}/{len(rows)} trials succeeded. Table: {out / 'metrics.md'}")


if __name__ == "__main__":
    main()
