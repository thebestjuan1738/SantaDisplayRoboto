# RPO locomanipulation policy, model_7999

Task `LearningRL-RPO-LocoManipulation-v0`, branch `mh/rpo-locomanip-walkv1` (commit `b20dbac`, unpushed):
hand targets on top of the HCRL RPO walk (HCRL-RPO-Walk-Flat-v0). Trained 8000 iterations, 4096 envs.
Training metrics at the end: linear velocity error 0.22 m/s, yaw velocity error 0.60 rad/s, hand position error 7 cm,
0.2 % of episodes ended in a fall.

## Files

| File | What it is |
|---|---|
| `policy.onnx` + `policy.onnx.data` | The actor. Weights live in the `.data` file, so keep the two together in one folder. Input `obs` [1, 86] float32, output `actions` [1, 23]. No observation normalization inside or outside the network. |
| `config.yaml` | Everything the deploy loop needs: observation order, slices and scales, command layout, action scale and offset, joint order, PD gains, effort and velocity limits. |
| `policy_torchscript.pt` | The same actor as TorchScript, if you'd rather run it in torch. |
| `env.yaml`, `agent.yaml` | Full training configs, for reference only. |

## Control loop (50 Hz)

1. Build the 86-dim observation in the order in `config.yaml`, multiplying each term by its `scale`:
   - `base_ang_vel` (3): IMU angular velocity in the base frame, scale 0.2
   - `projected_gravity` (3): gravity unit vector in the base frame
   - `velocity_commands` (3): vx, vy (m/s), yaw rate (rad/s), each within [-1, 1]
   - `joint_pos_rel` (23): joint position minus `default_joint_pos`
   - `joint_vel_rel` (23): joint velocity, scale 0.05
   - `last_action` (23): the raw network output from the previous step (zeros at start)
   - `hand_track` (8): see below
   No base linear velocity is needed.
2. Run the network to get `a` (23).
3. Joint targets = `default_joint_pos + 0.25 * a`, in the `joint_order` listed in `config.yaml`.
4. Send them to joint PD controllers with the `stiffness` / `damping` in `config.yaml` (simulated at 200 Hz, decimation 4).

## The hand command (8 values)

`[left_active, right_active, lx, ly, lz, rx, ry, rz]`

- `*_active` is 1 for a hand that should reach its target, 0 for a hand left free.
- Targets are in metres, in the **yaw-aligned root frame**: origin at the pelvis (root body) position,
  x forward and y left along the robot's heading, z up along world vertical (roll and pitch removed).
- The tracked point is **0.135 m along the x axis of each `<side>_elbow_yaw_link`**, near the forearm tip.
  The RPO has no hand link.
- Trained ranges: x 0 to 0.40, z -0.15 to 0.35 (both hands share x and z unless you send different values),
  left y 0 to 0.35, right y -0.35 to 0. Stay inside these.
- All eight zeros means "no hand task"; the arms then just help balance. In training, a hand marked inactive
  still carried a random target value, which the policy learned to ignore.
- Targets were resampled every 0.5 to 2 s in training, so it expects them to jump and to hold for a while.

## Caveats

- Only tested in Isaac Lab (the play video). It has not been through MuJoCo sim2sim or on hardware.
- 0 to 0.3 kg was added to each forearm during training, so a light held object is in distribution; more is not.
- The ONNX batch dimension is fixed at 1.
