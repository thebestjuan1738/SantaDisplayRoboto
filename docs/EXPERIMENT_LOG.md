# Experiment log

Model used for implementation: Claude Opus 5.5 (Claude Code). Every result below was produced by running the command shown. Mode is ASSISTED unless stated otherwise.

## 2026-11-18

| # | Goal | Change | Command | Observation | Decision |
|---|---|---|---|---|---|
| 0 | First full rollout | Baseline controller | `python run_trial.py` | The sequence completed in 100 s of sim time. Neither gift moved; the large gift was pushed back on the table. | Inspect the arms at grasp time. |
| 1 | Find why the grasp fails | Traced the IK targets | debug trace | The "ready arms" pose was solved from the robot's pose 0.40 m from the table. That put the gift out of reach, and the IK fell into a twisted solution (arm yaw 2.6 rad) that later solves started from. | Solve the ready pose relative to the planned grasp stance. Try 3 IK starting configurations and keep the best. |
| 2 | Re-run | As in 1 | `python run_trial.py` | Squeeze force went from 0 to 7.6 N. Contacts were only at the gift's front edge (contact y = gift front face), and the gift pivoted out as it left the table. | Add elbow-wider-than-wrist toe-in (2 cm) and a 2.5 cm squeeze inset. Command a 7 cm lift so ~4 cm remains after PD sag. |
| 3 | Re-run | As in 2 | `python run_trial.py` | The small gift was placed (2.4 cm error). The large gift sank through the grip at about 1 cm/s while carried (0.963 → 0.864 m) and hit the right table's edge. | Hypothesis: friction creep in MuJoCo's soft contacts. |
| 4 | Test the creep hypothesis | `physics.cone` = elliptic, `impratio` = 10 | sweep of 3 settings | pyramidal/1: large gift fails. elliptic/10: both placed (0.2 / 0.3 cm). elliptic/30: also both placed, but 20 % slower. | Adopt elliptic/10. Flag it as a sim choice that applies to foot contacts as well. |
| 5 | Stage 2 evaluation | none | `python run_eval.py` | 10/10. Nominal error 0.23 / 0.34 cm. Variation (±2 cm, controller not told) 0.19–0.99 cm. No saturation. | — |
| 6 | Controlled before/after | One value per experiment | `python tools/diagnose.py` | E1: carry sink 10.6 → 1.2 cm, large gift error 20.7 → 0.3 cm. E2 (toe-in 0 vs 2 cm): without toe-in the small gift is never lifted and stays on the start table (51.2 cm from goal); with it, 0.2 cm. | Recorded in `runs/diagnosis/`. |
| 7 | ONNX plumbing | Stand-in export (zero actions, walk schema) | `python run_trial.py --policy exports/_test_walk --assist full` | Loaded through LearningRLsim. Mission completed; unassisted, it stood without falling. | The adapter is ready for a real export. |

## 2026-11-19

