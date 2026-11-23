"""Run one SantaBot display trial in MuJoCo.

  python run_trial.py                         # assisted (no policy yet), headless
  python run_trial.py --viewer                # watch it live in the MuJoCo viewer
  python run_trial.py --video --gif           # record runs/<tag>/<tag>.mp4 / .gif
  python run_trial.py --policy exports/walk   # a trained export, unassisted
  python run_trial.py --policy exports/walk --assist full   # policy legs, pelvis held (bring-up)
  python run_trial.py --config my_tuning.yaml # try a tuned copy of config/santabot.yaml

A policy directory is what the TA's LearningRL play/export step writes:
config.yaml + policy.onnx + policy.onnx.data.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from santabot.layout import ROOT, load_config


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", help="exported run directory (config.yaml + policy.onnx + policy.onnx.data)")
    ap.add_argument("--assist", choices=["auto", "full", "none"], default="auto")
    ap.add_argument("--config", default=None, help="tuning file (default config/santabot.yaml)")
    ap.add_argument("--viewer", action="store_true", help="open the interactive MuJoCo viewer (real time)")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--gif", action="store_true")
    ap.add_argument("--view", default="three_quarter", help="camera: overview, three_quarter, top, grasp_left, grasp_right")
    ap.add_argument("--follow", action="store_true", help="camera follows the robot (view 'follow' by default)")
    ap.add_argument("--max-time", type=float, default=None)
    ap.add_argument("--perturb", default=None, help='JSON, e.g. {"small_gift": [0.02, -0.01]} (metres)')
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None, help="output directory (default runs/<timestamp>)")
    args = ap.parse_args(argv)

    from santabot.sim import SantaTrial

    cfg = load_config(args.config)
    perturb = json.loads(args.perturb) if args.perturb else None
    trial = SantaTrial(cfg, policy_dir=args.policy, assist=args.assist, perturb=perturb, seed=args.seed)
    tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else ROOT / "runs" / tag
    if args.policy and not trial.assisted:
        label = f"TRAINED POLICY ({Path(args.policy).name}) -- no assistance"
    elif args.policy:
        label = f"TRAINED POLICY ({Path(args.policy).name}) -- pelvis assisted"
    else:
        label = "ASSISTED: pelvis carried, legs scripted, arms by IK -- not trained"

    rec = None
    on_frame = None
    if args.video or args.gif:
        from santabot.render import Recorder

        view = "follow" if args.follow and args.view == "three_quarter" else args.view
        rec = Recorder(trial.model, view=view, label=label, track=args.follow)
        on_frame = rec.on_frame

    print(f"SantaBot trial  backend={trial.backend.name}  assisted={trial.assisted}")
    if args.viewer:
        import mujoco.viewer

        with mujoco.viewer.launch_passive(trial.model, trial.data) as v:
            v.cam.lookat[:] = (0, 0, 0.8)
            v.cam.distance, v.cam.azimuth, v.cam.elevation = 3.0, 110, -22

            def sync(tr, cmd, _f=on_frame):
                if _f:
                    _f(tr, cmd)
                v.sync()
                if not v.is_running():
                    raise KeyboardInterrupt

            try:
                res = trial.run(args.max_time, on_frame=sync, frame_every=1 / 60, realtime=True)
            except KeyboardInterrupt:
                print("viewer closed")
                return 1
            time.sleep(1.0)
    else:
        res = trial.run(args.max_time, on_frame=on_frame)

    trial.save(out, res, "trial")
    if rec is not None:
        if args.video:
            rec.save_mp4(out / "trial.mp4")
        if args.gif:
            rec.save_gif(out / "trial.gif")
    print(f"success={res.success}  completed={res.completed}  fell={res.fell}  sim {res.duration_s:.1f}s")
    for name, g in res.gifts.items():
        print(f"  {name:11s} placed={g['placed']!s:5s}  xy error {g['xy_error_m'] * 100:5.1f} cm  {g['why']}")
    if res.first_failure:
        print(f"  first failure: {res.first_failure}")
    print(f"outputs: {out}")
    return 0 if res.success else 2


if __name__ == "__main__":
    raise SystemExit(main())
