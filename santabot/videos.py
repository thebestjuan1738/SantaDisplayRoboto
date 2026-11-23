"""The committed video log: videos/<YYYY-MM-DD_HHMM>_<short-description>.mp4 + videos/README.md.

`runs/` is scratch and gitignored. After a major work session, the video that
shows where things stand is copied here, under a name that says when it was
recorded and what it shows, and a row is added to videos/README.md with the
mode and results so the folder reads as a history of the project.

  python run_trial.py --policy exports/x --video --follow --save-video "short description"
  python tools/save_video.py runs/<dir>/trial.mp4 "short description"   # an existing run
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from santabot.layout import ROOT

VIDEOS = ROOT / "videos"
INDEX = VIDEOS / "README.md"
HEADER = """# Video log

One video per major work session, newest last. Name: `YYYY-MM-DD_HHMM_short-description.mp4`
(the time the video was recorded, local). Saved with `run_trial.py --save-video "..."` or
`tools/save_video.py`; see CLAUDE.md. `runs/` is scratch and is not committed.

| Video | Recorded | Mode | What it shows | Result |
|---|---|---|---|---|
"""


def slug(text: str, max_len: int = 70) -> str:
    """Lower-case, hyphenated; long descriptions are cut at a word boundary."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) > max_len:
        s = s[:max_len]
        s = s[: s.rfind("-")] if "-" in s else s
    return s or "video"


def result_summary(result: dict) -> str:
    """One cell: success, falls, and each gift's placement."""
    parts = ["success" if result.get("success") else "not yet"]
    if result.get("fell"):
        parts.append(f"fell at {result.get('fall_time', 0):.1f} s")
    for name, g in (result.get("gifts") or {}).items():
        state = "placed" if g.get("placed") else "missed"
        parts.append(f"{name.replace('_gift', '')} {state} {g.get('xy_error_m', 0) * 100:.1f} cm")
    return ", ".join(parts)


def save_video(mp4: Path, description: str, mode: str, result: dict | None = None, when: datetime | None = None) -> Path:
    """Copy `mp4` into videos/ under a dated name and append its row to the index."""
    mp4 = Path(mp4)
    when = when or datetime.fromtimestamp(mp4.stat().st_mtime)
    VIDEOS.mkdir(exist_ok=True)
    name = f"{when:%Y-%m-%d_%H%M}_{slug(description)}.mp4"
    dest = VIDEOS / name
    shutil.copy2(mp4, dest)
    if not INDEX.exists():
        INDEX.write_text(HEADER, encoding="utf-8")
    if result is None:
        rj = mp4.parent / "trial_result.json"
        result = json.loads(rj.read_text(encoding="utf-8")) if rj.exists() else {}
    row = (
        f"| [{name}]({name}) | {when:%Y-%m-%d %H:%M} | {mode} | {description.replace('|', '/')} "
        f"| {result_summary(result) if result else '-'} |\n"
    )
    with INDEX.open("a", encoding="utf-8") as fh:
        fh.write(row)
    return dest
