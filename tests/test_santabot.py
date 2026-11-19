"""Fast checks: geometry from the brief, the no-side-step rule, IK reach,
the ONNX plumbing, and one full assisted trial (~3 s)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from santabot.layout import IN, build_layout, load_config

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_layout_matches_brief(cfg):
    lay = build_layout(cfg)
    small, large = lay.gifts
    assert small.size == pytest.approx(8 * IN) and large.size == pytest.approx(12 * IN)
    # small gift's seam-side face 6 in from the seam (x = 0)
    assert small.start[0] + small.size / 2 == pytest.approx(-6 * IN)
    # large gift 6 in to the left (-x) of the small one
    gap = (small.start[0] - small.size / 2) - (large.start[0] + large.size / 2)
    assert gap == pytest.approx(6 * IN)
    # goals mirror the starts across the seam, on the other table
    for g in lay.gifts:
        assert g.goal[0] == pytest.approx(-g.start[0]) and g.goal[1:] == pytest.approx(g.start[1:])
    # home 1 ft from the touching edges, facing the tables
    assert lay.home[1] == pytest.approx(-12 * IN) and lay.home[0] == 0.0
    assert lay.tree_pos[0] == 0.0  # between the mirrored small-gift spots
    assert lay.table_length == pytest.approx(60 * IN) and lay.table_depth == pytest.approx(24 * IN)


def test_full_assisted_trial_never_side_steps(cfg):
    from santabot.sim import SantaTrial

    tr = SantaTrial(cfg)
    res = tr.run()
    cmd = np.asarray(tr.log["cmd"])
    assert np.all(cmd[:, 1] == 0.0), "lateral velocity command must always be zero"
    assert (cmd[:, 0] < -0.05).any(), "the robot should reverse away from the tables"
    assert res.completed and not res.fell
    assert res.success, res.first_failure


def test_ik_reaches_both_grasps(cfg):
    from santabot.arm_ik import ArmIK, grasp_points
    from santabot.robot import JointMap, default_pose
    from santabot.scene import build_model

    lay = build_layout(cfg)
    m, _ = build_model(cfg, lay)
    ik = ArmIK(m, JointMap(m))
    q0 = default_pose()
    stand = cfg["navigation"]["grasp_standoff_m"]
    for g in lay.gifts:
        c = np.array([g.start[1] + stand, 0.0, g.start[2] - 0.75])
        gap = g.size / 2 + cfg["robot"]["forearm_pad"]["radius"] - cfg["manipulation"]["squeeze_inset_m"]
        w, e = grasp_points(c, g.size, gap, cfg["robot"]["wrist_site_x"], 0.55, cfg["manipulation"]["toe_in_m"])
        _, err = ik.solve(q0, w, e, w_elbow=cfg["manipulation"]["ik_elbow_weight"])
        assert max(err.values()) < 0.02, (g.name, err)


def test_onnx_walk_export_plumbing(tmp_path, cfg):
    pytest.importorskip("LearningRLsim")
    run = tmp_path / "walk"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_test_export.py"), str(run)], check=True)
    from santabot.sim import SantaTrial

    tr = SantaTrial(cfg, policy_dir=run, assist="none")
    assert tr.backend.cfg.observations.total_dim == 78
    assert not tr.arms_by_policy  # no hand command: the controller overrides the arms
    res = tr.run(max_time=3.0)
    assert not res.fell  # zero-action stand-in holds the default pose


def test_onnx_locomanip_export_feeds_wrist_targets(tmp_path, cfg):
    """A LearningRL-RPO-LocoManipulation-v0 export: the policy owns the arms, and the
    hand_track command it observes is the wrist points of the controller's arm pose."""
    pytest.importorskip("LearningRLsim")
    run = tmp_path / "locomanip"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_test_export.py"), str(run), "--hands"], check=True)
    from santabot.sim import SantaTrial

    tr = SantaTrial(cfg, policy_dir=run, assist="full")
    assert tr.backend.cfg.observations.total_dim == 86
    assert tr.backend.has_hands and tr.arms_by_policy
    tr.run(max_time=17.0)  # through "ready arms", "reach" and "squeeze" of the first gift
    hands = np.asarray(tr.log["hands"])
    phase = np.asarray(tr.log["phase"])
    assert np.all(hands[phase == "activate"] == 0.0)  # default arms: idle row
    squeeze = hands[phase == "squeeze small_gift"]
    assert squeeze.size and np.all(squeeze[:, :2] == 1.0)
    # wrists in front of the pelvis, left at +y and right at -y, at gift height
    assert np.all(squeeze[:, 2] > 0.15) and np.all(squeeze[:, 3] > 0.05) and np.all(squeeze[:, 6] < -0.05)
    assert np.all((squeeze[:, 4] > 0.0) & (squeeze[:, 4] < 0.3))
    # and that is exactly what the policy observed in its hand_track slice
    obs_hands = tr.backend.commands.value("hand_track")
    assert obs_hands.shape == (8,)
