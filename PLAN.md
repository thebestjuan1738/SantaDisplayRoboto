# Santa Display — Roboto Origin Loco-Manipulation Demo

**Course:** Human-Centered Robotics — Final Motion Display
**Platform:** RoboParty *Roboto Origin* (RPO), simulation only
**Deliverable:** A rendered video of the humanoid relocating two boxes between two tables ("moving presents under the tree")
**Plan date:** 2026-11-05

---

## 1. The Show (what the video must contain)

One continuous take. The robot executes the same cycle twice, once per box.

| # | Beat | Base motion | Arm motion | Nominal duration |
|---|------|-------------|------------|------------------|
| 1 | Establish | idle stance at start mark | arms at home | 3 s |
| 2 | Approach A | walk forward to Table A standoff | arms rise to pre-clamp | 8 s |
| 3 | Align | small lateral/yaw correction | pre-clamp pose held | 2 s |
| 4 | Clamp | **stand still** | arms close on box, squeeze | 3 s |
| 5 | Lift | stand still | arms raise box clear of table | 2 s |
| 6 | Retreat | walk **backward** to clear the table | hold box | 4 s |
| 7 | Turn | turn in place toward Table B | hold box | 4 s |
| 8 | Transit | walk forward a set distance | hold box | 8 s |
| 9 | Align B | lateral/yaw correction | hold box | 2 s |
| 10 | Place | stand still | lower box, open arms, release | 4 s |
| 11 | Retreat B | walk backward, turn back toward A | arms to home | 6 s |

Cycle ≈ 46 s. Two cycles + establishing/closing shots ≈ **100 s of motion**. Box 1 is the large box, box 2 the small one — do the hard one first, while the clamp is the fresh problem rather than the tired one.

### Non-negotiable acceptance criteria

- [ ] Both boxes end on Table B, upright, within **±8 cm** of their marks
- [ ] Zero falls and zero self-collisions across the take
- [ ] End-to-end success rate **≥ 8/10** runs on the final seed sweep
- [ ] Video ≥ 1080p, ≥ 30 fps, with at least two camera angles
- [ ] Any physics assist (see §4.3) is disclosed in the report and shown in a side-by-side

---

## 2. Hard Platform Constraints (read this before designing anything)

These come from the RoboParty repos and spec pages and **must be confirmed against the actual model files in Week 0** — the published sources disagree with each other.

| Property | Value | Consequence for this project |
|---|---|---|
| **DOF per arm** | **5** (no wrist roll on the base model) | **You cannot command a full 6-DOF end-effector pose.** See §4.1 |
| **Hands** | **Dummy hands, 0 finger DOF** on the base model | **There is no grasp.** The "squeeze" is a bimanual friction clamp. See §4.3 |
| DOF per leg | 6 | Standard; fine for omnidirectional walking |
| Waist | 1 (Origin) or 2 (RP1) | A yaw waist helps reach; confirm which you have |
| Total DOF | 23 (Origin) / 24 (RP1) | Affects obs/action vector sizes everywhere |
| Height / mass | ~1.25 m / ~34 kg | Drives table height — see §3.2 |
| Rated payload | ~5 kg | Keep boxes ≤ 2 kg for margin |
| Max step height | 50 mm | Floor must be flat; no thresholds in the scene |
| Training stack | Isaac Lab 2.1.1 / Isaac Sim 4.5.0, rsl_rl, **linux-64** | **You are on Windows.** See Risk R1 |
| Sim2sim | MuJoCo, via `roboparty_train` | Use it as the honesty check on the policy |
| License | GPL-3.0 at root; submodules vary | Check before publishing your fork |

### Repository map (upstream)

```
github.com/Roboparty/roboto_origin   # aggregator, read the README first
├── rpo_description      # URDF + MJCF + meshes               <- you need this
├── roboparty_train      # Isaac Lab tasks, rsl_rl, sim2sim    <- you fork this
├── roboparty_deploy     # ROS2 + ONNX inference + Python SDK (hardware; likely unused)
├── rpo_hardware         # CAD/BOM (unused)
└── roboparty_xr_teleop  # possible source of arm demo trajectories
```

---

## 3. Target Architecture

Three layers. **Only the bottom-left box is learned.** Everything else is deterministic, which is exactly what a scripted, repeatable display needs.

