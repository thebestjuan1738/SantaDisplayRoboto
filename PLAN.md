# Santabot — Holiday Gift Delivery

**Course:** Human-Centered Robotics — Final Motion Display
**Team:** Cody Andres Alessio-Bunnell · Sergio Sánchez Manso · Zhao-Yu "Yuki" Lu
**Platform:** RoboParty *Roboto Origin* (RPO)
**Milestones:** Review **2026-11-19** · Demonstration **2026-12-03**
**Plan revision:** 2026-11-12 — reconciled against the team slide deck

> This file is the engineering plan behind the deck. The deck is the source of truth for
> scope, schedule, team split and success criteria; **this file is the source of truth for
> architecture and implementation detail.** The deck summarizes; §5 specifies. §3 covers the
> few places the deck has not yet caught up with the engineering analysis.

---

## 1. Committed Task Definition (from the deck)

Santabot carries two presents from one table to the adjacent table, one at a time, and places each at the mirrored position "under the tree."

**Presents**
- Large: **12″ × 12″ × 12″** cardboard cube (≈ 305 mm)
- Small: **8″ × 8″ × 8″** cardboard cube (≈ 203 mm)
- Both light (empty cardboard)

**Configuration**
- Two tables, **adjacent** — they meet at an intersection
- **Home position:** 1 ft (≈ 305 mm) from the table intersection, facing the tables, relaxed pose
- Small present: **6″ from each corner** of the table
- Large present: **6″ to the left of the small**
- Presents go to the **mirrored position** on the second table

**Grip**
- The robot **squeezes each present between its wrists**. There is no hand.

**Success criteria**
| Requirement | Value |
|---|---|
| Sequence | home → table → move both presents → return home → **stand 1 s** |
| Repeatability | **2 successes out of 3 runs** |
| Time limit | **4 minutes per run** |
| Recorded per run | completion, drops, falls, duration |

---

## 2. Status (from the deck)

| | Item |
|---|---|
| ✅ Ready | Robot model · two-table scene · single-present code |
| ⬜ Needed | Two-present code · reach check · training computer · supervised robot tests |
| ❌ Not yet | **No trained behavior. No hardware result.** |

The scene preview in the deck is static, and the tables still need moving to the adjacent layout.

---

## 3. Reading the Deck Against This Plan

Two corrections the deck has not caught up with yet, plus one note on how to read its control-route slide.

### 3.1 The deck's "Control Route" slide summarizes §5 — it is not a different design

The deck says one learned policy, where "rewards and penalties shape gait, grip, placement and balance" and "policy outputs joint movements for each task phase." That is presentation-level phrasing for the architecture specified in §5: **RL for locomotion, IK + PD for the arms, an FSM for sequencing.** The deck's fallback line — "planned motions with feedback" — describes the arm layer that is already the primary design.

Nothing to decide here. Keep the deck's wording for the audience; build §5.

The one thing worth doing before the review is agreeing how all three of you answer if an instructor asks what "the policy" actually covers:

> It learns to walk, turn, and stay balanced — including while carrying a present. It does not learn the squeeze or the placement; those are commanded from measured positions.

That phrasing is accurate, matches the deck, and avoids claiming an end-to-end result you are not producing.

### 3.2 The 12″ present is the top feasibility risk, and the deck under-rates it

The deck lists "the 12″ present may be harder to grip with the wrists" as one risk among five. It is not one among five — it is **the** risk, and it is a *kinematic* question that can be answered this week, not a tuning question.

Squeezing a 305 mm cube between the wrists requires both wrists simultaneously ≥ 305 mm apart, forward of the torso, and at box-centre height. With **5-DOF arms** on a 1.25 m robot (arm ≈ 550 mm), that is a large shoulder abduction at a long moment arm. It may simply be outside the usable workspace.

**Do the reach check first, before any training.** It is a few hours of work and it determines whether the 12″ present is in scope at all. If it fails, you need to know on Nov 13, not Nov 28 — the deck's own fallback (start with the 8″) becomes the plan, and that is a fine outcome *if discovered early*.

### 3.3 "No sensing abilities" is a hardware-only problem — and it is a big one

