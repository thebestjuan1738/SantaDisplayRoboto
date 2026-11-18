"""Pelvis-frame inverse kinematics for the forearm squeeze.

The Origin has no hands, so a gift is held between the two forearms. Each arm
(5 DoF) is solved for two points at once:

* the WRIST site (forearm tip), and
* the ELBOW site (forearm root),

so the forearm lies along the gift's side, pointing forward. Six targets on
five joints is over-determined; damped least squares finds the best fit and
weights the wrist higher, because the wrist is what sets the squeeze.

Solved on a private MjData whose floating base is pinned at the origin, so the
targets are pelvis-frame and independent of where the robot is walking.
"""

from __future__ import annotations

import mujoco
import numpy as np

from santabot.robot import ARM_JOINTS, JointMap


class ArmIK:
    def __init__(self, model: mujoco.MjModel, jmap: JointMap, base_height: float = 0.0):
        self.m = model
        self.d = mujoco.MjData(model)
        self.jmap = jmap
        self.d.qpos[:] = model.qpos0
        free = [j for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE]
        self.base_adr = model.jnt_qposadr[model.body("base_link").jntadr[0]]
        self._free = free
        self.sides = {}
        for side, names in ARM_JOINTS.items():
            ids = [model.joint(n).id for n in names]
            self.sides[side] = {
                "qadr": np.array([model.jnt_qposadr[i] for i in ids]),
                "dadr": np.array([model.jnt_dofadr[i] for i in ids]),
                "range": np.array([model.jnt_range[i] for i in ids]),
                "wrist": model.site(f"{side}_wrist").id,
                "elbow": model.site(f"{side}_elbow").id,
                "jmap_idx": jmap.idx(names),
            }

    def _pin_base(self):
        a = self.base_adr
        self.d.qpos[a : a + 3] = 0.0
        self.d.qpos[a + 3 : a + 7] = (1, 0, 0, 0)

    def fk(self, q_full: np.ndarray) -> dict:
        """Wrist/elbow positions (pelvis frame) for a full joint vector in jmap order."""
        self._pin_base()
        self.d.qpos[self.jmap.qpos] = q_full
        mujoco.mj_kinematics(self.m, self.d)
        out = {}
        for side, s in self.sides.items():
            out[side] = (self.d.site_xpos[s["wrist"]].copy(), self.d.site_xpos[s["elbow"]].copy())
        return out

    def solve(self, q_seed, wrist, elbow, extra_seeds=(), **kw):
        """Multi-start: the current pose plus `extra_seeds`; the best fit per side wins."""
        best_q = np.array(q_seed, dtype=float)
        best_err = {s: np.inf for s in self.sides}
        for seed in (q_seed, *extra_seeds):
            q, err = self._solve_once(seed, wrist, elbow, **kw)
            for side, s in self.sides.items():
                if err[side] < best_err[side] - 1e-4:
                    best_err[side] = err[side]
                    best_q[s["jmap_idx"]] = q[s["jmap_idx"]]
        return best_q, best_err

    def _solve_once(
        self,
        q_seed: np.ndarray,
        wrist: dict[str, np.ndarray],
        elbow: dict[str, np.ndarray],
        iters: int = 80,
        w_elbow: float = 0.5,
        damping: float = 0.02,
    ) -> tuple[np.ndarray, dict[str, float]]:
        """Returns (full joint vector with both arms solved, wrist error per side)."""
        q = np.array(q_seed, dtype=float)
        self._pin_base()
        self.d.qpos[self.jmap.qpos] = q
        jw = np.zeros((3, self.m.nv))
        je = np.zeros((3, self.m.nv))
        errs = {}
        for side, s in self.sides.items():
            for _ in range(iters):
                mujoco.mj_kinematics(self.m, self.d)
                mujoco.mj_comPos(self.m, self.d)
                ew = wrist[side] - self.d.site_xpos[s["wrist"]]
                ee = elbow[side] - self.d.site_xpos[s["elbow"]]
                mujoco.mj_jacSite(self.m, self.d, jw, None, s["wrist"])
                mujoco.mj_jacSite(self.m, self.d, je, None, s["elbow"])
                J = np.vstack([jw[:, s["dadr"]], w_elbow * je[:, s["dadr"]]])
                e = np.concatenate([ew, w_elbow * ee])
                if np.linalg.norm(ew) < 1e-4 and np.linalg.norm(ee) < 5e-3:
                    break
                dq = J.T @ np.linalg.solve(J @ J.T + damping**2 * np.eye(6), e)
                dq = np.clip(dq, -0.2, 0.2)
                qa = self.d.qpos[s["qadr"]] + dq
                self.d.qpos[s["qadr"]] = np.clip(qa, s["range"][:, 0] + 1e-3, s["range"][:, 1] - 1e-3)
            mujoco.mj_kinematics(self.m, self.d)
            errs[side] = float(np.linalg.norm(wrist[side] - self.d.site_xpos[s["wrist"]]))
            q[s["jmap_idx"]] = self.d.qpos[s["qadr"]]
        return q, errs


def grasp_points(
    centre: np.ndarray, size: float, half_gap: float, forearm_len: float, depth_frac: float, toe_in: float = 0.0
) -> tuple[dict, dict]:
    """Wrist and elbow targets (pelvis frame) for forearms along a gift's sides.

    `centre` is the gift centre in the pelvis frame; `half_gap` is the lateral
    distance from the gift's mid-plane to each forearm AXIS.
    """
    x_wrist = centre[0] - size / 2 + depth_frac * size
    wrist = {
        "left": np.array([x_wrist, centre[1] + half_gap, centre[2]]),
        "right": np.array([x_wrist, centre[1] - half_gap, centre[2]]),
    }
    # toe-in: elbows wider than wrists, so the squeeze is concentrated at the
    # wrists near the gift's mid-depth instead of at its front edge.
    elbow = {
        "left": wrist["left"] + np.array([-forearm_len, toe_in, 0.0]),
        "right": wrist["right"] + np.array([-forearm_len, -toe_in, 0.0]),
    }
    return wrist, elbow