```
                    ┌───────────────────────────────────────┐
                    │  SHOW DIRECTOR  (FSM, 20 Hz, Python)  │
                    │  states + guards + nominal durations  │
                    └───┬───────────────────────────┬───────┘
          base_vel_cmd  │                           │  bimanual target + clamp cmd
         (vx, vy, wz)   │                           │  (midpoint, separation, yaw)
                        v                           v
      ┌──────────────────────────┐      ┌──────────────────────────────┐
      │  LOCOMOTION POLICY (RL)  │      │  ARM CONTROLLER (IK + PD)    │
      │  50 Hz, ONNX             │      │  200 Hz, numeric IK          │
      │  12 leg (+waist) targets │      │  10 arm joint targets        │
      └────────────┬─────────────┘      └───────────────┬──────────────┘
                   └──────────────┬────────────────────-┘
                                  v
                   ┌──────────────────────────────┐
                   │  JOINT PD / ACTUATOR MODEL   │  1 kHz, in-sim
                   └──────────────────────────────┘
```

### 3.1 Why the arms are not RL

Your stated pipeline — time-based PID arm control — is the right call, and this plan commits to it. RL for the arms would buy generalization you do not need, since the box positions are fixed and known, at the cost of weeks of reward shaping and non-repeatable motion. IK plus joint PD is deterministic, trivially tunable, and frame-accurate for video.

**One amendment:** make the Show Director a **guarded** FSM rather than purely open-loop. Each state keeps a nominal duration *and* a completion predicate (`base within 5 cm of standoff mark`, `both forearm contacts active`, `box height > table + 3 cm`). Transition on `predicate OR timeout`. Pure wall-clock sequencing drifts the moment the locomotion policy takes one extra step, and you will spend the last week re-tuning magic numbers after every retrain. The guards cost about thirty lines and make the sequence robust to policy changes. Keep a `--force-timed` flag as the fallback if a guard proves flaky near the deadline.

### 3.2 Scene geometry is a design problem, not a detail

The robot is 1.25 m tall, so shoulder height is roughly 0.95–1.0 m and arm length ~0.55 m. The box must sit where the *forearms* can close around it with the elbows comfortably bent — not at the edge of the workspace.

**Week 0 task:** load the URDF, sweep the arm joints, and export the reachable bimanual workspace as a point cloud. Then pick table height and box size from the data. First guess to validate, not to trust: table surface **0.60–0.70 m**, large box **0.25 m** cube, small box **0.15 m** cube, standoff distance **0.45 m** from the table edge. Both tables identical (the brief specifies same size), separated by **2.0 m** with a 90° heading change between them.

---

## 4. The Three Technical Problems

### 4.1 Problem: 5-DOF arms cannot track a 6-DOF pose

A 5-DOF serial arm spans a 5-dimensional subspace of SE(3). Asking for full position plus orientation gives you an unsolvable IK problem that your solver will silently approximate, producing drift and jitter on camera.

**Solution — reparameterize the task bimanually.** Do not track two independent end-effector poses. Track a single 4-DOF *clamp frame*:

| Parameter | Meaning |
|---|---|
| `p_mid ∈ R³` | midpoint between the two contact pads |
| `yaw` | approach heading of the clamp, in torso frame |
| `separation` | distance between the pads — this is the squeeze axis |

Five numbers across ten joints: comfortably over-determined, well-conditioned, and it maps directly onto what the motion actually is. Solve with damped least-squares IK (λ ≈ 0.05) on the 10-joint bimanual chain, with a nullspace term pulling toward a nominal elbow-out posture for a natural silhouette.

**Deliverable:** `control/arm_ik.py` exposing `solve(p_mid, yaw, separation) -> q_arms[10]`, plus a unit test asserting residual < 5 mm across the scripted trajectory.

### 4.2 Problem: carrying a box breaks a vanilla locomotion policy

A 2 kg mass held 0.4 m in front of the torso shifts the CoM forward and adds inertia the policy has never seen. A policy trained on the bare robot will pitch forward and fall, or shuffle visibly. This is the most commonly underestimated failure in loco-manipulation demos.

**Solution — payload-aware domain randomization.** In the training env:

- Attach a rigid body of randomized mass **0–3 kg** at a randomized offset **0.25–0.50 m** forward and **0.7–1.0 m** up from the base frame
- **Randomize its appearance and disappearance mid-episode** — this is what pickup and place actually look like to the legs, and training through the transient is what makes beats 5 and 10 survive
- Drive the arm joints with smooth random trajectories (filtered noise, realistic velocity limits) so the legs learn to reject arm-swing torque
- Randomize base mass ±15%, friction 0.4–1.2, and add push perturbations

