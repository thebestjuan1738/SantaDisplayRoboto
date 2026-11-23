# SantaBot — Roboto Origin locomanipulation display

The Roboto Origin (RPO, 23 DoF) runs a holiday display:

1. It starts at home and walks to the left table.
2. It squeezes a gift between its forearms, backs away, turns, and carries the gift to the mirror-image spot on the right table.
3. It returns for the second gift and repeats the transfer.
4. It walks home and deactivates.

A tree stands between the two mirrored spots. The robot walks forward, reverses and turns in place, and **never side-steps**: the lateral velocity command is zero at every step.

> **Status (2026-11-19): the whole-body policy (`LearningRL-RPO-LocoManipulation-v0`) is training on the TA's GPU; the export is expected by the end of the week and will be tuned over break.** Until then, every
> rollout so far runs in **ASSISTED** mode:
> - A soft weld carries the pelvis along the path the controller commands, and the legs follow a scripted stepping pattern.
> - The arms, the squeeze and the gifts are real MuJoCo contact physics.
> - The walking is not dynamic.
>
> Every video, plot and result file is labelled with its mode.

```
 high-level controller (this repo)                 whole-body policy (TA's LearningRL pipeline)
 ─────────────────────────────────                 ────────────────────────────────────────────
 pose estimate ─► MissionController ── vx, wz ─────► base_velocity ─┐
                  │  GoTo / ArmMove / Hold                          ├► policy.onnx ─► 23 joint targets
                  └─ arm IK → wrist points ── hand_track ───────────┘   (legs AND arms)      │
                                                                                             ▼
                                                                          PD → MuJoCo (or the robot)
```

The policy is trained by `LearningRL-RPO-LocoManipulation-v0` on our branch of the TA's repo: one
network walks to the velocity command and puts its wrists where the hand command asks.

## Quick start

```bash
py -3.12 -m venv .venv && .venv\Scripts\activate        # Python 3.12
pip install -r requirements.txt
pip install --no-deps "LearningRLsim @ git+https://github.com/mark-helwig/LearningRL#subdirectory=LearningRLsim"
python tools/fetch_assets.py                             # RPO model, pinned to the TA's revision

python run_trial.py --viewer                             # watch one trial live
python run_trial.py --video --gif                        # record runs/<time>/trial.mp4 + .gif
python run_eval.py                                       # 5 nominal + 5 variation trials, table + plots
python tools/diagnose.py                                 # reproduce the two controlled iterations
pytest -q tests
```

`LearningRLsim` is installed with `--no-deps` for two reasons:
- It pins `mujoco<4`, and Windows Smart App Control blocks mujoco 3.x's DLL on our laptops.
- Only its pure-Python config, observation, action and ONNX modules are used here.

## Dropping in the trained policy

This is the one step needed once the TA has trained a policy.

1. Copy the exported **run directory** into `exports/<name>/`. It holds the three files LearningRLlab's play/export step writes: `config.yaml`, `policy.onnx` and `policy.onnx.data`. Keep the `.onnx` and `.data` files together.
2. Bring it up in stages:
   ```bash
   python run_trial.py --policy exports/<name> --assist full   # policy legs, pelvis still held: check the plumbing
   python run_trial.py --policy exports/<name> --viewer        # unassisted: the policy must balance and walk
   python run_eval.py  --policy exports/<name>                 # Stage-2 style evaluation
   ```

Nothing in the controller changes.

What the adapter (`santabot/locomotion.py: OnnxPolicy`) does:
- **Reuses the TA's code.** It runs the TA's `LearningRLsim` on the export's `config.yaml`, using its observation assembly, action terms and ONNX session. The policy sees exactly what `learningrl-sim` would feed it.
- **Follows the export's settings.** Joint order, default pose, PD gains, armature, friction, `sim_dt` and decimation all come from the export.
- **Feeds the velocity command.** The `base_velocity` command term is `(vx, 0, wz)` from the mission controller.
- **Feeds the hand command.** `hand_track` is `[1, 1, left_wrist_xyz, right_wrist_xyz]` in the pelvis frame: wrist points 0.135 m along each forearm, the point the task trains on. The controller plans them straight from the gift geometry (open, squeeze, lift, lower) as min-jerk paths, with **no inverse kinematics**: the policy maps wrist targets to joints itself. Outside an arm sequence the row is all zeros, the training side's "no hand target" command, and the policy holds its own arms. IK is only used in assisted mode and for a walk-only policy, where the controller writes the arm joints itself.
- **Lets the policy drive the arms.** With a `hand_track` export the controller no longer writes arm joints. An export without one (a walk-only policy) falls back to overriding the 10 arm joints with the IK solution; `control.arm_control: override` forces that fallback for comparison.

