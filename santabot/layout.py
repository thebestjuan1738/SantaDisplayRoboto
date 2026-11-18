"""Scene geometry from the brief, converted from inches to a metric world frame.

World frame (see config/santabot.yaml): tables end to end along x, front edges
on y = 0, seam at x = 0, robot facing +y. Left (from the robot) is -x.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

IN = 0.0254
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "santabot.yaml"


def load_config(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class Gift:
    name: str
    size: float  # cube edge, m
    mass: float
    start: np.ndarray  # centre (x, y, z), world
    goal: np.ndarray  # mirrored centre on the other table


@dataclass(frozen=True)
class Layout:
    table_length: float
    table_depth: float
    table_height: float
    table_top: float
    table_leg: float
    left_table_center: np.ndarray
    right_table_center: np.ndarray
    gifts: tuple[Gift, ...]
    home: np.ndarray  # (x, y, yaw)
    tree_pos: np.ndarray
    tree_radius: float
    tree_height: float

    def grasp_stand(self, gift_xy: np.ndarray, standoff: float) -> np.ndarray:
        """Pelvis pose (x, y, yaw) squarely in front of a gift, facing +y."""
        return np.array([gift_xy[0], -standoff, np.pi / 2])


def build_layout(cfg: dict, perturb: dict | None = None) -> Layout:
    """`perturb` maps gift name -> (dx, dy) metres, for variation trials."""
    s = cfg["scene"]
    t = s["table"]
    L, D, H = t["length_in"] * IN, t["depth_in"] * IN, t["height_in"] * IN
    setback = s["gift_front_setback_in"] * IN

    gifts: list[Gift] = []
    left_face = None  # x of the left face of the previously placed gift
    for g in s["gifts"]:
        size = g["size_in"] * IN
        if left_face is None:
            right_face = -g["side_offset_in"] * IN  # seam-side face, on the left table
        else:
            right_face = left_face - g["gap_left_of_previous_in"] * IN
        cx = right_face - size / 2
        left_face = right_face - size
        cy = setback + size / 2
        start = np.array([cx, cy, H + size / 2])
        if perturb and g["name"] in perturb:
            dx, dy = perturb[g["name"]]
            start = start + np.array([dx, dy, 0.0])
        # The goal mirrors the NOMINAL spot, so a perturbed start is still
        # judged against where the gift should end up.
        goal = np.array([-cx, cy, H + size / 2])
        gifts.append(Gift(g["name"], size, float(g["mass_kg"]), start, goal))

    home_d = s["home"]["distance_from_edge_in"] * IN
    tr = s["tree"]
    return Layout(
        table_length=L,
        table_depth=D,
        table_height=H,
        table_top=t["top_thickness_in"] * IN,
        table_leg=t["leg_in"] * IN,
        left_table_center=np.array([-L / 2, D / 2]),
        right_table_center=np.array([L / 2, D / 2]),
        gifts=tuple(gifts),
        home=np.array([0.0, -home_d, np.pi / 2]),
        tree_pos=np.array([0.0, tr["y_in"] * IN, H]),
        tree_radius=tr["base_radius_in"] * IN,
        tree_height=tr["height_in"] * IN,
    )
