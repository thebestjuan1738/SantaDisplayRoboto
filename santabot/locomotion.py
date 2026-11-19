"""Low-level backends: the place a trained ONNX policy plugs in.

Both backends answer the same question once per control step:

    targets(velocity_cmd, t, hands) -> joint position targets for all joints

* `OnnxPolicy` runs an export from the TA's LearningRL pipeline: a run
  directory holding `config.yaml`, `policy.onnx` and `policy.onnx.data`
  (written by LearningRLlab's play/export script). Observation assembly,
  action processing and the ONNX session are the TA's own LearningRLsim code,
  so the policy sees exactly what LearningRLsim's sim2sim replay would feed it.
  An export of `LearningRL-RPO-LocoManipulation-v0` also observes `hand_track`
  (`[left_active, right_active, left_xyz, right_xyz]`, wrist points in the
  yaw-aligned root frame); `has_hands` is then True and the policy drives the
  arms as well as the legs.
* `ScriptedGait` is the pre-training stand-in. It steps the legs in a fixed
  pattern while the pelvis is carried along the commanded path by the assist
  weld. It is NOT a walking controller and is always reported as ASSISTED.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np

from santabot.robot import JOINT_NAMES, default_gains, default_pose


class RobotView:
    """The attribute names LearningRLsim's observation library reads (`ctx.sim.*`)."""

    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData, jmap):
        self.m, self.d, self.jmap = model, data, jmap
        j = model.body("base_link").jntadr[0]
        self.qa = model.jnt_qposadr[j]
        self.va = model.jnt_dofadr[j]

    @property
    def time(self):
        return float(self.d.time)

    @property
    def joint_pos(self):
        return self.d.qpos[self.jmap.qpos].copy()

    @property
    def joint_vel(self):
        return self.d.qvel[self.jmap.dof].copy()

    @property
    def base_pos_w(self):
        return self.d.qpos[self.qa : self.qa + 3].copy()

    @property
    def base_quat_w(self):
        return self.d.qpos[self.qa + 3 : self.qa + 7].copy()

    @property
    def base_rot_w(self):
        r = np.zeros(9)
        mujoco.mju_quat2Mat(r, self.base_quat_w)
        return r.reshape(3, 3)

    @property
    def base_lin_vel_w(self):
        return self.d.qvel[self.va : self.va + 3].copy()

    @property
    def base_lin_vel_b(self):
        return self.base_rot_w.T @ self.base_lin_vel_w

    @property
    def base_ang_vel_b(self):
        return self.d.qvel[self.va + 3 : self.va + 6].copy()

    @property
    def projected_gravity_b(self):
        return self.base_rot_w.T @ np.array([0.0, 0.0, -1.0])

    @property
    def heading_w(self):
        f = self.base_rot_w[:, 0]
        return float(np.arctan2(f[1], f[0]))


class _Commands:
    """`ctx.commands.value(name)`: the high-level controller's latest commands."""

    SUPPORTED = ("base_velocity", "hand_track")

    def __init__(self):
        self.velocity = np.zeros(3)
        self.hands = np.zeros(8)  # all-zero = the training side's idle row

    def value(self, name: str) -> np.ndarray:
        if name == "base_velocity":
            return self.velocity.copy()
        if name == "hand_track":
            return self.hands.copy()
        raise KeyError(
            f"the policy observes command '{name}', which the SantaBot controller does not produce. "
            f"Supported: {self.SUPPORTED}."
        )