Over a full mission the wrist targets stay inside the ranges the task trains on (x 0.04–0.35 m, |y| 0.10–0.25 m, z −0.11–0.23 m against 0–0.40, 0–0.35 and −0.15–0.35).

To check the plumbing without a trained policy, `python tools/make_test_export.py exports/_test_locomanip --hands` writes a stand-in export in the locomanipulation format (86 observations, 23 actions). Its policy outputs zeros, so the robot just holds its pose.

### Which task the TA should train

**`LearningRL-RPO-LocoManipulation-v0`**, on branch `student/cody-rpo-locomanip` of the TA's
repo (github.com/mark-helwig/LearningRL). It is the TA's `LearningRL-G1-LocoManipulation-v0`
with the Origin swapped in exactly as his `LearningRL-RPO-Walk-v0` does it:

- **Same training recipe as the G1 task.** Rewards and weights, the hand-tracking weight ramp (0 → 2 over 5000 PPO iterations), terminations, flat ground, physics and PPO are all unchanged.
- **Tracked points are the wrists.** The Origin has no hand link, so `RPOHandPosCommand` tracks a point 0.135 m along each forearm (`<side>_elbow_yaw_link`). The command format is still the G1's 8 values, under the same `HandPosCommandCfg` type, so LearningRLsim replays it unchanged.
- **Target ranges sized to the Origin's arm.** x 0–0.40 m, each side 0–0.35 m, z −0.15–0.35 m.
- **Forearm load.** 0–0.3 kg is added to each forearm at startup, so the policy learns to balance with a light gift held in front of it.

Velocity commands train over ±1 m/s and ±1 rad/s, which covers everything the controller sends:

| Command | Range |
|---|---|
| Forward speed | up to 0.25 m/s |
| Reverse speed | up to 0.12 m/s |
| Turn in place / yaw rate | up to 0.45 rad/s |
| Lateral speed | always 0 |

Train and export it the usual way, from `/workspace/isaaclab` in the TA's container:

```bash
./isaaclab.sh -p source/LearningRLlab/scripts/train.py --task LearningRL-RPO-LocoManipulation-v0 --viz kit --enable_cameras physics=newton_mjwarp
./isaaclab.sh -p source/LearningRLlab/scripts/play.py  --task LearningRL-RPO-LocoManipulation-v0-PLAY --viz kit --enable_cameras physics=newton_mjwarp --video
```

**Known limit:** the policy is rewarded for wrist *position*, and nothing in training pushes against an object. How hard it squeezes a real gift therefore depends on how far inside the gift faces the targets sit (`manipulation.squeeze_inset_m`). That is the first thing to tune once the export arrives.

## Scene, and the interpretations made

Everything is in `config/santabot.yaml`, in inches where the brief gave inches.

| Brief | Model |
|---|---|
| Two 60" × 24" tables, touching | Placed end to end. Front edges on y = 0, seam at x = 0. |
| Table height at the Origin's waist | 29.5" (0.749 m). The pelvis stands at 0.75 m, and its hull spans 0.66–0.82 m. |
| 8", 8", 8" and 12", 12", 12" empty gifts | Cubes of 0.20 kg and 0.45 kg. **Measure the real boxes.** |
| Small gift 6" from the closest side | The small gift's seam-side face is 6" from the seam, the table side nearest home. |
| Large gift 6" to the left of the small one | 6" gap between their faces, further from the seam. |
| Gift depth on the table | Not given. Front faces sit **2" from the front edge** (see the reach check). |
| Mirrored spots | Each gift's spot reflected across the seam. |
| Home 1 ft from the touching edges | Pelvis 12" in front of the seam, facing the tables. |
| Tree between the mirrored spots | On the seam, 17" back from the front edge. |
| No end effectors: squeeze between the wrists | A capsule pad on each forearm. The wrists are commanded 2.5 cm *inside* the gift faces, and the elbows are 2 cm wider than the wrists (toe-in). The PD error is the squeeze. |

