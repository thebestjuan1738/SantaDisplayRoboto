"""The SantaBot high-level controller.

A sequence of primitives, each of which runs until done:

  GoTo   -- unicycle navigation: turn in place, walk forward OR reverse, turn
            to a final heading. The lateral velocity command is always 0, so
            the robot never side-steps.
  ArmMove-- a min-jerk move of both arms to a target computed from the gift
            geometry in the pelvis frame when the move starts.
  Hold   -- stand still.

The arms are planned in one of two spaces:

  wrist space (a whole-body policy with a hand_track command): the arm moves
      are min-jerk paths between WRIST POINTS, sent to the policy as
      hand_track. No inverse kinematics -- the policy maps wrist targets to
      joints itself.
  joint space (assisted mode, or a walk-only policy): the wrist points are
      solved to arm joint angles by IK and written to the arm joints.

Every control step the controller outputs a `Command`:
  velocity  (vx, vy=0, wz)  -> the policy's base_velocity command
  hands     (8) or None     -> hand_track, in wrist space
  arm_q     (joint vector)  -> arm joint targets, in joint space
  phase     a label for logs and plots

Inputs are only the pelvis pose estimate (x, y, z, yaw) and the known table
layout -- no object sensing -- which is what the hardware will have.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from santabot.arm_ik import ArmIK, grasp_points
from santabot.layout import Gift, Layout
from santabot.robot import ARM_JOINTS


def wrap(a: float) -> float:
    return (a + np.pi) % (2 * np.pi) - np.pi


def min_jerk(s: float) -> float:
    s = min(max(s, 0.0), 1.0)
    return s**3 * (10 - 15 * s + 6 * s**2)


@dataclass
class Command:
    velocity: np.ndarray  # (vx, vy, wz), body frame
    arm_q: np.ndarray  # full joint vector; only arm entries are used
    phase: str
    holding: str | None = None
    deactivated: bool = False
    hands: np.ndarray | None = None  # hand_track (wrist space only)


@dataclass
class Ctx:
    t: float
    pose: np.ndarray  # x, y, z, yaw
    arm_q: np.ndarray
    vel: np.ndarray = field(default_factory=lambda: np.zeros(3))


# ---------------------------------------------------------------------------
class Primitive:
    label = "idle"

    def start(self, c: Ctx, ctl: MissionController) -> None:
        self.t0 = c.t

    def update(self, c: Ctx, ctl: MissionController) -> bool:
        raise NotImplementedError


class Hold(Primitive):
    def __init__(self, seconds: float, label: str = "hold"):
        self.seconds, self.label = seconds, label

    def update(self, c, ctl):
        ctl.station_keep(c)
        return c.t - self.t0 >= self.seconds and (ctl.stopped() or ctl.station_active)


class GoTo(Primitive):
    """Navigate the pelvis to (x, y) and optionally turn to `yaw`.

    `direction`: "forward", "reverse", or "auto" (reverse when the goal is
    behind and close, which is how a person backs away from a table).
    """

    def __init__(self, x, y, yaw=None, direction="auto", label="walk", speed=1.0):
        self.goal = np.array([x, y], dtype=float)
        self.yaw = yaw
        self.direction = direction
        self.label = label
        self.speed = speed

    def start(self, c, ctl):
        super().start(c, ctl)
        ctl.hold_pose = None  # moving on: nothing to keep station on until it arrives
        d = self.goal - c.pose[:2]
        self.reverse = False
        if self.direction == "reverse":
            self.reverse = True
        elif self.direction == "auto":
            behind = abs(wrap(np.arctan2(d[1], d[0]) - c.pose[3])) > np.deg2rad(110)
            self.reverse = behind and np.linalg.norm(d) < 0.6
        self.arrived = np.linalg.norm(d) < ctl.nav["pos_tolerance_m"]
        self.locked_heading = None

    def update(self, c, ctl):
        n = ctl.nav
        x, y, _, yaw = c.pose
        d = self.goal - np.array([x, y])
        dist = float(np.linalg.norm(d))
        if not self.arrived:
            if dist < n["pos_tolerance_m"]:
                self.arrived = True
            else:
                desired = np.arctan2(d[1], d[0]) + (np.pi if self.reverse else 0.0)
                if dist < 0.10:  # do not chase the bearing in the last few cm
                    if self.locked_heading is None:
                        self.locked_heading = desired
                    desired = self.locked_heading
                e = wrap(desired - yaw)
                if abs(e) > n["turn_in_place_above_rad"]:
                    ctl.set_velocity(0.0, n["k_heading"] * e, c)
                else:
                    vmax = (n["max_reverse_mps"] if self.reverse else n["max_forward_mps"]) * self.speed
                    # project the remaining distance on the heading so it stops, not orbits
                    along = dist * max(np.cos(e), 0.0)
                    v = min(vmax, n["k_distance"] * along + 0.03)
                    ctl.set_velocity(-v if self.reverse else v, n["k_heading"] * e, c)
                return False
        if self.yaw is None:
            ctl.set_velocity(0.0, 0.0, c)
            if ctl.stopped():
                ctl.hold_pose = np.array([self.goal[0], self.goal[1], yaw])
                return True
            return False
        e = wrap(self.yaw - yaw)
        if abs(e) > n["yaw_tolerance_rad"]:
            ctl.set_velocity(0.0, n["k_heading"] * e, c)
            return False
        ctl.set_velocity(0.0, 0.0, c)
        if ctl.stopped():
            ctl.hold_pose = np.array([self.goal[0], self.goal[1], self.yaw])
            return True
        return False


class ArmMove(Primitive):
    """Min-jerk move from the current arm state to `target(c, ctl)`.

    The state is the two wrist points in wrist space, the joint vector in joint
    space. `home=True` marks the move back to the default arms; in wrist space
    the hand command goes idle (all zero) when it ends, handing the arms back
    to the policy's own default.
    """

    def __init__(self, target, seconds, label, home=False, anchor="world"):
        """`anchor` (wrist space only): "world" ties the wrist path to the room, so
        the wrists keep reaching for the gift if the body sways while standing;
        "body" keeps it relative to the pelvis (poses carried while walking)."""
        self.target_fn, self.seconds, self.label = target, seconds, label
        self.home = home
        self.anchor = "body" if home else anchor

    def start(self, c, ctl):
        super().start(c, ctl)
        self.x0 = ctl.arm_state()
        self.x1 = self.target_fn(c, ctl)
        self.world = ctl.wrist_space and self.anchor == "world"
        if self.world:
            self.x0 = ctl.wrists_to_world(self.x0, c.pose)
            self.x1 = ctl.wrists_to_world(self.x1, c.pose)
        if ctl.wrist_space and not self.home:
            ctl.hands_active = True

    def update(self, c, ctl):
        ctl.station_keep(c)
        s = min_jerk((c.t - self.t0) / self.seconds)
        x = self.x0 + s * (self.x1 - self.x0)
        ctl.set_arm_state(ctl.wrists_to_pelvis(x, c.pose) if self.world else x)
        if s >= 1.0 and self.home:
            ctl.hands_active = False
        return s >= 1.0


class SetHolding(Primitive):
    def __init__(self, name):
        self.name = name
        self.label = "grip" if name else "release"

    def update(self, c, ctl):
        ctl.holding = self.name
        return True


class Deactivate(Primitive):
    label = "deactivated"

    def update(self, c, ctl):
        ctl.set_velocity(0.0, 0.0, c)
        ctl.deactivated = True
        return False  # terminal


# ---------------------------------------------------------------------------
class MissionController:
    def __init__(
        self,
        cfg: dict,
        layout: Layout,
        ik: ArmIK | None,
        q_default: np.ndarray,
        arm_idx: np.ndarray,
        wrist_space: bool = False,
        home_wrists: np.ndarray | None = None,
    ):
        """`wrist_space`: plan arm moves as wrist points for a policy's hand_track
        command (needs `home_wrists`, the default pose's wrist points, left then
        right, pelvis frame); otherwise solve them to joints with `ik`."""
        if wrist_space and home_wrists is None:
            raise ValueError("wrist_space needs home_wrists")
        if not wrist_space and ik is None:
            raise ValueError("joint-space arm planning needs an ArmIK")
        self.wrist_space = wrist_space
        self.home_wrists = None if home_wrists is None else np.asarray(home_wrists, float).copy()
        self.wrists = None if home_wrists is None else self.home_wrists.copy()
        self.hands_active = False
        self.hold_pose: np.ndarray | None = None  # (x, y, yaw) to keep station on while the arms work
        self.station_active = False
        self.cfg = cfg
        self.nav = cfg["navigation"]
        self.man = cfg["manipulation"]
        self.layout = layout
        self.ik = ik
        self.q_default = q_default.copy()
        self.arm_idx = arm_idx  # positions of the 10 arm joints in the joint vector
        self.arm_q = q_default.copy()
        self.vel = np.zeros(3)
        self.holding: str | None = None
        self.deactivated = False
        self.ik_error: dict[str, float] = {"left": 0.0, "right": 0.0}
        self.ik_seeds = ()
        if ik is not None:
            forward = q_default.copy()
            for side in ("left", "right"):
                for j, v in zip(ARM_JOINTS[side], (-0.7, 0.0, 0.0, 0.6, 0.0)):
                    forward[ik.jmap.index[j]] = v
            self.ik_seeds = (q_default.copy(), forward)
        self.dt = None
        self.plan = self._build_plan()
        self.k = -1
        self.current: Primitive | None = None

    # -- helpers used by primitives -----------------------------------------
    def set_velocity(self, vx: float, wz: float, c: Ctx) -> None:
        n = self.nav
        vx = float(np.clip(vx, -n["max_reverse_mps"], n["max_forward_mps"]))
        wz = float(np.clip(wz, -n["max_yaw_rate"], n["max_yaw_rate"]))
        dv, dw = n["accel_mps2"] * self.dt, n["yaw_accel"] * self.dt
        self.vel[0] += np.clip(vx - self.vel[0], -dv, dv)
        self.vel[1] = 0.0  # never side-step
        self.vel[2] += np.clip(wz - self.vel[2], -dw, dw)

    def stopped(self) -> bool:
        return abs(self.vel[0]) < 1e-3 and abs(self.vel[2]) < 1e-3

    def arm_state(self) -> np.ndarray:
        return self.wrists.copy() if self.wrist_space else self.arm_q.copy()

    def set_arm_state(self, x: np.ndarray) -> None:
        if self.wrist_space:
            self.wrists = np.asarray(x, float)
        else:
            self.arm_q = np.asarray(x, float)

    def hand_track(self) -> np.ndarray | None:
        """`[left_active, right_active, left_xyz, right_xyz]`; all zero when idle."""
        if not self.wrist_space:
            return None
        if not self.hands_active:
            return np.zeros(8)
        return np.concatenate([[1.0, 1.0], self.wrists])

    def station_keep(self, c: Ctx) -> None:
        """Stand still at `hold_pose`, stepping back to it if the body drifts.

        A trained policy can give ground while the arms reach forward. Forward/
        backward error beyond `start_m` (or heading error beyond `yaw_start_rad`)
        is walked back out -- never sideways -- until it is under `stop_m`.
        """
        sk = self.nav.get("station_keeping", {})
        if not sk.get("enabled", False) or self.hold_pose is None:
            self.station_active = False
            self.set_velocity(0.0, 0.0, c)
            return
        x, y, _, yaw = c.pose
        gx, gy, gyaw = self.hold_pose
        along = (gx - x) * np.cos(yaw) + (gy - y) * np.sin(yaw)
        e_yaw = wrap(gyaw - yaw)
        threshold = sk["stop_m"] if self.station_active else sk["start_m"]
        yaw_threshold = sk["yaw_stop_rad"] if self.station_active else sk["yaw_start_rad"]
        move = abs(along) > threshold
        turn = abs(e_yaw) > yaw_threshold
        self.station_active = move or turn
        vx = float(np.clip(self.nav["k_distance"] * along, -sk["max_mps"], sk["max_mps"])) if move else 0.0
        wz = self.nav["k_heading"] * e_yaw if turn else 0.0
        self.set_velocity(vx, wz, c)

    def wrists_to_world(self, w: np.ndarray, pose: np.ndarray) -> np.ndarray:
        """Two wrist points (6), yaw-aligned pelvis frame -> world."""
        x, y, z, yaw = pose
        cy, sy = np.cos(yaw), np.sin(yaw)
        out = np.empty(6)
        for k in (0, 3):
            px, py, pz = w[k : k + 3]
            out[k : k + 3] = (x + cy * px - sy * py, y + sy * px + cy * py, z + pz)
        return out

    def wrists_to_pelvis(self, w: np.ndarray, pose: np.ndarray) -> np.ndarray:
        """Two wrist points (6), world -> yaw-aligned pelvis frame."""
        return np.concatenate([self.to_pelvis(w[k : k + 3], pose) for k in (0, 3)])

    def to_pelvis(self, p_world: np.ndarray, pose: np.ndarray) -> np.ndarray:
        x, y, z, yaw = pose
        dx, dy = p_world[0] - x, p_world[1] - y
        c, s = np.cos(yaw), np.sin(yaw)
        return np.array([c * dx + s * dy, -s * dx + c * dy, p_world[2] - z])

    def _arm_pose(self, gift: Gift, where: str, half_gap: float, dx=0.0, dz=0.0, depth=None, at_stand=False):
        """Target fn: forearms along the gift sides, gift at its start or goal.

        The gift is located from the known layout and the pelvis pose. With
        `at_stand`, the pose used is the planned grasp stance rather than the
        current one (for arm moves made before stepping in).
        """

        def fn(c: Ctx, ctl: MissionController) -> np.ndarray:
            centre_w = gift.start if where == "start" else gift.goal
            pose = c.pose
            if at_stand:
                pose = np.array([centre_w[0], -self.nav["grasp_standoff_m"], c.pose[2], np.pi / 2])
            centre = self.to_pelvis(centre_w, pose) + np.array([dx, 0.0, dz])
            wrist, elbow = grasp_points(
                centre,
                gift.size,
                half_gap,
                self.cfg["robot"]["wrist_site_x"],
                self.man["grasp_depth_frac"] if depth is None else depth,
                toe_in=self.man["toe_in_m"],
            )
            if self.wrist_space:
                # the policy places the wrists itself: no IK
                return np.concatenate([wrist["left"], wrist["right"]])
            q, err = self.ik.solve(c.arm_q, wrist, elbow, extra_seeds=self.ik_seeds, w_elbow=self.man["ik_elbow_weight"])
            self.ik_error = err
            out = c.arm_q.copy()
            out[self.arm_idx] = q[self.arm_idx]
            return out

        return fn

    def _nominal_arms(self, c, ctl):
        if self.wrist_space:
            return self.home_wrists.copy()
        out = c.arm_q.copy()
        out[self.arm_idx] = self.q_default[self.arm_idx]
        return out

    # -- the display sequence ----------------------------------------------
    def _build_plan(self) -> list[Primitive]:
        lay, n, m = self.layout, self.nav, self.man
        pad_r = self.cfg["robot"]["forearm_pad"]["radius"]
        face = np.pi / 2  # facing the tables
        app, stand = n["approach_distance_m"], n["grasp_standoff_m"]
        T = m["move_time_s"]
        plan: list[Primitive] = [Hold(1.0, "activate")]
        # a trained policy crouches and its wrists sag under load: lift higher so gifts clear the tables
        lift = m["lift_m"] + (m.get("policy_extra_lift_m", 0.0) if self.wrist_space else 0.0)
        for g in lay.gifts:
            open_gap = g.size / 2 + pad_r + m["open_clearance_m"]
            grip_gap = g.size / 2 + pad_r - m["squeeze_inset_m"]
            back = -m["ready_pullback_m"]
            name = g.name
            plan += [
                GoTo(g.start[0], -app, face, label=f"approach {name}"),
                ArmMove(
                    self._arm_pose(g, "start", open_gap, dx=back, at_stand=True), T, f"ready arms {name}", anchor="body"
                ),
                GoTo(g.start[0], -stand, face, direction="forward", label=f"step in {name}", speed=0.5),
                ArmMove(self._arm_pose(g, "start", open_gap), T, f"reach {name}"),
                ArmMove(self._arm_pose(g, "start", grip_gap), m["squeeze_time_s"], f"squeeze {name}"),
                SetHolding(name),
                Hold(m["settle_time_s"], f"settle {name}"),
                ArmMove(
                    self._arm_pose(g, "start", grip_gap, dx=-m["carry_pullin_m"], dz=lift),
                    T,
                    f"lift {name}",
                ),
                GoTo(g.start[0], -stand - n["back_off_m"], None, direction="reverse", label=f"back off {name}"),
                GoTo(g.goal[0], -app, face, label=f"carry {name}"),
                GoTo(g.goal[0], -stand, face, direction="forward", label=f"step in place {name}", speed=0.5),
                ArmMove(
                    self._arm_pose(g, "goal", grip_gap, dz=m["place_drop_m"]),
                    T,
                    f"lower {name}",
                ),
                ArmMove(self._arm_pose(g, "goal", open_gap, dz=m["place_drop_m"]), T, f"release {name}"),
                SetHolding(None),
                ArmMove(self._arm_pose(g, "goal", open_gap, dx=back, dz=0.03), T, f"retract {name}"),
                GoTo(g.goal[0], -stand - n["back_off_m"], None, direction="reverse", label=f"back off {name}"),
                ArmMove(self._nominal_arms, T, "arms home", home=True),
            ]
        hx, hy, hyaw = lay.home
        plan += [
            GoTo(hx, hy, hyaw, label="return home"),
            Hold(1.0, "settle home"),
            Deactivate(),
        ]
        return plan

    # -- main entry ----------------------------------------------------------
    def step(self, t: float, pose: np.ndarray, dt: float) -> Command:
        self.dt = dt
        c = Ctx(t=t, pose=np.asarray(pose, float), arm_q=self.arm_q.copy())
        if self.current is None:
            self._advance(c)
        while self.current is not None and self.current.update(c, self):
            c.arm_q = self.arm_q.copy()
            self._advance(c)
        label = self.current.label if self.current else "done"
        return Command(
            self.vel.copy(), self.arm_q.copy(), label, self.holding, self.deactivated, hands=self.hand_track()
        )

    def _advance(self, c: Ctx) -> None:
        self.k += 1
        if self.k >= len(self.plan):
            self.current = None
            return
        self.current = self.plan[self.k]
        self.current.start(c, self)

    @property
    def progress(self) -> tuple[int, int]:
        return self.k, len(self.plan)


ARM_NAMES = ARM_JOINTS["left"] + ARM_JOINTS["right"]
