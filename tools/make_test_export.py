"""Write a STAND-IN policy export in the exact layout the TA's pipeline produces.

  python tools/make_test_export.py exports/_test_zero            # 78-dim walk schema
  python tools/make_test_export.py exports/_test_clock --clock   # + phase_clock (80-dim)

The ONNX graph is an untrained MLP whose output is all zeros, so the robot
just holds its default pose. It exists only to prove the plumbing: that a
real export dropped into exports/ is loaded, its observation vector is
assembled to the right size, and its actions reach the joints. It is NOT a
walking policy -- run it with --assist full.

The schema mirrors LearningRL-RPO-FlatWalk-v0 / ForwardWalk-v0 (78 obs, 23
actions) as recorded in the student branch's MULTI_POLICY_PLAN.md; a real
export's config.yaml replaces all of this.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import importlib.util

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from santabot.robot import JOINT_NAMES, default_gains, default_pose  # noqa: E402


def build_config(clock: bool) -> dict:
    n = len(JOINT_NAMES)
    kp, kd, eff = default_gains()
    terms = []
    start = 0

    def add(name, func, dim, scale=1.0, params=None):
        nonlocal start
        t = {"name": name, "func": func, "dim": dim, "slice": [start, start + dim], "scale": scale, "clip": None}
        if params:
            t["params"] = params
        terms.append(t)
        start += dim

    add("base_ang_vel", "base_ang_vel", 3, 0.2)
    add("projected_gravity", "projected_gravity", 3)
    add("velocity_commands", "generated_commands", 3, params={"command_name": "base_velocity"})
    add("joint_pos_rel", "joint_pos_rel", n)
    add("joint_vel_rel", "joint_vel_rel", n, 0.05)
    add("last_action", "last_action", n)
    if clock:
        add("gait_clock", "phase_clock", 2)
    return {
        "policy_frequency_hz": 50.0,
        "sim_frequency_hz": 200.0,
        "sim_dt": 0.005,
        "decimation": 4,
        "robot": "roboparty_rpo",
        "task": "SantaBot-StandIn-ZeroPolicy-PLAY",
        "run": {"name": "stand-in", "checkpoint": None, "note": "untrained zero-output stand-in"},
        "init_state": {"pos": [0.0, 0.0, 0.75]},
        "observations": {"total_dim": start, "terms": terms},
        "commands": [
            {
                "name": "base_velocity",
                "type": "UniformVelocityCommandCfg",
                "obs_slice": [6, 9],
                "ranges": {"lin_vel_x": [-0.35, 0.35], "lin_vel_y": [-0.35, 0.35], "ang_vel_z": [-0.5, 0.5], "heading": None},
                "heading_command": False,
                "rel_standing_envs": 0.25,
                "resampling_time_range": [6.0, 10.0],
            }
        ],
        "actions": {
            "total_dim": n,
            "terms": [
                {
                    "name": "joint_pos",
                    "type": "JointPositionAction",
                    "dim": n,
                    "slice": [0, n],
                    "joint_names": list(JOINT_NAMES),
                    "scale": 0.25,
                    "offset": default_pose().tolist(),
                    "clip": [[-10.0, 10.0]] * n,
                }
            ],
        },
        "default_joint_pos": {"joint_order": list(JOINT_NAMES), "values": default_pose().tolist()},
        "actuators": {
            "joint_order": list(JOINT_NAMES),
            "stiffness": kp.tolist(),
            "damping": kd.tolist(),
            "armature": [0.01] * n,
            "friction": [0.0] * n,
            "effort_limit": eff.tolist(),
            "velocity_limit": [25.0 if e > 100 else 8.0 for e in eff],
        },
    }


def _onnx_proto():
    """onnx's generated protobuf module, loaded WITHOUT `import onnx`.

    The onnx wheel's C extension can be blocked by Windows Smart App Control;
    the schema module is pure Python (needs only `protobuf`). Falls back to a
    normal import where that works.
    """
    try:
        from onnx import onnx_ml_pb2

        return onnx_ml_pb2
    except Exception:
        pass
    for base in map(Path, sys.path):
        f = base / "onnx" / "onnx_ml_pb2.py"
        if f.is_file():
            spec = importlib.util.spec_from_file_location("santabot_onnx_ml_pb2", f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("pip install onnx (only its pure-Python onnx_ml_pb2 schema is used)")


def build_onnx(obs_dim: int, act_dim: int, path: Path) -> None:
    """A 2-layer MLP `obs -> actions` with a zero output head, weights stored as
    ONNX external data in `<path>.data`, the layout the TA's exporter writes."""
    pb = _onnx_proto()
    rng = np.random.default_rng(0)
    weights = {
        "w1": rng.normal(0, 0.05, (obs_dim, 64)).astype(np.float32),
        "b1": np.zeros(64, np.float32),
        "w2": np.zeros((64, act_dim), np.float32),  # zero head: output is exactly 0
        "b2": np.zeros(act_dim, np.float32),
    }
    model = pb.ModelProto(ir_version=8, producer_name="santabot-standin")
    model.opset_import.add(domain="", version=17)
    g = model.graph
    g.name = "standin_actor"
    for op, ins, out in (
        ("MatMul", ["obs", "w1"], "h"),
        ("Add", ["h", "b1"], "h1"),
        ("Elu", ["h1"], "h2"),
        ("MatMul", ["h2", "w2"], "o"),
        ("Add", ["o", "b2"], "actions"),
    ):
        g.node.add(op_type=op, input=ins, output=[out], name=out + "_" + op)
    blob = bytearray()
    for name, arr in weights.items():
        t = g.initializer.add(name=name, data_type=pb.TensorProto.FLOAT, dims=list(arr.shape))
        t.data_location = pb.TensorProto.EXTERNAL
        offset = len(blob)
        blob += arr.tobytes()
        for k, v in (("location", path.name + ".data"), ("offset", str(offset)), ("length", str(arr.nbytes))):
            t.external_data.add(key=k, value=v)
    for vi, name, dim in ((g.input.add(), "obs", obs_dim), (g.output.add(), "actions", act_dim)):
        vi.name = name
        tt = vi.type.tensor_type
        tt.elem_type = pb.TensorProto.FLOAT
        tt.shape.dim.add(dim_param="batch")
        tt.shape.dim.add(dim_value=dim)
    path.write_bytes(model.SerializeToString())
    (path.parent / (path.name + ".data")).write_bytes(bytes(blob))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--clock", action="store_true", help="append the alternating-gait phase_clock observation")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = build_config(a.clock)
    with open(out / "config.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False)
    build_onnx(cfg["observations"]["total_dim"], cfg["actions"]["total_dim"], out / "policy.onnx")
    print(f"wrote {out} (obs {cfg['observations']['total_dim']}, actions {cfg['actions']['total_dim']})")


if __name__ == "__main__":
    main()
