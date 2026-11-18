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
}


class Recorder:
    def __init__(self, model, width=960, height=540, view="three_quarter", caption=True, label=""):
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
        try:
            self.font = ImageFont.truetype("arial.ttf", 22)
            self.small = ImageFont.truetype("arial.ttf", 16)
        except OSError:
            self.font = self.small = ImageFont.load_default()

    def set_view(self, view):
        lookat, dist, az, el = VIEWS[view] if isinstance(view, str) else view
        self.cam.lookat[:] = lookat
        self.cam.distance, self.cam.azimuth, self.cam.elevation = dist, az, el

    def grab(self, data, text: str = "") -> np.ndarray:
        self.r.update_scene(data, self.cam, self.opt)
        img = self.r.render()
        if self.caption and (text or self.label):
            im = Image.fromarray(img)
            dr = ImageDraw.Draw(im, "RGBA")
            dr.rectangle([0, 0, im.width, 36], fill=(15, 20, 30, 170))
            dr.text((14, 6), text, fill=(255, 255, 255, 255), font=self.font)
            if self.label:
                w = dr.textlength(self.label, font=self.small)
                dr.text((im.width - w - 14, 10), self.label, fill=(255, 210, 90, 255), font=self.small)
            img = np.asarray(im)
        return img

    def on_frame(self, trial, cmd):
        holding = f"  |  holding {cmd.holding.replace('_', ' ')}" if cmd.holding else ""
        self.frames.append(self.grab(trial.data, f"t={trial.data.time:5.1f}s  {cmd.phase}{holding}"))

    def save_mp4(self, path: Path, fps=30):
        import imageio.v2 as imageio

        with imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8) as w:
            for f in self.frames:
                w.append_data(f)

    def save_gif(self, path: Path, fps=12, every=8, width=560, colors=96):
        frames = []
        for f in self.frames[::every]:
            im = Image.fromarray(f)
            im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
            frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=colors))
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
