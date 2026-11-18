"""Build the MuJoCo scene: the unmodified RPO MJCF plus tables, gifts and a tree.

The robot MJCF is loaded verbatim from the pinned rpo_description (the same
file the TA's LearningRLsim replays) and only *added to*:

* a wrist site and a capsule contact pad on each forearm (elbow_yaw_link),
* a mocap frame and a soft weld to the pelvis, used only in assisted mode.

Nothing about the robot's joints, masses or actuators is changed here.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np

from santabot.layout import ROOT, Layout

SIDES = ("left", "right")
ASSIST_WELD = "assist_weld"
ASSIST_MOCAP = "assist_frame"


def _mat(spec, name, rgba, **kw):
    m = spec.add_material()
    m.name = name
    m.rgba = rgba
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def build_spec(cfg: dict, layout: Layout) -> mujoco.MjSpec:
    mjcf = Path(cfg["robot"]["mjcf"])
    if not mjcf.is_absolute():
        mjcf = ROOT / mjcf
    if not mjcf.is_file():
        raise FileNotFoundError(f"{mjcf} not found. Run `python tools/fetch_assets.py` first.")
    spec = mujoco.MjSpec.from_file(str(mjcf))
    spec.option.timestep = cfg["control"]["sim_dt"]

    # -- look -----------------------------------------------------------------
    tex = spec.add_texture()
    tex.name = "floor_tex"
    tex.type = mujoco.mjtTexture.mjTEXTURE_2D
    tex.builtin = mujoco.mjtBuiltin.mjBUILTIN_CHECKER
    tex.rgb1 = [0.93, 0.93, 0.95]
    tex.rgb2 = [0.82, 0.84, 0.88]
    tex.width = tex.height = 512
    floor = _mat(spec, "floor_mat", [1, 1, 1, 1], texrepeat=[2, 2], texuniform=True)
    floor.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = "floor_tex"
    ground = spec.geom("ground")
    ground.material = "floor_mat"

    _mat(spec, "wood", [0.55, 0.38, 0.24, 1])
    _mat(spec, "wood_dark", [0.36, 0.24, 0.15, 1])
    _mat(spec, "gift_red", [0.78, 0.10, 0.12, 1])
    _mat(spec, "gift_green", [0.08, 0.45, 0.22, 1])
    _mat(spec, "ribbon_gold", [0.95, 0.78, 0.20, 1], specular=0.6)
    _mat(spec, "pine", [0.05, 0.36, 0.16, 1])
    _mat(spec, "trunk", [0.40, 0.25, 0.12, 1])
    _mat(spec, "star", [1.0, 0.85, 0.15, 1], emission=0.6)
    _mat(spec, "pad", [0.15, 0.15, 0.18, 1])

    world = spec.worldbody
    light = world.add_light()
    light.pos = [0.0, -1.5, 3.0]
    light.dir = [0.0, 0.4, -1.0]
    light.diffuse = [0.5, 0.5, 0.5]
    light.castshadow = True

    # -- tables (static, collide with robot and gifts) -------------------------
    L, D, H = layout.table_length, layout.table_depth, layout.table_height
    t, leg = layout.table_top, layout.table_leg
    for tname, centre in (("left_table", layout.left_table_center), ("right_table", layout.right_table_center)):
        b = world.add_body()
        b.name = tname
        b.pos = [centre[0], centre[1], 0.0]
        top = b.add_geom()
        top.name = f"{tname}_top"
        top.type = mujoco.mjtGeom.mjGEOM_BOX
        top.size = [L / 2, D / 2, t / 2]
        top.pos = [0, 0, H - t / 2]
        top.material = "wood"
        top.contype = 1
        top.conaffinity = 1
        top.condim = 3
        top.friction = [0.7, 0.01, 0.001]
        for sx in (-1, 1):
            for sy in (-1, 1):
                g = b.add_geom()
                g.type = mujoco.mjtGeom.mjGEOM_BOX
                g.size = [leg / 2, leg / 2, (H - t) / 2]
                g.pos = [sx * (L / 2 - leg), sy * (D / 2 - leg), (H - t) / 2]
                g.material = "wood_dark"
                g.contype = 1
                g.conaffinity = 1

    # -- gifts (free bodies, squeezed between the forearms) -------------------
    gift_mats = ("gift_red", "gift_green")
    for i, gift in enumerate(layout.gifts):
        b = world.add_body()
        b.name = gift.name
        b.pos = gift.start.tolist()
        fj = b.add_freejoint()
        fj.name = f"{gift.name}_free"
        h = gift.size / 2
        box = b.add_geom()
        box.name = f"{gift.name}_box"
        box.type = mujoco.mjtGeom.mjGEOM_BOX
        box.size = [h, h, h]
        box.mass = gift.mass
        box.material = gift_mats[i % 2]
        box.contype = 1
        box.conaffinity = 1
        box.condim = 4
        box.friction = [cfg["scene"]["gift_friction"], 0.02, 0.001]
        # ribbons: visual only
        for size in ([h + 0.002, 0.012, h + 0.002], [0.012, h + 0.002, h + 0.002]):
            r = b.add_geom()
            r.type = mujoco.mjtGeom.mjGEOM_BOX
            r.size = size
            r.material = "ribbon_gold"
            r.contype = r.conaffinity = 0
            r.mass = 0
            r.group = 2
        bow = b.add_geom()
        bow.type = mujoco.mjtGeom.mjGEOM_ELLIPSOID
        bow.size = [0.035, 0.035, 0.018]
        bow.pos = [0, 0, h + 0.012]
        bow.material = "ribbon_gold"
        bow.contype = bow.conaffinity = 0
        bow.mass = 0
        bow.group = 2
        # goal marker: a flat translucent square on the destination table
        mk = world.add_geom()
        mk.name = f"{gift.name}_goal_marker"
        mk.type = mujoco.mjtGeom.mjGEOM_BOX
        mk.size = [h, h, 0.0008]
        mk.pos = [gift.goal[0], gift.goal[1], H + 0.0008]
        mk.rgba = [0.95, 0.78, 0.2, 0.25]
        mk.contype = mk.conaffinity = 0
        mk.group = 2

    # -- tree (static, between the mirrored small-gift spots) ------------------
    tb = world.add_body()
    tb.name = "tree"
    tb.pos = layout.tree_pos.tolist()
    th, tr = layout.tree_height, layout.tree_radius
    trunk = tb.add_geom()
    trunk.type = mujoco.mjtGeom.mjGEOM_CYLINDER
    trunk.size = [0.03, 0.05, 0]
    trunk.pos = [0, 0, 0.05]
    trunk.material = "trunk"
    trunk.contype = trunk.conaffinity = 1
    for k, (z0, frac) in enumerate(((0.10, 1.0), (0.32, 0.78), (0.52, 0.55))):
        # three stacked cones approximated by ellipsoids for a soft silhouette
        cone = tb.add_geom()
        cone.type = mujoco.mjtGeom.mjGEOM_ELLIPSOID
        cone.size = [tr * frac, tr * frac, th * 0.22]
        cone.pos = [0, 0, th * z0 + th * 0.18]
        cone.material = "pine"
        cone.contype = cone.conaffinity = 1 if k == 0 else 0
    star = tb.add_geom()
    star.type = mujoco.mjtGeom.mjGEOM_SPHERE
    star.size = [0.025, 0, 0]
    star.pos = [0, 0, th * 0.98]
    star.material = "star"
    star.contype = star.conaffinity = 0
    rng = np.random.default_rng(7)
    for _ in range(14):
        z = rng.uniform(0.2, 0.85) * th
        rad = tr * (1.05 - 0.9 * z / th) * 0.92
        a = rng.uniform(0, 2 * np.pi)
        orn = tb.add_geom()
        orn.type = mujoco.mjtGeom.mjGEOM_SPHERE
        orn.size = [0.012, 0, 0]
        orn.pos = [rad * np.cos(a), rad * np.sin(a), z]
        orn.rgba = [[0.9, 0.1, 0.1, 1], [0.95, 0.8, 0.2, 1], [0.2, 0.4, 0.95, 1]][rng.integers(3)]
        orn.contype = orn.conaffinity = 0

    # -- forearm pads and wrist sites ---------------------------------------
    pad = cfg["robot"]["forearm_pad"]
    for side in SIDES:
        fb = spec.body(f"{side}_elbow_yaw_link")
        for g in fb.geoms:  # the forearm shell mesh no longer collides; the pad does
            g.contype = 0
            g.conaffinity = 0
        p = fb.add_geom()
        p.name = f"{side}_forearm_pad"
        p.type = mujoco.mjtGeom.mjGEOM_CAPSULE
        p.fromto = [pad["from_x"], 0, 0, pad["to_x"], 0, 0]
        p.size = [pad["radius"], 0, 0]
        p.material = "pad"
        p.contype = 1
        p.conaffinity = 0
        p.condim = 4
        p.friction = [pad["friction"], 0.02, 0.001]
        p.mass = 0
        s = fb.add_site()
        s.name = f"{side}_wrist"
        s.pos = [cfg["robot"]["wrist_site_x"], 0, 0]
        s.size = [0.012, 0, 0]
        s.rgba = [1, 0.85, 0.1, 1]
        e = fb.add_site()
        e.name = f"{side}_elbow"
        e.pos = [0, 0, 0]
        e.size = [0.01, 0, 0]
        e.rgba = [0.2, 0.8, 1, 0.6]

    # -- assisted-mode support -------------------------------------------------
    mb = world.add_body()
    mb.name = ASSIST_MOCAP
    mb.mocap = True
    mb.pos = [0, 0, cfg["robot"]["spawn_height_m"]]
    eq = spec.add_equality()
    eq.name = ASSIST_WELD
    eq.type = mujoco.mjtEq.mjEQ_WELD
    eq.objtype = mujoco.mjtObj.mjOBJ_BODY
    eq.name1 = ASSIST_MOCAP
    eq.name2 = "base_link"
    eq.solref = cfg["assist"]["weld_solref"]
    data = np.zeros(len(eq.data))  # mjNEQDATA; weld layout: anchor, relpos, relquat, torquescale
    data[6] = 1.0  # relpose quat w: frames coincide
    data[10] = 1.0  # torquescale
    eq.data = data
    return spec


def build_model(cfg: dict, layout: Layout) -> tuple[mujoco.MjModel, mujoco.MjSpec]:
    spec = build_spec(cfg, layout)
    return spec.compile(), spec
