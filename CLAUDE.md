# CLAUDE.md

Guidance for Claude Code (and anyone else) working in this repository. Team: Cody, Sergio and Yuki.

## What this is

SantaBot: the RoboParty Roboto Origin (RPO, 23 DoF) moves two gifts between two tables and returns home,
in MuJoCo first, then on hardware (Stage 3, due 2026-12-03). See README.md for the task, scene and design.

- `santabot/` -- high-level controller (`mission.py`), policy adapter (`locomotion.py`), trial loop (`sim.py`)
- `config/santabot.yaml` -- every tunable number; scene dimensions in inches as the brief gives them
- `exports/<name>/` -- trained policy exports (`config.yaml` + `policy.onnx` + `policy.onnx.data`), committed
- `runs/` -- scratch output of every trial; gitignored, never committed
- `videos/` -- the committed video log (see below)
- `docs/EXPERIMENT_LOG.md` -- the dated record of every change and its measured effect
- `slides/build_deck.py` -- regenerates the course deck; the team also keeps a shared Google Slides copy

The trained policy comes from the TA's repo, github.com/mark-helwig/LearningRL, branch
`student/cody-rpo-locomanip`, task `LearningRL-RPO-LocoManipulation-v0` (one policy for legs and arms:
`base_velocity` + `hand_track` wrist targets in, 23 joint targets out). Mark trains it and sends the export.

## Commands

```bash
pytest -q tests                                                     # must pass before committing
python run_trial.py --policy exports/<name>                          # trained policy, unassisted
python run_trial.py --policy exports/<name> --assist full            # policy limbs, pelvis held (bring-up)
python run_trial.py                                                  # assisted mode (no policy)
python run_eval.py --policy exports/<name>                           # 5 nominal + 5 variation trials
python tools/velocity_sweep.py exports/<name>                        # how the policy tracks velocity commands
python tools/diagnose.py                                             # reproduce the controlled iterations
python slides/build_deck.py                                          # rebuild the deck (close it in PowerPoint first)
```

## Rules for every work session

### 1. Keep the experiment log

Every change that is tested gets a numbered row in `docs/EXPERIMENT_LOG.md`, under a `## YYYY-MM-DD` heading,
continuing the numbering: Goal | Change | Command | Observation | Decision. Record failures and numbers
honestly, including runs that made things worse. Update the "Open items" list at the bottom.

### 2. After a major work session, save a video

A major session is one that changes what the robot does: a new policy export, a controller or tuning change
that moves the results, or a fix for a failure. At the end of it, record the current state and add it to the
committed video log:

```bash
python run_trial.py --policy exports/<name> --follow --save-video "short description of what it shows"
```

That records `runs/.../trial.mp4`, copies it to `videos/YYYY-MM-DD_HHMM_<short-description>.mp4` (date and
time of recording) and appends a row to `videos/README.md` with the mode and the results. For a run that is
already recorded: `python tools/save_video.py runs/<dir>/trial.mp4 "short description"`.

Keep descriptions short and factual ("small gift placed, large still drops"), not promotional.
Then commit `videos/`, `docs/EXPERIMENT_LOG.md` and the code together.

### 3. Always say which mode a result comes from

- **Assisted:** pelvis carried by a soft weld, legs scripted, arms by IK. Not a trained policy.
- **Policy, pelvis assisted:** the trained policy drives all joints but the pelvis is held up.
- **Policy, unassisted:** the real test.

Videos carry this in their banner; logs, slides and messages must say it too. Never present assisted
results as trained-policy results.

### 4. A new policy export needs re-calibrating

`navigation.policy_command_map` in the config converts the speed the controller wants into the command a
specific policy needs (the current export ignores commands under ~0.12 m/s). It was measured for
`exports/locomanip_walkv1_7999`. For a new export, run `tools/velocity_sweep.py`, update the table, and log it.

## Environment notes

- Python 3.12, `.venv` from `requirements.txt`; install the TA's `LearningRLsim` with `--no-deps`
  (it pins `mujoco<4`). MuJoCo 4.0.1.
- On Cody's Windows laptop, Smart App Control blocked MuJoCo's DLLs (it was turned off on 2026-11-23).
  If `import mujoco` fails with "An Application Control policy has blocked this file", tell the user;
  do not work around a security setting without asking.
- The robot model is fetched with `python tools/fetch_assets.py` into `vendor/` (gitignored).
- Do not commit `runs/`, `.venv/`, `vendor/`, or PowerPoint lock files (`~$*`).