| # | Goal | Change | Command | Observation | Decision |
|---|---|---|---|---|---|
| 8 | Train arms and legs in one policy | New task `LearningRL-RPO-LocoManipulation-v0` on branch `student/cody-rpo-locomanip` of the TA's repo: his G1 locomanipulation task with the Origin swapped in; wrist points tracked; Origin-sized target ranges; 0–0.3 kg forearm load | `ruff check . && ruff format --check . && pytest -m static LearningRLlab/tests` | Lint and the TA's static tests pass (9/9). Isaac Lab cannot run on our laptops, so the env has not been built or trained here. | Replaces the earlier plan to train a walk-only policy. |
| 9 | Policy drives the arms | The adapter feeds `hand_track` (FK wrist points of the controller's arm pose); arms are no longer overridden when the export has it | `pytest -q tests` | 5/5 pass. Over a full mission the wrist targets stay inside the training ranges. | Ready for the real export. |

## 2026-11-23 -- first trained policy (`exports/locomanip_walkv1_7999`)

Mark's `LearningRL-RPO-LocoManipulation-v0` run on the Walk-v1 base (commit `b20dbac`), model_7999. Training-side metrics (his README): 0.22 m/s linear and 0.60 rad/s yaw velocity error, 7 cm hand error, 0.2 % falls.

| # | Goal | Change | Command | Observation | Decision |
|---|---|---|---|---|---|
| 10 | Plumbing | none | `run_trial.py --policy exports/locomanip_walkv1_7999 --assist full` | Loads (86 obs / 23 actions). With the pelvis held, the policy's own arms carried both gifts across: small 2.0 cm (tipped), large 6.7 cm. | Interface works end to end. |
| 11 | First unassisted run | none | `run_trial.py --policy exports/locomanip_walkv1_7999` | Never fell in 180 s, but froze 10 cm short of the first gift: commanded 0.06-0.12 m/s, achieved ~0. | Measure the velocity response. |
| 12 | Velocity response | new `tools/velocity_sweep.py` (open floor, 6 s holds) | `python tools/velocity_sweep.py exports/locomanip_walkv1_7999` | Dead zone: \|vx\| <= 0.12 m/s -> stands still (its gait rewards treat \|cmd\| <= 0.1 as "stand"). Forward undershoots by ~0.13 m/s (0.25 -> 0.14, 0.40 -> 0.27, 0.60 -> 0.44); reverse -0.30 -> -0.29; yaw ~73 % (0.45 -> 0.33). No falls in 24 tests; raised arms change little. | Calibrate commands. |
| 13 | Calibrate commands | `navigation.policy_command_map`: [achieved, command] tables from #12; any nonzero wish lifted out of the dead zone | `run_trial.py --policy ...` | Full route walked unassisted, no fall, deactivated at 93 s. No grasp: while the arms reached, the body drifted 26 cm backwards (pelvis-frame wrist targets went with it), grip 0 N. | Hold position while the arms work. |
| 14 | Hold position | `navigation.station_keeping` (walk back to the arrival spot beyond 4 cm, forward/reverse only); wrist paths anchored to the room while standing | `run_trial.py --policy ...` | **Small gift picked, carried and placed unassisted** (17-20 N, ~10 cm lift), final error 8.7 cm: pushed 6.5 cm while releasing as station-keeping stepped in. Large gift: robot slid 10 cm sideways while squeezing (right-wrist target pushed to y ~ 0, outside its trained range); gripped at 27-37 N but sank 9 cm in the carry (policy stands ~7 cm lower than the assisted model) and hit the far table edge, ending on the floor. | Next: lateral drift during squeeze, more lift for the lower stance, no station-keeping steps during release. |

| 15 | Why it crouches | stance measured standing still (zero command) | inline script | Pelvis 0.71 m (0.67-0.68 m while reaching/carrying) vs 0.75 default. Knee target 0.67 rad vs default 0.30, actual 0.76 (0.09 rad sag vs Isaac's delayed-PD model). Walk-v1 has no height reward, rewards a 0.15 m swing, and its leg-deviation penalty covers only thigh roll/yaw. | Training fix (pelvis height 0.73 m, 0.09 m swing, light hip-pitch/knee/ankle penalty) written on `student/cody-rpo-locomanip`; needs Mark's retrain. Controller: +5 cm lift with a policy. |
| 16 | New layout + extra lift | gift gap 6 -> 9 in (team choice); tree centred between the placed gifts, 17 in deep; `manipulation.policy_extra_lift_m` 0.05 | `run_trial.py --policy exports/locomanip_walkv1_7999 --follow --save-video ...` | Assisted: both placed (0.3 / 0.3 cm). Policy unassisted: **small gift placed, 2.0 cm** (was 8.7). Large gift never moved: stepping in it drifted 8-13 cm sideways, could not meet the 3 cm arrival tolerance without side-stepping (71 s stall), and the open right forearm pushed the gift ~5 cm, so the grasp closed on nothing. | Next: arrive on forward distance only when stepping in, and shift the open wrists sideways with the body's drift so they stay around the gift. |

## Open items

- **`LearningRL-RPO-LocoManipulation-v0` is training** on the TA's GPU (branch `student/cody-rpo-locomanip`); export expected by end of week. Over break: `--assist full`, then unassisted, then `run_eval.py`.
- **Squeeze strength with a real policy is unknown.** Training rewards wrist position only; tune `squeeze_inset_m` against the measured grip force.
- **Hardware data needed:**
  - pelvis pose estimate (odometry or external tracking)
  - real box masses and friction
  - forearm pad material
  - the robot's own damping/sit command, for "deactivate"
