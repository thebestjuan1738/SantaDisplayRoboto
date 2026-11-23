"""Add an already-recorded run's video to the committed video log (videos/).

  python tools/save_video.py runs/<dir>/trial.mp4 "short description" [--mode "..."]

The name uses the video file's own recording time. Results are read from the
trial_result.json beside it. See santabot/videos.py and CLAUDE.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from santabot.videos import save_video  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4")
    ap.add_argument("description")
    ap.add_argument("--mode", default=None, help="e.g. 'assisted', 'policy model_7999, unassisted'")
    a = ap.parse_args()
    mp4 = Path(a.mp4)
    mode = a.mode
    if mode is None:
        rj = mp4.parent / "trial_result.json"
        r = json.loads(rj.read_text(encoding="utf-8")) if rj.exists() else {}
        mode = ("assisted" if r.get("assisted") else "unassisted") + (f", {r['mode']}" if r.get("mode") else "")
    print(save_video(mp4, a.description, mode))


if __name__ == "__main__":
    main()