**Command space** — the show needs all of these, so train all of these:

| Command | Range | Used in beat |
|---|---|---|
| `vx` forward | 0 → 0.6 m/s | 2, 8 |
| `vx` backward | −0.4 → 0 m/s | 6, 11 |
| `vy` lateral | ±0.3 m/s | 3, 9 |
| `wz` yaw rate | ±0.8 rad/s | 7, 11 |
| **zero command (stand still)** | all zero | **4, 5, 10** |

**Call out the stand-still case explicitly.** Beats 4, 5 and 10 are stationary while the arms move and a mass appears or vanishes. Most locomotion reward sets treat zero-command as a trivial case, so it ends up undertrained and twitchy — which reads terribly on video. Add a dedicated stance term penalizing base XY drift and foot slip under zero command, and oversample zero-command episodes to roughly 25% of the batch.

### 4.3 Problem: there are no hands

With dummy end effectors, holding the box means **friction force closure between two opposing pads**. The statics are easy: you need `2·μ·N ≥ m·g`, so a 2 kg box at μ = 0.8 needs only about 12 N of squeeze per side. The *simulation* of it is the hard part — PhysX contact jitter, penetration recovery, and solver slop routinely let boxes squirt out of a clamp that is analytically sound.

**Run two tracks in parallel. Do not bet the deadline on the hard one.**

**Track A — Grasp latch (the reliable path, build this first).**
When `both pads in contact` AND `squeeze force > F_min` AND `held for 10 consecutive frames`, create a fixed joint between the box and a virtual frame at the clamp midpoint, with a breakaway force threshold. Release destroys the joint. This is standard practice for display demos and it will carry your video. **Disclose it plainly in the report** — a documented assist is good engineering; an undisclosed one is not.

**Track B — True friction clamp (the stretch goal).**
- Physics material: static friction ≥ 1.0, dynamic ≥ 0.9, restitution 0
- Solver: position iterations 16, velocity iterations 4; substep to 1/480 s during beats 4–10 only
- Collision geometry: add compliant pad primitives to the forearms rather than using raw mesh collision
- Contact offset and rest offset tuned to avoid the jitter-penetration oscillation

If Track B lands by the end of Week 4, shoot the video with it and keep a Track A take as the safety. Either way, the side-by-side comparison is a genuinely interesting slide for the presentation.

---

## 5. Inheriting the Classmate's G1 Hybrid Policy

**Set expectations now: the checkpoint will not transfer.** The G1 has 7-DOF arms and a different leg kinematic chain; the Roboto Origin has 5-DOF arms and 23–24 total DOF. Observation and action dimensions differ, link masses differ, gear ratios differ. **Budget a full retrain from scratch.** What transfers is the *architecture, the env scaffolding, and the reward terms* — still easily a week of saved work.

**Integration contract — ask your classmate for exactly this list:**

- [ ] The Isaac Lab task/env file and its config class
- [ ] **Exact observation vector definition and ordering**, with units and frames
- [ ] Observation normalization statistics, if any
- [ ] Action scaling, decimation, control dt, and default joint position offsets
- [ ] Every reward term with its weight
- [ ] The EE-tracking head: how targets are parameterized and in which frame
- [ ] Termination and curriculum conditions
- [ ] The rsl_rl runner config (network sizes, PPO hyperparameters)
- [ ] Whether the hybrid split is a single policy with a gated head, or two policies — **this is the key architectural question**

Record the answers in `docs/inherited_policy.md`. Credit them in the report and the video credits.

---

## 6. Roadmap

Weeks are anchored to a **demo date of ~2026-12-12**. Shift the whole grid if your actual date differs. Each milestone has a hard gate — **do not start the next week's work until the gate passes**, because every one of these failures is cheaper to fix early than to debug through three layers later.

### Week 0 — Nov 5–9 · Foundations and de-risking
> **This week is mostly about finding out what is false in this plan.**

- Resolve the **Windows/Linux blocker** (Risk R1) — WSL2 with Ubuntu 22.04 and CUDA, or a lab Linux box. Do this on day one.
- Clone `roboto_origin` and all submodules; install Isaac Lab 2.1.1 and Isaac Sim 4.5.0
- **Verify the actual DOF count, joint limits, link masses and torque limits** from `rpo_description` against §2 of this document. Correct this file where it is wrong.
- Load the URDF in Isaac Sim and the MJCF in MuJoCo; confirm they agree (same joint order, same masses)
- Run a stock `roboparty_train` locomotion task for 100 iterations — this proves the toolchain
- Export the bimanual reachable workspace; finalize table height, box dimensions, standoff distances (§3.2)
- Send the §5 integration contract to your classmate