class OnnxPolicy:
    name = "onnx"

    def __init__(self, run_dir: str | Path, model, data, jmap_factory):
        try:
            from LearningRLsim import actions as act_lib
            from LearningRLsim import observations as obs_lib
            from LearningRLsim import runconfig
            from LearningRLsim.actions import ActuatorCommand
            from LearningRLsim.policy import Policy
        except ImportError as exc:  # pragma: no cover - environment problem
            raise ImportError(
                "Running an ONNX export needs the TA's LearningRLsim package. Install it with:\n"
                '  pip install "LearningRLsim @ git+https://github.com/mark-helwig/LearningRL#subdirectory=LearningRLsim"'
            ) from exc
        self._obs_lib = obs_lib
        self.cfg = runconfig.load(run_dir)
        if self.cfg.robot not in (None, "roboparty_rpo"):
            raise ValueError(f"{run_dir}: export is for robot '{self.cfg.robot}', not roboparty_rpo")
        self.joint_order = tuple(self.cfg.joint_order)
        self.jmap = jmap_factory(self.joint_order)
        unsupported = [c.name for c in self.cfg.commands if c.name not in _Commands.SUPPORTED]
        if unsupported:
            raise ValueError(f"{run_dir}: export declares command(s) {unsupported}; supported: {_Commands.SUPPORTED}")
        self.has_hands = any(c.name == "hand_track" for c in self.cfg.commands)
        self.policy = Policy(Path(run_dir) / "policy.onnx", self.cfg)
        self.terms = act_lib.build(self.cfg)
        self.command = ActuatorCommand.nominal(self.cfg)
        self.commands = _Commands()
        self.view = RobotView(model, data, self.jmap)
        self.ctx = SimpleNamespace(
            cfg=self.cfg, sim=self.view, commands=self.commands, last_action=self._reset_action(), episode_time=0.0
        )
        self.default_pos = self.cfg.default_joint_pos.copy()
        self.kp = self.cfg.actuators.stiffness.copy()
        self.kd = self.cfg.actuators.damping.copy()
        self.effort = self.cfg.actuators.effort_limit.copy()
        self.sim_dt = self.cfg.sim_dt
        self.decimation = self.cfg.decimation
        self.t_start = None
        self.last_raw = self.ctx.last_action.copy()

    def _reset_action(self):
        return np.concatenate([t.reset_action for t in self.terms]) if self.terms else np.zeros(0)

    def apply_to_model(self, model):
        """Armature/friction as trained (LearningRLsim does the same)."""
        model.dof_armature[self.jmap.dof] = self.cfg.actuators.armature
        model.dof_frictionloss[self.jmap.dof] = self.cfg.actuators.friction

    def targets(self, velocity: np.ndarray, t: float, hands: np.ndarray | None = None) -> np.ndarray:
        if self.t_start is None:
            self.t_start = t
        self.ctx.episode_time = t - self.t_start
        self.commands.velocity = np.asarray(velocity, float)
        self.commands.hands = np.zeros(8) if hands is None else np.asarray(hands, float)
        obs = self._obs_lib.assemble(self.ctx)
        raw = self.policy(obs)
        for term, tc in zip(self.terms, self.cfg.actions.terms):
            a, b = tc.slice
            term.process(raw[a:b])
            term.apply(self.command)
        self.ctx.last_action = raw
        self.last_raw = raw
        return self.command.joint_pos_target.copy()


class ScriptedGait:
    """Pre-training stand-in: a fixed alternating stepping pattern.

    Only meaningful together with the assist weld, which carries the pelvis.
    """

    name = "assisted-scripted-gait"
    has_hands = False

    def __init__(self, cfg: dict, model, data, jmap_factory):
        self.a = cfg["assist"]
        self.joint_order = JOINT_NAMES
        self.jmap = jmap_factory(self.joint_order)
        self.default_pos = default_pose(self.joint_order)
        self.kp, self.kd, self.effort = default_gains(self.joint_order)
        self.sim_dt = cfg["control"]["sim_dt"]
        self.decimation = cfg["control"]["decimation"]
        self.phase = 0.0
        self.amp = 0.0
        self.last_t = None
        i = self.jmap.index
        self.idx = {
            side: (i[f"{side}_thigh_pitch_joint"], i[f"{side}_knee_joint"], i[f"{side}_ankle_pitch_joint"])
            for side in ("left", "right")
        }
        self.last_raw = np.zeros(0)

    def apply_to_model(self, model):
        pass

    def targets(self, velocity: np.ndarray, t: float, hands: np.ndarray | None = None) -> np.ndarray:
        dt = 0.0 if self.last_t is None else t - self.last_t
        self.last_t = t
        vx, _, wz = velocity
        drive = min(1.0, abs(vx) / 0.15 + self.a["turn_step_scale"] * abs(wz) / 0.3)
        self.amp += np.clip(drive - self.amp, -2.0 * dt, 2.0 * dt)
        if self.amp > 1e-3:
            self.phase = (self.phase + 2 * np.pi * self.a["gait_hz"] * dt) % (2 * np.pi)
        q = self.default_pos.copy()
        stride = np.clip(vx / 0.25, -1.0, 1.0)
        for side, ph in (("left", self.phase), ("right", self.phase + np.pi)):
            hip, knee, ankle = self.idx[side]
            lift = max(0.0, np.sin(ph)) * self.amp
            swing = np.cos(ph) * self.amp * stride
            q[hip] += -self.a["hip_amp"] * (lift * 0.8 + 0.5 * swing)
            q[knee] += self.a["knee_amp"] * lift
            q[ankle] += -self.a["ankle_amp"] * lift + 0.5 * self.a["hip_amp"] * 0.5 * swing
        return q