The deck lists this risk without separating the two environments:

- **In simulation**, ground-truth pose is free. Placement accuracy is a non-issue.
- **On hardware**, there is no perception in the loop. Every position is open-loop dead reckoning from the home pose, and drift accumulates across an entire 4-minute sequence of walking, turning and returning. A few centimetres of yaw drift on the approach becomes a missed present.

This is the reason to expect the sim→hardware gap to be *large* regardless of how good the policy is. Mitigations, cheapest first:

1. **Physical registration** — a marked home position and table edges the robot can touch to re-zero
2. **Generous tolerances** — oversize the target placement zone; "mirrored position" need not be millimetre-accurate
3. **Re-zero between presents** — return to home and re-register before the second delivery rather than carrying drift through
4. **IMU yaw integration** for heading hold during the turn
5. **RealSense D435i** (optional on this platform) — only if it is already mounted and working; integrating perception in three weeks is not realistic

Decide at the hardware interface audit (task 4) which of these you get.

---

## 4. Platform Constraints

From the RoboParty repos and spec pages. **Verify against the actual model files** — the published sources disagree with each other, and you already have the robot model, so this is a quick confirmation.

| Property | Value | Consequence |
|---|---|---|
| **DOF per arm** | **5** | Cannot command a full 6-DOF wrist pose — see §5.2 |
| **Hands** | **Dummy, 0 finger DOF** | Confirms the deck's wrist-squeeze approach is the only option |
| DOF per leg | 6 | Fine for omnidirectional walking |
| Waist | 1 (Origin) / 2 (RP1) | Waist yaw materially helps the reach check |
| Total DOF | 23 (Origin) / 24 (RP1) | Sets obs/action vector sizes |
| Height / mass | ~1.25 m / ~34 kg | Drives table height |
| Rated payload | ~5 kg | Non-issue — cardboard boxes are well under |
| Max step height | 50 mm | Flat floor only; watch for cable runs and thresholds on the lab floor |
| Training stack | Isaac Lab 2.1.1 / Isaac Sim 4.5.0, rsl_rl, **linux-64** | The "training computer" the deck needs must be Linux |
| Sim2sim | MuJoCo | Use it as the honesty check before hardware |
| Sensing | 6-axis IMU; RealSense D435i optional | See §3.3 |
| License | GPL-3.0 at root; submodules vary | Check before publishing the fork |

### Upstream repository map

```
github.com/Roboparty/roboto_origin
├── rpo_description      # URDF + MJCF + meshes          <- reach check uses this
├── roboparty_train      # Isaac Lab tasks, rsl_rl, sim2sim
├── roboparty_deploy     # ROS2 + ONNX inference + Python SDK  <- the hardware path
├── rpo_hardware         # CAD/BOM
└── roboparty_xr_teleop  # possible source of arm trajectories
```

`roboparty_deploy` is no longer optional — it is the interface the hardware audit (task 4) must assess.

---

## 5. Architecture

```
                    ┌───────────────────────────────────────┐
                    │  SHOW DIRECTOR  (FSM, 20 Hz, Python)  │
                    │  phases + guards + 4-min watchdog     │
                    └───┬───────────────────────────┬───────┘
          base_vel_cmd  │                           │  wrist-clamp target
         (vx, vy, wz)   │                           │  (midpoint, yaw, separation)
                        v                           v
      ┌──────────────────────────┐      ┌──────────────────────────────┐
      │  LOCOMOTION POLICY (RL)  │      │  ARM CONTROLLER (IK + PD)    │
      │  50 Hz, ONNX             │      │  200 Hz, damped-LS IK        │
      │  12 leg (+waist) targets │      │  10 arm joint targets        │
      └────────────┬─────────────┘      └───────────────┬──────────────┘
                   └──────────────┬────────────────────-┘
                                  v
          Sim: Isaac Lab / MuJoCo   ·   Hardware: roboparty_deploy (ROS2 + ONNX)
```

**Only the locomotion layer is learned.** That split is deliberate:

- **Legs → RL.** Balance and gait under a shifting payload are exactly what RL is good at, there is no practical closed-form alternative, and `roboparty_train` already ships a working recipe to fork.
- **Arms → IK + PD, not RL.** The present positions are fixed and measured (§1), so there is nothing to generalize over. RL here would buy generalization you do not need, at the cost of weeks of reward shaping and motion that differs run to run. IK plus joint PD is deterministic, tunable, and reproducible — which is what a graded 2-of-3 demonstration actually rewards.
- **Sequencing → FSM, not a learned phase selector.** Long-horizon phase transitions from sparse reward are the hardest thing to train and the hardest to debug under a 4-minute clock. An explicit state machine is inspectable: when a run fails you know *which phase* it failed in, which is exactly what task 3's diagnosis step needs to produce.

### 5.1 The FSM needs a watchdog, not just guards

Each phase carries a nominal duration *and* a completion predicate (`base within tolerance of mark`, `both wrist contacts active`, `box clear of table`). Transition on `predicate OR timeout`.

Add one thing the Nov 5 draft did not have: a **global 4-minute watchdog**. The deck imposes a hard time limit, so the FSM must track elapsed time and, if it is running long, either skip the optional polish or abort cleanly to a safe stance. A run that fails at 4:05 having otherwise succeeded still scores as a failure — budget phase durations against the clock from the start.

Nominal budget (≈ 150 s, leaving ~60% margin on the 4-minute limit):

| Phase | Duration |
|---|---|
| Home → approach table A | 15 s |
| Align + squeeze large present | 12 s |
| Lift, turn to table B, place, release | 30 s |
| Return for small present | 20 s |
| Align + squeeze small present | 12 s |
| Lift, turn, place, release | 30 s |
| Return home + stand 1 s | 20 s |

### 5.2 5-DOF arms cannot track a 6-DOF pose

A 5-DOF chain spans a 5-dimensional subspace of SE(3); a 6-DOF target gives an unsolvable IK problem your solver will silently approximate, producing drift. Reparameterize to a **4-DOF wrist-clamp frame**:

| Parameter | Meaning |
|---|---|
| `p_mid ∈ R³` | midpoint between the two wrists |
| `yaw` | approach heading in torso frame |
| `separation` | wrist-to-wrist distance — the squeeze axis (**305 mm** for the large, **203 mm** for the small) |

Five numbers across ten joints: over-determined and well-conditioned. Solve with damped least-squares (λ ≈ 0.05) plus a nullspace term toward a nominal elbow-out posture.

**Deliverable:** `control/arm_ik.py` → `solve(p_mid, yaw, separation) -> q_arms[10]`, with a unit test asserting < 5 mm residual across the scripted trajectory. **This same code is the reach check** — build it first and you get §3.2's answer for free.

---

## 6. The Technical Problems

### 6.1 Holding a box between two wrists

With no fingers, this is friction force closure: `2·μ·N ≥ m·g`. Light cardboard helps enormously — a 12″ empty box is roughly 0.3–0.5 kg, so at μ = 0.8 you need only ~3 N of squeeze per side. **The statics are easy. The simulation is not**, and cardboard adds a wrinkle hardware-side.

**Track A — Grasp latch (build first, this carries the demo).**
When `both wrists in contact` AND `squeeze force > F_min` AND `held 10 consecutive frames`, create a fixed joint between the box and a virtual frame at the clamp midpoint, with a breakaway threshold. Release destroys it. Standard practice for a simulated display. **Disclose it in the report** — a documented assist is good engineering; an undisclosed one is not. Note it has no hardware analogue, which is part of why §3.3's gap is real.

**Track B — True friction clamp (stretch).**
- Static friction ≥ 1.0, dynamic ≥ 0.9, restitution 0
- Solver position iterations 16, velocity 4; substep to 1/480 s during contact phases only
- Compliant pad primitives on the wrists rather than raw mesh collision
- Tune contact/rest offset to avoid jitter-penetration oscillation

**Hardware wrinkle:** real cardboard **deforms and crushes** under a wrist squeeze, and a crushed box changes dimensions mid-run. Sim will model it rigid. Mitigate by taping the boxes closed, keeping squeeze force just above the slip threshold, and — if needed — lightly stiffening the boxes internally. Confirm with the instructor that stiffened boxes are acceptable.

