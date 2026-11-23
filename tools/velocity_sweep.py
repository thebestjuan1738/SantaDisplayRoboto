"""Measure how a policy export tracks constant velocity commands, in open space.

  python tools/velocity_sweep.py exports/locomanip_walkv1_7999

For each command it resets the robot (away from the tables), holds the command
for `--hold` seconds and reports the mean forward speed and yaw rate over the
last half of the window, plus whether it fell. Run twice: arms free (hand
command idle) and arms raised to a "ready" wrist pose.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from santabot.sim import SantaTrial  # noqa: E402

READY = np.array([1, 1, 0.15, 0.23, 0.10, 0.15, -0.23, 0.10])  # wrists forward, wide, at gift height


def run_cmd(tr: SantaTrial, vx: float, wz: float, hands: np.ndarray, hold: float) -> dict:
    tr.reset()
    # open floor, away from the tables, facing -y
    qa = tr.view.qa
    tr.data.qpos[qa : qa + 3] = (0.0, -2.0, tr.cfg["robot"]["spawn_height_m"])
    tr.data.qpos[qa + 3 : qa + 7] = (np.cos(-np.pi / 4), 0, 0, np.sin(-np.pi / 4))
    mujoco.mj_forward(tr.model, tr.data)
    b = tr.backend
    b.t_start = None
    b.ctx.last_action = np.zeros_like(b.ctx.last_action)
    kp, kd, eff = b.kp, b.kd, b.effort
    dt_ctl = b.sim_dt * b.decimation
    xs, ys, yaws, ts = [], [], [], []
    fell = None
    settle = 1.0
    while tr.data.time < hold + settle:
        t = tr.data.time
        cmd = np.array([vx, 0.0, wz]) if t >= settle else np.zeros(3)
        h = hands if t >= settle else np.zeros(8)
        q_target = b.targets(cmd, t, h)
        for _ in range(b.decimation):
            q = tr.data.qpos[tr.jmap.qpos]
            qd = tr.data.qvel[tr.jmap.dof]
            tr.data.ctrl[tr.jmap.act] = np.clip(kp * (q_target - q) - kd * qd, -eff, eff)
            mujoco.mj_step(tr.model, tr.data)
        p = tr.view.base_pos_w
        xs.append(p[0]), ys.append(p[1]), yaws.append(tr.view.heading_w), ts.append(tr.data.time)
        if p[2] < 0.45 and fell is None:
            fell = round(tr.data.time - settle, 2)
            break
    ts, xs, ys, yaws = map(np.asarray, (ts, xs, ys, yaws))
    yaws = np.unwrap(yaws)
    m = ts >= settle + hold / 2
    if fell is not None or m.sum() < 3:
        return {"fwd": float("nan"), "yaw": float("nan"), "fell": fell}
    v = np.stack([np.gradient(xs[m], ts[m]), np.gradient(ys[m], ts[m])], 1)
    fwd = v[:, 0] * np.cos(yaws[m]) + v[:, 1] * np.sin(yaws[m])
    return {"fwd": float(fwd.mean()), "yaw": float(np.gradient(yaws[m], ts[m]).mean()), "fell": fell}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policy")
    ap.add_argument("--hold", type=float, default=6.0)
    a = ap.parse_args()
    tr = SantaTrial(policy_dir=a.policy, assist="none")
    tests = [(v, 0.0) for v in (0.05, 0.10, 0.15, 0.25, 0.40, 0.60, -0.12, -0.30)] + [
        (0.0, w) for w in (0.25, 0.45, -0.45, 0.80)
    ]
    print(f"{'arms':6s} {'cmd vx':>7s} {'cmd wz':>7s} | {'fwd m/s':>8s} {'yaw r/s':>8s}  fell")
    for arms, hands in (("free", np.zeros(8)), ("ready", READY)):
        for vx, wz in tests:
            r = run_cmd(tr, vx, wz, hands, a.hold)
            print(f"{arms:6s} {vx:+7.2f} {wz:+7.2f} | {r['fwd']:+8.3f} {r['yaw']:+8.3f}  {r['fell'] or ''}")


if __name__ == "__main__":
    main()
