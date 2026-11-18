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
| 7 | ONNX plumbing | Stand-in export (zero actions, 80-dim obs with phase_clock) | `python run_trial.py --policy exports/_test_clock --assist full` | Loaded through LearningRLsim. Observation 80, action 23. Mission completed. Unassisted, it stood for 8 s without falling. | The adapter is ready for a real export. |

## Open items

- **Train a walking policy.** Use `LearningRL-RPO-FlatWalk-v0` (it needs reverse and turn-in-place), then run unassisted.
- **Loaded walking is untested.** The arms are overridden while walking, and the walk policy was trained with nominal arms.
- **Hardware data needed:**
  - pelvis pose estimate (odometry or external tracking)
  - real box masses and friction
  - forearm pad material
  - the robot's own damping/sit command, for "deactivate"