**GATE 0:** Robot stands stably in both Isaac Lab and MuJoCo. Scene dimensions are fixed and written into `configs/scene.yaml`. GPU training confirmed working.

### Week 1 — Nov 10–16 · Locomotion baseline
- Fork `roboparty_train`; create the `santa_locomotion` task
- Implement the full command space from §4.2 (forward, **backward**, lateral, yaw, **zero**)
- Baseline domain randomization: friction, base mass, pushes, observation noise
- Train to convergence; iterate on reward weights
- **Sim2sim to MuJoCo** — this is the honesty check, do not skip it

**GATE 1:** Omnidirectional walking including backward and turn-in-place, stable for 60 s under random command sequences, surviving the MuJoCo transfer without visible degradation.

### Week 2 — Nov 17–23 · Payload robustness and arm control
- Add payload randomization with mid-episode mass appear/disappear (§4.2)
- Add randomized arm-motion disturbance
- Add the dedicated zero-command stance reward; oversample stance episodes
- Retrain; compare against the Week 1 baseline on a carry benchmark
- **In parallel:** implement `control/arm_ik.py` (§4.1) with the bimanual 4-DOF parameterization and its unit test
- Script the arm keyframe trajectories for approach / clamp / lift / lower / release

**GATE 2:** Robot walks a 3 m loop carrying a 2 kg payload, no falls, 10/10 trials. Arm IK tracks the full scripted trajectory with < 5 mm residual and no joint limit violations.

### Week 3 — Nov 24–30 · Clamp and single-box integration
> ⚠️ **Thanksgiving is Thursday Nov 26 — this week has roughly three working days. Plan accordingly.**

- Build the scene: two tables, two boxes, floor, tree placeholder
- Implement **Track A grasp latch** (§4.3) — get this working before touching Track B
- Implement the Show Director FSM with guarded transitions (§3.1)
- Integrate: run beats 1–11 for **one box only**, end to end
- Begin Track B friction tuning if time allows

**GATE 3:** One box relocated from Table A to Table B, autonomously, **3/5 attempts**.

### Week 4 — Dec 1–7 · Full sequence and robustness
- Extend the FSM to the second box (return leg, re-approach, smaller box)
- Note that **end-to-end success compounds** — two cycles at 90% each is 81% overall, so Gate 4 is meaningfully harder than twice Gate 3
- Seed sweep: 20 runs, log every failure, categorize, fix the top two modes
- Tune for *visual* quality, not just success: smooth arm velocity profiles, no twitching at stance, natural elbow posture
- Track B decision point — ship it or fall back to Track A

**GATE 4:** Full two-box sequence, **8/10 runs**, no falls. This is the engineering finish line; everything after is presentation.

### Week 5 — Dec 8–12 · Production
- Scene dressing: Christmas tree, wrapping-paper textures on the boxes, Santa hat on the robot, warm lighting
- Camera work: at minimum a wide establishing shot, a tracking medium shot, and a close-up on the clamp
- Render in **Isaac Sim** (RTX path tracing, Movie Capture) — not MuJoCo, whose rendering will not hold up on a projector
- Edit; add titles and credits
- Write the report: architecture, RL methodology, the 5-DOF and no-hands constraints and how you handled them, the disclosed physics assist, results table, failure analysis
- Prepare the Track A / Track B side-by-side slide

**GATE 5:** Final video exported. Report submitted. Repo has a README that reproduces the result.

---

## 7. Risk Register

