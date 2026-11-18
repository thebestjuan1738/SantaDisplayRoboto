"""RPO joint data used when no policy export is loaded.

Transcribed from the TA's robot_description/robots/roboparty_rpo/joint_groups.py
(RoboParty's RPO_CFG). When an ONNX export IS loaded, its config.yaml supplies
the joint order, default pose and PD gains instead, and these are unused.
"""

from __future__ import annotations

import re

import mujoco
import numpy as np

JOINT_NAMES: tuple[str, ...] = (
    "left_thigh_yaw_joint", "left_thigh_roll_joint", "left_thigh_pitch_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_thigh_yaw_joint", "right_thigh_roll_joint", "right_thigh_pitch_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
    "torso_joint",
    "left_arm_pitch_joint", "left_arm_roll_joint", "left_arm_yaw_joint",
    "left_elbow_pitch_joint", "left_elbow_yaw_joint",
    "right_arm_pitch_joint", "right_arm_roll_joint", "right_arm_yaw_joint",
    "right_elbow_pitch_joint", "right_elbow_yaw_joint",
)  # fmt: skip

ARM_JOINTS = {
    side: tuple(f"{side}_{j}_joint" for j in ("arm_pitch", "arm_roll", "arm_yaw", "elbow_pitch", "elbow_yaw"))
    for side in ("left", "right")
}
LEG_JOINTS = tuple(n for n in JOINT_NAMES if "thigh" in n or "knee" in n or "ankle" in n)

_STIFFNESS = {
    r".*_thigh_(yaw|roll|pitch)_joint": 100.0, r".*_knee_joint": 150.0, r"torso_joint": 150.0,
    r".*_ankle_(pitch|roll)_joint": 40.0, r".*_arm_(pitch|roll|yaw)_joint": 40.0,
    r".*_elbow_pitch_joint": 30.0, r".*_elbow_yaw_joint": 20.0,
}  # fmt: skip
_DAMPING = {
    r".*_thigh_(yaw|roll|pitch)_joint": 3.3, r".*_knee_joint": 5.0, r"torso_joint": 5.0,
    r".*_ankle_(pitch|roll)_joint": 2.0, r".*_arm_(pitch|roll|yaw)_joint": 2.0,
    r".*_elbow_pitch_joint": 1.5, r".*_elbow_yaw_joint": 1.0,
}  # fmt: skip
_EFFORT = {r".*_(thigh|knee).*|torso_joint": 120.0, r".*": 27.0}

NOMINAL = {
    "left_thigh_pitch_joint": -0.1, "left_knee_joint": 0.3, "left_ankle_pitch_joint": -0.2,
    "left_arm_pitch_joint": 0.18, "left_arm_roll_joint": 0.06, "left_elbow_pitch_joint": 0.78,
    "right_thigh_pitch_joint": -0.1, "right_knee_joint": 0.3, "right_ankle_pitch_joint": -0.2,
    "right_arm_pitch_joint": 0.18, "right_arm_roll_joint": -0.06, "right_elbow_pitch_joint": 0.78,
}  # fmt: skip


def _lookup(table: dict[str, float], name: str) -> float:
    for pattern, value in table.items():
        if re.fullmatch(pattern, name):
            return value
    raise KeyError(name)


def default_gains(joint_order=JOINT_NAMES):
    kp = np.array([_lookup(_STIFFNESS, n) for n in joint_order])
    kd = np.array([_lookup(_DAMPING, n) for n in joint_order])
    effort = np.array([_lookup(_EFFORT, n) for n in joint_order])
    return kp, kd, effort


def default_pose(joint_order=JOINT_NAMES) -> np.ndarray:
    return np.array([NOMINAL.get(n, 0.0) for n in joint_order])


class JointMap:
    """Addresses of named joints and their motors in a compiled model."""

    def __init__(self, model: mujoco.MjModel, joint_order=JOINT_NAMES):
        self.names = tuple(joint_order)
        ids = [model.joint(n).id for n in self.names]
        self.qpos = np.array([model.jnt_qposadr[i] for i in ids])
        self.dof = np.array([model.jnt_dofadr[i] for i in ids])
        self.act = np.array([model.actuator(n).id for n in self.names])
        self.range = np.array([model.jnt_range[i] for i in ids])
        self.index = {n: k for k, n in enumerate(self.names)}

    def idx(self, names) -> np.ndarray:
        return np.array([self.index[n] for n in names])