### 6.2 Carrying a present while walking

A mass held forward of the torso shifts the CoM and adds inertia the policy has not seen. **This is much less severe than the Nov 5 draft assumed** — cardboard boxes are light, so revise payload randomization down to **0–1.5 kg** (was 0–3 kg). Keep the mechanism, though: the *geometric* disturbance remains, because a 305 mm box held at arm's length moves the CoM meaningfully even at 0.4 kg.

In the training env:
- Randomized mass **0–1.5 kg** at **0.25–0.50 m** forward, **0.7–1.0 m** up from base frame
- **Randomize appearance/disappearance mid-episode** — this is exactly what pickup and place look like to the legs
- Smooth random arm trajectories so the legs learn to reject arm-swing torque
- Base mass ±15%, friction 0.4–1.2, push perturbations

**Command space** — the adjacent-table layout is turn-heavy, not transit-heavy:

| Command | Range | Used in |
|---|---|---|
| `vx` forward | 0 → 0.6 m/s | approach, return |
| `vx` backward | −0.4 → 0 m/s | retreat from table |
| `vy` lateral | ±0.3 m/s | fine alignment |
| `wz` yaw rate | ±0.8 rad/s | **the table-to-table transition — heavily weighted** |
| **zero (stand still)** | all zero | **squeeze, place, and the final 1 s stand** |

Two emphases specific to this task. **Turning matters more than walking** — the tables are adjacent, so the robot pivots far more than it transits; weight yaw commands accordingly. And **the final 1-second stand is a graded requirement**, not an afterthought: add a dedicated zero-command stance term penalizing base XY drift and foot slip, and oversample zero-command episodes to ~25% of the batch. Most reward sets treat zero-command as trivial and it ends up twitchy.

---

## 7. Roadmap

Anchored to the deck's Gantt. Dependencies carried over: task 2 needs 1; task 3 needs 2; task 5 needs the interface audit, a supervisor and lab access.

**Owners** (per the deck, pending team confirmation): **Yuki** — task definition and integration · **Cody** — control and robot interface · **Sergio** — trials and diagnosis.

### Now — through Nov 12 · closing out Stage 1
- [x] Two-present task agreed *(task 1 — Yuki)*
- Scene + return logic underway *(task 2 — Cody)*
- **Add: resolve the training computer.** It must be Linux (§4). This gates everything in the next block and the deck already lists it as needed.

### Nov 13–19 · Scene, reach check, and the Nov 19 review
> **The review lands at the end of this block. Go in with the reach check answered.**

- **Reach check first** (§3.2) — build `control/arm_ik.py`, sweep the bimanual workspace, answer whether **305 mm wrist separation is achievable**. A few hours; it determines scope.
- Move tables to the adjacent layout; place presents at the deck's measured positions (small 6″ from each corner, large 6″ to its left)
- Extend single-present code to two presents, including the return leg *(task 2)*
- Fork `roboparty_train`; create the `santabot_locomotion` task with the §6.2 command space
- Start locomotion training — this is the long pole and needs wall-clock time
- **Submit the hardware interface request** *(task 4 — Cody + Yuki)*. Lead time is the risk; file it early.
- Agree the shared one-line description of the architecture for the review (§3.1)

**GATE A — by Nov 19:** Reach check answered for both present sizes. Two-present scene built. Locomotion training running. Hardware request submitted.

### Nov 20–22 · Full sequence in simulation
- Implement the grasp latch (§6.1 Track A)
- Implement the FSM with guards and the 4-minute watchdog (§5.1)
- **Test the full sequence and diagnose** *(task 3 — Sergio)* — run it end to end, record **where it first fails**, per the deck's first-experiment plan
- Conduct the hardware interface audit *(task 4)*

**GATE B — by Nov 22:** Full two-present sequence runs in simulation at least once, with a written failure log.

### Nov 23–29 · Integration and trials
> ⚠️ **Thanksgiving is Thursday Nov 26** — this block is shorter than it looks.