| ID | Risk | Lik. | Impact | Mitigation | Resolve by |
|----|------|------|--------|------------|-----------|
| **R1** | **Dev machine is Windows; `roboparty_train` is linux-64** | High | **Blocking** | WSL2 + Ubuntu 22.04 + CUDA passthrough, or a lab Linux workstation. Verify GPU visibility inside WSL before anything else. | **Day 1** |
| **R2** | No hands → friction clamp unreliable in PhysX | High | High | Track A grasp latch as the primary path (§4.3) | Week 3 |
| **R3** | Payload destabilizes locomotion | High | High | Payload DR with mid-episode transients (§4.2) | Week 2 |
| **R4** | G1 policy does not transfer | **Certain** | Medium | Already assumed — architecture reference only, budget a full retrain (§5) | Week 0 |
| **R5** | Published RPO specs are wrong / model files differ | Medium | Medium | Verify everything against `rpo_description` in Week 0 and correct this document | Week 0 |
| **R6** | Insufficient GPU hours for RL iteration | Medium | High | Reserve lab GPU time now. Budget ~2 h per run and ~15 runs. Checkpoint aggressively. | Week 0 |
| **R7** | 5-DOF IK singular or unreachable at the box pose | Medium | High | Workspace sweep *before* fixing scene geometry (§3.2); DLS damping | Week 0 |
| **R8** | Two-cycle success probability compounds | Medium | Medium | Scope ladder (§8) — one box is still a passing demo | Week 4 |
| **R9** | Isaac Lab / Isaac Sim version mismatch breaks the fork | Medium | Medium | Pin exact versions in `environment.yml`; do not upgrade mid-project | Week 0 |
| **R10** | Last-week render and edit crunch | Medium | Medium | Do a throwaway full render in Week 3 to surface pipeline problems early | Week 3 |

---

## 8. Scope Ladder — guarantee a video

Work down this list only if you must. **Tier 0 is the submission; everything above it is upside.** Decide at the Week 4 gate.

| Tier | Scope | Status |
|------|-------|--------|
| **T0 — Must ship** | One box, Table A → Table B, grasp latch, basic scene, single camera | Non-negotiable |
| **T1** | Both boxes, full two-cycle sequence | Target |
| **T2** | True friction clamp (Track B), no latch | Stretch |
| **T3** | Full Santa dressing, multi-camera, path-traced render | Polish |
| **T4** | Onboard-camera POV shot, real-time telemetry overlay | If miraculous |

---

## 9. Proposed Repo Layout

```
SantaDisplayRoboto/
├── PLAN.md                     # this file
├── README.md                   # reproduction instructions
├── environment.yml             # pinned: IsaacLab 2.1.1, IsaacSim 4.5.0, py3.10
├── external/
│   └── roboto_origin/          # submodule / vendored upstream
├── assets/
│   ├── robot/                  # URDF, MJCF, USD conversions
│   └── scene/                  # tables, boxes, tree, textures
├── envs/
│   └── santa_locomotion/       # IsaacLab task: cfg, rewards, randomization
├── control/
│   ├── fsm.py                  # Show Director, guarded transitions
│   ├── arm_ik.py               # bimanual DLS IK (p_mid, yaw, separation)
│   ├── locomotion_runtime.py   # ONNX policy wrapper
│   └── grasp_latch.py          # Track A attach/release
├── configs/
│   ├── scene.yaml              # table heights, box dims, marks, standoffs
│   ├── show.yaml               # FSM durations, guard tolerances
│   └── gains.yaml              # arm PD gains
├── policies/                   # checkpoints + exported ONNX
├── scripts/
│   ├── train.py  play.py  sim2sim.py  record.py  workspace_sweep.py
├── docs/
│   ├── inherited_policy.md     # §5 integration contract answers
│   └── results.md              # seed sweep logs, failure taxonomy
└── media/                      # renders, final cut
```

---

## 10. Open Questions

Non-blocking — the plan proceeds on the stated assumption, but confirm these in Week 0.

| Question | Assumed |
|---|---|
| Actual demo/submission date? | **2026-12-12** — shift the week grid if different |
| Simulation only, or hardware deployment too? | **Simulation only** (per the brief) |
| Which variant — Origin 23-DOF or RP1 24-DOF? | Origin; verify from `rpo_description` |
| GPU access — personal, lab, or cluster? | Unresolved — **this gates Week 1** |
| Is the classmate's repo shareable, and under what terms? | Assumed yes, with attribution |
| Team size and split? | Suggested: one on RL/locomotion, one on arms/FSM/scene, shared on video |

---

## Sources

Platform facts in §2 were gathered from:
- [github.com/Roboparty/roboto_origin](https://github.com/Roboparty/roboto_origin) — module list, Isaac Lab/Isaac Sim/ROS2 version badges, GPL-3.0
- [humanoid.guide/product/roboto-origin](https://humanoid.guide/product/roboto-origin/) — 23 DOF, 0 hands, 125 cm, 34 kg, 5 kg payload (page carries a "Not Verified" badge)
- [cnx-software.com — RoboParty RP1 (ROBOTO 01)](https://www.cnx-software.com/?p=178402) — per-limb DOF breakdown, 50 mm step height, dummy hands on the base model, submodule descriptions

These sources disagree on generation and specifics. **Gate 0 exists to replace them with ground truth from `rpo_description`.**
