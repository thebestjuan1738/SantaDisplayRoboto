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

## Open items

- **Train `LearningRL-RPO-LocoManipulation-v0`** (TA), then bring it up: `--assist full`, then unassisted, then `run_eval.py`.
- **Squeeze strength with a real policy is unknown.** Training rewards wrist position only; tune `squeeze_inset_m` against the measured grip force.
- **Hardware data needed:**
  - pelvis pose estimate (odometry or external tracking)
  - real box masses and friction
  - forearm pad material
  - the robot's own damping/sit command, for "deactivate"