- Integrate the hardware interface *(task 4)*
- **Book and begin supervised trials** *(task 5 — Cody + Sergio)*. Lab access and a supervisor are hard dependencies — if either slips, fall back to §9 T1 and say so early.
- Harden simulation: 20-run seed sweep, categorize failures, fix the top two modes
- Time every run against the 4-minute limit
- Sim2sim to MuJoCo before any hardware run — do not skip this

**GATE C — by Nov 29:** 2-of-3 success demonstrated in simulation. Hardware either integrated and trialled, or formally descoped.

### Nov 30–Dec 3 · Buffer, analysis, demonstration
- Trial buffer *(task 5)* — this is the deck's own slack; protect it
- Analysis and final handoff *(task 6 — all three)*: compare simulation against hardware, report every run outcome against the 2-of-3 bar with durations
- Record the demonstration video
- Prepare the Track A / Track B disclosure and the sim-vs-hardware gap discussion

**GATE D — Dec 3:** Demonstration delivered. Every run logged with completion, drops, falls and duration.

---

## 8. Hardware Workstream

New relative to the Nov 5 draft, which assumed simulation only. Tasks 4 and 5 in the deck make hardware a first-class track.

**Interface audit checklist** *(task 4)*
- [ ] Can `roboparty_deploy` run the exported ONNX policy on the onboard compute?
- [ ] Joint ordering, sign conventions and offsets — **confirm they match the sim model exactly.** This is the classic silent sim-to-real failure.
- [ ] Control rate achievable on hardware vs the 50 Hz the policy expects
- [ ] E-stop procedure, and who holds it
- [ ] Is the RealSense mounted and functional? (§3.3 option 5)
- [ ] Battery runtime vs a 4-minute run plus setup — how many trials per charge?
- [ ] Fall protection: gantry, harness, or spotters?

**Trial protocol** *(task 5)*
- Supervisor present, lab access booked, e-stop held by a named person
- Start with the robot stationary and arms only, then walking without a present, then the full sequence
- Log every run: completion, drops, falls, duration — as the deck specifies
- Stop on repeated falls; diagnose in simulation, not on the robot

**Descope trigger.** If lab access or supervision is not confirmed by **Nov 23**, declare hardware out of scope and deliver the simulation result. Say it at the review rather than discovering it on Dec 1.

---

## 9. Scope Ladder

The deck's fallback is "build the behavior one present at a time, starting with the 8″." This formalizes it. Decide at Gate C.

| Tier | Scope |
|---|---|
| **T0 — must ship** | **8″ present only**, simulation, full sequence incl. return home + 1 s stand, 2 of 3 |
| **T1** | Both presents in simulation, 2 of 3, under 4 minutes |
| **T2** | T1 + supervised hardware trials, any outcome, honestly reported |
| **T3** | Hardware achieves 2 of 3 |
| **T4** | True friction clamp (no latch) + polished scene and video |

T0 is a complete, honest deliverable. The deck's own fallback language already licenses it.

---

## 10. Risk Register

| ID | Risk | Lik. | Impact | Mitigation | By |
|----|------|------|--------|-----------|-----|
| **R1** | **12″ present outside wrist-squeeze workspace** | Med-High | **Scope-defining** | Reach check first (§3.2); fall back to 8″-only (T0) | **Nov 19** |
| **R2** | **No training computer / not Linux** | High | **Blocking** | Resolve now — deck already flags it; `roboparty_train` is linux-64 | **Nov 13** |
| **R3** | **Lab access or supervision not granted** | Med-High | High | File request Nov 13; descope trigger Nov 23 (§8) | Nov 23 |
| **R4** | **Locomotion policy doesn't converge in time** | Med | **High** | Fork `roboparty_train`'s working recipe rather than writing rewards from scratch; start training Nov 13, not later (§7) | **Nov 22** |
| **R5** | Open-loop drift ruins hardware placement | High | High | Physical registration, generous tolerances, re-zero between presents (§3.3) | Nov 29 |
| R6 | Wrist friction clamp unreliable in PhysX | High | Med | Grasp latch as primary (§6.1 Track A) | Nov 22 |
| R7 | Cardboard crushes under squeeze on hardware | Med | Med | Tape closed, minimal squeeze force, confirm stiffening with instructor | Nov 29 |
| R8 | Robot stops after the first delivery | Med | Med | Deck's own risk — FSM return-leg logic + explicit test (task 3) | Nov 22 |
| R9 | Run exceeds 4 minutes | Low-Med | High | Phase budget + global watchdog (§5.1); time every run | Nov 29 |
| R10 | Sim joint order ≠ hardware joint order | Med | **High** | Explicit check in the interface audit (§8) | Nov 29 |
| R11 | Payload destabilizes locomotion | Low-Med | Med | Payload DR 0–1.5 kg with mid-episode transients (§6.2). Downgraded — boxes are light | Nov 22 |
| R12 | Thanksgiving compresses the Nov 23–29 block | Certain | Low-Med | Front-load into Nov 20–22; protect the Nov 30 buffer | Nov 23 |

