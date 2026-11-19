"""Offscreen rendering: video, GIF and stills, with a caption overlay."""

from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

VIEWS = {
    # name: (lookat, distance, azimuth, elevation)
    "overview": ((0.0, 0.0, 0.75), 3.1, 90.0, -22.0),
    "three_quarter": ((-0.1, -0.1, 0.8), 2.7, 120.0, -22.0),
    "grasp_left": ((-0.4, 0.0, 0.85), 1.4, 125.0, -30.0),
    "grasp_right": ((0.4, 0.0, 0.85), 1.4, 55.0, -30.0),
    "top": ((0.0, 0.0, 0.5), 3.0, 90.0, -80.0),
    "follow": ((0.0, 0.0, 0.85), 1.9, 125.0, -20.0),  # with track=True: follows the pelvis
}


class Recorder:
    def __init__(self, model, width=960, height=540, view="three_quarter", caption=True, label="", track=False):
        model.vis.global_.offwidth = max(model.vis.global_.offwidth, width)
        model.vis.global_.offheight = max(model.vis.global_.offheight, height)
        self.r = mujoco.Renderer(model, height=height, width=width)
        self.cam = mujoco.MjvCamera()
        self.opt = mujoco.MjvOption()
        self.opt.geomgroup[:] = 1
        self.set_view(view)
        self.frames: list[np.ndarray] = []
        self.caption = caption
        self.label = label
        # follow the robot: keep the view's angles and distance, slide the look-at point
        self.track = track
        self._look = None
        try:
            self.font = ImageFont.truetype("arial.ttf", 22)
            self.small = ImageFont.truetype("arial.ttf", 16)
        except OSError:
            self.font = self.small = ImageFont.load_default()

    def set_view(self, view):
        lookat, dist, az, el = VIEWS[view] if isinstance(view, str) else view
        self.cam.lookat[:] = lookat
        self.cam.distance, self.cam.azimuth, self.cam.elevation = dist, az, el

    def _add_spheres(self, spheres):
        """Draw extra marker spheres into the scene: [(pos, radius, rgba), ...]."""
        scn = self.r.scene
        for pos, radius, rgba in spheres:
            if scn.ngeom >= scn.maxgeom:
                break
            mujoco.mjv_initGeom(
                scn.geoms[scn.ngeom],
                mujoco.mjtGeom.mjGEOM_SPHERE,
                np.array([radius, 0.0, 0.0]),
                np.asarray(pos, dtype=np.float64),
                np.eye(3).flatten(),
                np.asarray(rgba, dtype=np.float32),
            )
            scn.ngeom += 1

    def grab(self, data, text: str = "", spheres=(), legend: bool = False) -> np.ndarray:
        self.r.update_scene(data, self.cam, self.opt)
        self._add_spheres(spheres)
        img = self.r.render()
        if self.caption and (text or self.label or legend):
            im = Image.fromarray(img)
            dr = ImageDraw.Draw(im, "RGBA")
            dr.rectangle([0, 0, im.width, 36], fill=(15, 20, 30, 170))
            dr.text((14, 6), text, fill=(255, 255, 255, 255), font=self.font)
            if self.label:
                w = dr.textlength(self.label, font=self.small)
                dr.text((im.width - w - 14, 10), self.label, fill=(255, 210, 90, 255), font=self.small)
            if legend:
                x0, y0 = 14, im.height - 62
                dr.rectangle([x0 - 8, y0 - 8, x0 + 355, y0 + 52], fill=(15, 20, 30, 150))
                for k, (rgb, words) in enumerate(
                    (((25, 215, 65), "wrist target sent to the policy (hand_track)"), ((40, 90, 255), "actual wrist, where it misses the target"))
                ):
                    y = y0 + 24 * k
                    dr.ellipse([x0, y + 3, x0 + 13, y + 16], fill=rgb + (255,))
                    dr.text((x0 + 22, y), words, fill=(255, 255, 255, 255), font=self.small)
            img = np.asarray(im)
        return img

    @staticmethod
    def wrist_spheres(trial):
        """Green: the hand_track wrist targets (pelvis frame -> world). Blue: the actual wrists."""
        hands = getattr(trial, "hands", None)
        if hands is None or hands[0] < 0.5:
            return []
        pos = trial.view.base_pos_w
        rot = trial.view.base_rot_w
        out = []
        for k, side in enumerate(("left", "right")):
            target = pos + rot @ hands[2 + 3 * k : 5 + 3 * k]
            actual = trial.data.site_xpos[trial.model.site(f"{side}_wrist").id]
            out.append((target, 0.032, (0.10, 0.85, 0.25, 1.0)))
            # the actual wrist only where it visibly misses its target (e.g. blocked by the gift)
            if np.linalg.norm(actual - target) > 0.015:
                out.append((actual, 0.026, (0.15, 0.35, 1.0, 1.0)))
        return out

    def _follow(self, trial):
        base = trial.view.base_pos_w
        goal = np.array([base[0], base[1] + 0.15, 0.85])
        self._look = goal if self._look is None else self._look + 0.08 * (goal - self._look)
        self.cam.lookat[:] = self._look

    def on_frame(self, trial, cmd):
        if self.track:
            self._follow(trial)
        holding = f"  |  holding {cmd.holding.replace('_', ' ')}" if cmd.holding else ""
        spheres = self.wrist_spheres(trial)
        self.frames.append(
            self.grab(trial.data, f"t={trial.data.time:5.1f}s  {cmd.phase}{holding}", spheres, legend=bool(spheres))
        )

    def save_mp4(self, path: Path, fps=30):
        import imageio.v2 as imageio

        with imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8) as w:
            for f in self.frames:
                w.append_data(f)

    def save_gif(self, path: Path, fps=12, every=8, width=560, colors=128):
        frames = []
        for f in self.frames[::every]:
            im = Image.fromarray(f)
            im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
            # octree quantization keeps small saturated markers (green/blue) instead of graying them
            frames.append(im.quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE))
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