**Reach check.**
- The pelvis can't get closer than about 5 cm to the table edge, because the hull sits at table height.
- That leaves the gifts' mid-depth about 0.43 m from the shoulder, roughly the full arm length.
- With a 6" setback, the 8" gift's centre is out of reach.
- Change `gift_front_setback_in` if the physical layout differs. `tests/test_santabot.py` checks that the IK still reaches.

## The controller

`santabot/mission.py` runs a fixed sequence of primitives.

**For each gift:**
1. `approach`: stop 0.40 m from the table.
2. `ready arms`: raise the forearms, opened wide.
3. `step in`: walk forward to 0.11 m from the edge.
4. `reach`, `squeeze`, `settle`, `lift`.
5. `back off`: reverse 0.30 m.
6. `carry`: turn and walk to the mirrored spot.
7. `step in place`, `lower`, `release`, `retract`.
8. `back off`, then return the arms home.

**Then:** `return home`, `settle`, `deactivated`.

How the primitives work:
- **`GoTo`** is unicycle navigation. If the heading error is above 0.35 rad it turns in place; otherwise it walks forward or reverses with heading feedback, then turns to the final yaw. It reverses automatically when the goal is behind it and within 0.6 m. Speeds and accelerations are rate-limited.
- **`ArmMove`** is a min-jerk move between pelvis-frame IK solutions (`santabot/arm_ik.py`). The IK fits each 5-DoF arm to two points, wrist and elbow, so the forearm lies along the gift's side. It uses several starting configurations so it can't get stuck in a bad local solution.
- **Inputs are only the pelvis pose estimate and the known layout.** There is no object sensing, because the hardware won't have any.

**Tuning:** every number is in `config/santabot.yaml`:
- speeds and tolerances
- standoffs
- squeeze inset and toe-in
- lift compensation for PD sag
- move times
- assist gait

Use `python run_trial.py --config my_copy.yaml` to try a variant.

## Current results (assisted, not trained)

`python run_eval.py` gives **10/10 successful trials**:
- 5 nominal trials, which are deterministic.
- 5 variation trials, where each gift starts up to ±2 cm off its nominal spot and the controller isn't told.
- Final placement error is 0.2–1.0 cm. No torque saturation.

`tools/diagnose.py` reproduces the two diagnosed failures, written up in `docs/EXPERIMENT_LOG.md`:

| Experiment | Before | After |
|---|---|---|
| **E1 Friction creep** | Default pyramidal friction (impratio 1). The large gift sank 10.6 cm while being carried and missed its goal by 20.7 cm. | Elliptic cone, impratio 10: 1.2 cm sink, 0.3 cm error. |
| **E2 Toe-in** | Parallel forearms (no toe-in). Contact happened only at the gift's front edge, so the small gift was never lifted and stayed on the start table (51 cm error). | 2 cm toe-in: 0.2 cm error. |

## Repository

```
config/santabot.yaml     every tunable number
santabot/                layout, scene, robot data, arm IK, mission controller,
                         locomotion backends (ONNX / assisted), trial loop, render, plots
run_trial.py run_eval.py one trial / Stage-2 evaluation
tools/                   fetch_assets, make_test_export (stand-in ONNX), diagnose
slides/                  Stage 2 deck (built from the course template)
docs/EXPERIMENT_LOG.md   dated record of every change and its measured effect
videos/                  committed video log: YYYY-MM-DD_HHMM_<description>.mp4 + index (see CLAUDE.md)
CLAUDE.md                working rules for the team and their Claude sessions
tests/                   pytest
```

The robot model is Roboparty/rpo_description @ 37aac9c (CERN-OHL-W-2.0), fetched into `vendor/`. The joint gains and default pose are from RoboParty's RPO_CFG, as transcribed in the TA's `robot_description`. Observation and action handling come from the TA's LearningRLsim.
