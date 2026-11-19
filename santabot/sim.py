"""One SantaBot trial in MuJoCo: scene + high-level controller + locomotion backend.

Loop (per control step, 1 / (sim_dt * decimation) Hz):

  pose  = pelvis estimate (sim: ground truth)
  cmd   = MissionController.step(pose)          velocity + arm targets
  hands = cmd.hands                              wrist points, planned directly (no IK)
  q*    = backend.targets(cmd.velocity, hands)   the policy: legs AND arms
  -- or, with no hand command (assisted mode, walk-only policy, arm_control = override):
  q*[arms] = cmd.arm_q[arms]                     IK arm joints from the controller
  decimation x { tau = clip(Kp (q* - q) - Kd qdot); mj_step; move assist frame }

The PD law, gains and effort clip are LearningRLsim's IdealPD equivalent.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import mujoco
import numpy as np

from santabot.arm_ik import ArmIK
from santabot.layout import Layout, build_layout, load_config
from santabot.locomotion import OnnxPolicy, RobotView, ScriptedGait
from santabot.mission import MissionController
from santabot.robot import ARM_JOINTS, JointMap
from santabot.scene import ASSIST_MOCAP, ASSIST_WELD, build_model


@dataclass
class TrialResult:
    mode: str
    assisted: bool
    duration_s: float
    completed: bool
    fell: bool
    fall_time: float | None
    gifts: dict = field(default_factory=dict)
    max_tilt_deg: float = 0.0
    saturated_frac: float = 0.0
    phases: list = field(default_factory=list)
    first_failure: str | None = None
    wall_s: float = 0.0

    @property
    def success(self) -> bool:
        return self.completed and not self.fell and all(g["placed"] for g in self.gifts.values())

    def to_dict(self):
        d = self.__dict__.copy()
        d["success"] = self.success
        return d


class SantaTrial:
    def __init__(
        self,
        cfg: dict | None = None,
        policy_dir: str | Path | None = None,
        assist: str = "auto",
        perturb: dict | None = None,
        seed: int = 0,
    ):
        self.cfg = cfg or load_config()
        self.layout: Layout = build_layout(self.cfg, perturb)
        self.model, self.spec = build_model(self.cfg, self.layout)
        self.data = mujoco.MjData(self.model)
        self.rng = np.random.default_rng(seed)

        def jmap_factory(order):
            return JointMap(self.model, order)

        if policy_dir:
            self.backend = OnnxPolicy(policy_dir, self.model, self.data, jmap_factory)
        else:
            self.backend = ScriptedGait(self.cfg, self.model, self.data, jmap_factory)
        if assist == "auto":
            assist = "none" if policy_dir else "full"
        if assist == "none" and not policy_dir:
            raise ValueError("assist='none' needs a policy: the scripted gait cannot balance on its own.")
        self.assisted = assist == "full"
        self.backend.apply_to_model(self.model)
        self.model.opt.timestep = self.backend.sim_dt
        phys = self.cfg.get("physics", {})
        if phys.get("cone") == "elliptic":
            self.model.opt.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        self.model.opt.impratio = float(phys.get("impratio", 1.0))
        self.jmap: JointMap = self.backend.jmap
        self.view = RobotView(self.model, self.data, self.jmap)

        arm_names = ARM_JOINTS["left"] + ARM_JOINTS["right"]
        self.arm_idx = self.jmap.idx(arm_names)
        self.torso_idx = self.jmap.idx(["torso_joint"])
        self.ik = ArmIK(self.model, self.jmap)
        arm_control = self.cfg["control"].get("arm_control", "auto")
        if arm_control == "policy" and not self.backend.has_hands:
            raise ValueError("control.arm_control = policy, but the backend has no hand_track command")
        self.arms_by_policy = self.backend.has_hands and arm_control != "override"
        # wrist space: the policy maps wrist targets to joints, so the controller
        # plans wrist points directly. One forward-kinematics call gives the
        # default arms' wrist points, the start and end of every arm sequence.
        home = self.ik.fk(self.backend.default_pos)
        self.ctl = MissionController(
            self.cfg,
            self.layout,
            None if self.arms_by_policy else self.ik,
            self.backend.default_pos,
            self.arm_idx,
            wrist_space=self.arms_by_policy,
            home_wrists=np.concatenate([home["left"][0], home["right"][0]]),
        )
        self.hold_scale = self.cfg["manipulation"]["arm_gain_scale_holding"]

        self.mocap_id = self.model.body(ASSIST_MOCAP).mocapid[0]
        self.weld_id = self.model.equality(ASSIST_WELD).id
        self.gift_ids = {g.name: self.model.body(g.name).id for g in self.layout.gifts}
        self.pad_geoms = [self.model.geom(f"{s}_forearm_pad").id for s in ("left", "right")]
        self.gift_geoms = {g.name: self.model.geom(f"{g.name}_box").id for g in self.layout.gifts}
        self.reset()

    # ------------------------------------------------------------------
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.hands = np.zeros(8)
        hx, hy, hyaw = self.layout.home
        qa = self.view.qa
        z0 = self.cfg["robot"]["spawn_height_m"]
        self.data.qpos[qa : qa + 3] = (hx, hy, z0)
        self.data.qpos[qa + 3 : qa + 7] = (np.cos(hyaw / 2), 0, 0, np.sin(hyaw / 2))
        self.data.qpos[self.jmap.qpos] = self.backend.default_pos
        self.data.eq_active[self.weld_id] = 1 if self.assisted else 0
        self.assist_pose = np.array([hx, hy, hyaw])
        self._set_mocap()
        mujoco.mj_forward(self.model, self.data)
        self.log: dict[str, list] = {k: [] for k in LOG_KEYS}

    def _set_mocap(self):
        x, y, yaw = self.assist_pose
        self.data.mocap_pos[self.mocap_id] = (x, y, self.cfg["robot"]["spawn_height_m"])
        self.data.mocap_quat[self.mocap_id] = (np.cos(yaw / 2), 0, 0, np.sin(yaw / 2))

    def hand_command(self, arm_q: np.ndarray) -> np.ndarray:
        """hand_track for an IK arm pose (joint-space planning only, e.g. a policy
        run with arm_control = override); in wrist space the controller sends
        `cmd.hands` directly.

        Wrist points (the `<side>_wrist` sites, 0.135 m along each forearm -- the
        same points LearningRL-RPO-LocoManipulation-v0 tracks) of the commanded
        arm pose, by forward kinematics with the pelvis at the origin. Both hands
        are active whenever the arms are away from their default pose; otherwise
        the row is all zero, the training side's idle command, and the policy
        holds its own arms.
        """
        arms = arm_q[self.arm_idx] - self.backend.default_pos[self.arm_idx]
        if np.max(np.abs(arms)) < 1e-3:
            return np.zeros(8)
        fk = self.ik.fk(arm_q)
        return np.concatenate([[1.0, 1.0], fk["left"][0], fk["right"][0]])

    def wrist_points(self) -> np.ndarray:
        """Actual wrist points (left, right) in the pelvis frame, from the measured joints."""
        fk = self.ik.fk(self.data.qpos[self.jmap.qpos])
        return np.concatenate([fk["left"][0], fk["right"][0]])

    def pose_estimate(self) -> np.ndarray:
        p = self.view.base_pos_w
        return np.array([p[0], p[1], p[2], self.view.heading_w])

    def pad_force(self, gift: str) -> float:
        """Total normal force between both forearm pads and a gift (N)."""
        total = 0.0
        f6 = np.zeros(6)
        gid = self.gift_geoms[gift]
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            pair = {c.geom1, c.geom2}
            if gid in pair and pair & set(self.pad_geoms):
                mujoco.mj_contactForce(self.model, self.data, i, f6)
                total += abs(f6[0])
        return total

    # ------------------------------------------------------------------
    def run(self, max_time: float | None = None, on_frame=None, frame_every: float = 1 / 30, realtime=False):
        cfg = self.cfg
        max_time = max_time or cfg["trial"]["max_time_s"]
        dt_ctl = self.backend.sim_dt * self.backend.decimation
        res = TrialResult(
            mode=self.backend.name, assisted=self.assisted, duration_s=0.0, completed=False, fell=False, fall_time=None
        )
        kp, kd, eff = self.backend.kp.copy(), self.backend.kd.copy(), self.backend.effort.copy()
        sat_steps = steps = 0
        next_frame = 0.0
        last_phase = None
        wall0 = time.perf_counter()
        while self.data.time < max_time:
            t = self.data.time
            pose = self.pose_estimate()
            cmd = self.ctl.step(t, pose, dt_ctl)
            if cmd.phase != last_phase:
                res.phases.append((round(t, 2), cmd.phase))
                last_phase = cmd.phase
            self.hands = cmd.hands if cmd.hands is not None else self.hand_command(cmd.arm_q)
            q_target = self.backend.targets(cmd.velocity, t, self.hands)
            kp_now = kp.copy()
            if not self.arms_by_policy:
                q_target[self.arm_idx] = cmd.arm_q[self.arm_idx]
                q_target[self.torso_idx] = self.backend.default_pos[self.torso_idx]
                if cmd.holding:
                    kp_now[self.arm_idx] *= self.hold_scale
            for _ in range(self.backend.decimation):
                q = self.data.qpos[self.jmap.qpos]
                qd = self.data.qvel[self.jmap.dof]
                tau = kp_now * (q_target - q) - kd * qd
                sat = np.abs(tau) > eff
                tau = np.clip(tau, -eff, eff)
                self.data.ctrl[self.jmap.act] = tau
                if self.assisted:
                    vx, _, wz = cmd.velocity
                    x, y, yaw = self.assist_pose
                    dt = self.model.opt.timestep
                    self.assist_pose = np.array(
                        [x + vx * np.cos(yaw) * dt, y + vx * np.sin(yaw) * dt, yaw + wz * dt]
                    )
                    self._set_mocap()
                mujoco.mj_step(self.model, self.data)
                steps += 1
                sat_steps += int(sat.any())
            self._record(cmd, pose, q_target)
            g = self.view.projected_gravity_b
            tilt = float(np.degrees(np.arccos(np.clip(-g[2], -1, 1))))
            res.max_tilt_deg = max(res.max_tilt_deg, tilt)
            if not res.fell and (self.view.base_pos_w[2] < cfg["trial"]["fall_height_m"] or tilt > 60):
                res.fell, res.fall_time = True, float(self.data.time)
                res.first_failure = res.first_failure or f"fell at {self.data.time:.2f}s during '{cmd.phase}'"
                break
            if on_frame is not None and self.data.time >= next_frame:
                on_frame(self, cmd)
                next_frame += frame_every
            if realtime:
                lag = self.data.time - (time.perf_counter() - wall0)
                if lag > 0:
                    time.sleep(lag)
            if cmd.deactivated and self.data.time - self._deact_t(cmd) > 1.5:
                res.completed = True
                break
        res.duration_s = float(self.data.time)
        res.saturated_frac = sat_steps / max(steps, 1)
        res.wall_s = time.perf_counter() - wall0
        res.gifts = self.evaluate_gifts()
        if res.first_failure is None:
            for name, gr in res.gifts.items():
                if not gr["placed"]:
                    res.first_failure = f"{name} not placed: {gr['why']}"
                    break
        if res.first_failure is None and not res.completed:
            res.first_failure = f"timed out in '{last_phase}'"
        return res

    def _deact_t(self, cmd):
        if not hasattr(self, "_deact_time"):
            self._deact_time = self.data.time
        return self._deact_time

    def evaluate_gifts(self) -> dict:
        out = {}
        tol = self.cfg["trial"]["gift_place_tolerance_m"]
        for g in self.layout.gifts:
            bid = self.gift_ids[g.name]
            p = self.data.xpos[bid].copy()
            up = self.data.xmat[bid].reshape(3, 3)[:, 2]
            err_xy = float(np.linalg.norm(p[:2] - g.goal[:2]))
            on_table = abs(p[2] - g.goal[2]) < 0.02
            upright = up[2] > np.cos(np.deg2rad(15))
            placed = err_xy < tol and on_table and upright
            why = "" if placed else ", ".join(
                w
                for w, bad in (
                    (f"xy error {err_xy * 100:.1f} cm", err_xy >= tol),
                    (f"height {p[2]:.3f} m vs {g.goal[2]:.3f}", not on_table),
                    ("tipped", not upright),
                )
                if bad
            )
            out[g.name] = {
                "final_pos": p.round(4).tolist(),
                "goal": g.goal.round(4).tolist(),
                "xy_error_m": round(err_xy, 4),
                "placed": bool(placed),
                "why": why,
            }
        return out

    def _record(self, cmd, pose, q_target):
        L = self.log
        L["t"].append(self.data.time)
        L["phase"].append(cmd.phase)
        L["pose"].append(pose)
        L["cmd"].append(cmd.velocity)
        L["q"].append(self.data.qpos[self.jmap.qpos].copy())
        L["q_target"].append(q_target.copy())
        L["tau"].append(self.data.ctrl[self.jmap.act].copy())
        L["gift_pos"].append(np.concatenate([self.data.xpos[i] for i in self.gift_ids.values()]))
        L["grip_force"].append(self.pad_force(cmd.holding) if cmd.holding else 0.0)
        L["holding"].append(cmd.holding or "")
        L["ik_err"].append(max(self.ctl.ik_error.values()))
        L["hands"].append(self.hands.copy())
        active = self.hands[0] > 0.5
        L["hand_err"].append(
            float(np.linalg.norm((self.wrist_points() - self.hands[2:]).reshape(2, 3), axis=1).max()) if active else 0.0
        )
        L["assist_err"].append(
            float(np.linalg.norm(self.assist_pose[:2] - pose[:2])) if self.assisted else 0.0
        )

    def save(self, out_dir: Path, res: TrialResult, tag: str):
        out_dir.mkdir(parents=True, exist_ok=True)
        arrays = {k: np.asarray(v) for k, v in self.log.items() if k not in ("phase", "holding")}
        np.savez_compressed(
            out_dir / f"{tag}_trace.npz",
            phase=np.asarray(self.log["phase"]),
            holding=np.asarray(self.log["holding"]),
            joint_order=np.asarray(self.jmap.names),
            gift_names=np.asarray(list(self.gift_ids)),
            **arrays,
        )
        with open(out_dir / f"{tag}_result.json", "w", encoding="utf-8") as fh:
            json.dump(res.to_dict(), fh, indent=2)


LOG_KEYS = (
    "t", "phase", "pose", "cmd", "q", "q_target", "tau", "gift_pos",
    "grip_force", "holding", "ik_err", "assist_err", "hands", "hand_err",
)  # fmt: skip