---

## 11. Repo Layout

```
SantaDisplayRoboto/
├── PLAN.md                     # this file
├── README.md                   # reproduction instructions
├── environment.yml             # pinned: IsaacLab 2.1.1, IsaacSim 4.5.0, py3.10
├── external/roboto_origin/     # upstream submodule
├── assets/
│   ├── robot/                  # URDF, MJCF, USD
│   └── scene/                  # adjacent tables, 12"/8" presents, tree
├── envs/santabot_locomotion/   # IsaacLab task: cfg, rewards, randomization
├── control/
│   ├── fsm.py                  # phases, guards, 4-min watchdog
│   ├── arm_ik.py               # bimanual DLS IK — also the reach check
│   ├── locomotion_runtime.py   # ONNX wrapper (shared sim + hardware)
│   └── grasp_latch.py          # Track A attach/release (sim only)
├── configs/
│   ├── scene.yaml              # table layout, present positions, home mark
│   ├── show.yaml               # phase budget, guard tolerances
│   └── gains.yaml              # arm PD gains
├── hardware/
│   ├── interface_audit.md      # §8 checklist, filled in
│   └── trial_log.md            # per-run: completion, drops, falls, duration
├── policies/                   # checkpoints + exported ONNX
├── scripts/                    # train.py play.py sim2sim.py record.py reach_check.py
├── docs/results.md             # seed sweeps, failure taxonomy
└── media/                      # renders, final cut
```

---

## 12. To Confirm

The deck's own open list, plus what this analysis adds.

| Question | Owner | By |
|---|---|---|
| **Present weights** (deck) | Sergio | Nov 13 — needed for payload DR |
| **Feasible wrist grip** (deck) | Cody | **Nov 19 — this is the reach check, §3.2** |
| **Training access** (deck) | Cody | **Nov 13 — blocking, must be Linux** |
| **Lab time** (deck) | Cody + Yuki | Nov 23 — descope trigger |
| Agree a shared description of the architecture for the review (§3.1) | All three | Nov 19 |
| Confirm Gantt owner assignments | All three | Nov 13 |
| Table height — derive from the reach check, not guessed | Cody | Nov 19 |
| Is stiffening the cardboard boxes allowed? | Sergio | Nov 23 |
| Is the grasp latch acceptable if disclosed? | All three | Nov 22 |

---

## Sources

- Team slide deck, *Santabot: Holiday Gift Delivery*, version dated 2026-11-12 — task definition, configuration, success criteria, Gantt, risks, fallback
- [github.com/Roboparty/roboto_origin](https://github.com/Roboparty/roboto_origin) — module list, Isaac Lab / Isaac Sim / ROS2 version badges, GPL-3.0
- [humanoid.guide/product/roboto-origin](https://humanoid.guide/product/roboto-origin/) — 23 DOF, 0 hands, 125 cm, 34 kg (page carries a "Not Verified" badge)
- [cnx-software.com — RoboParty RP1 (ROBOTO 01)](https://www.cnx-software.com/?p=178402) — per-limb DOF breakdown, 50 mm step height, dummy hands, submodule descriptions

The two secondary sources disagree on generation and specifics. You already have the robot model — confirm §4 against it directly.
