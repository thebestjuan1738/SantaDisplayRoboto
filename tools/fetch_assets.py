"""Fetch the Roboto Origin (RPO) model into vendor/rpo_description.

Pinned to the same revision as the TA's LearningRL gitman.yml, so the MuJoCo
model here is the one LearningRLsim replays policies against.

  python tools/fetch_assets.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/Roboparty/rpo_description"
REV = "37aac9ca665e92731444a1618320078e7ba21569"
DEST = Path(__file__).resolve().parent.parent / "vendor" / "rpo_description"


def main():
    if (DEST / "mjcf" / "rpo.xml").is_file():
        print(f"{DEST} already present")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_name("_rpo_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    subprocess.run(["git", "clone", "--quiet", REPO, str(tmp)], check=True)
    subprocess.run(["git", "-C", str(tmp), "checkout", "--quiet", REV], check=True)
    shutil.rmtree(tmp / ".git", ignore_errors=True)
    tmp.rename(DEST)
    print(f"fetched {REPO}@{REV[:10]} -> {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
