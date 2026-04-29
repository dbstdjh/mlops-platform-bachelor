from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE_ROOT = REPO_ROOT / "control-plane"
SDK_SRC_ROOT = REPO_ROOT / "sdk" / "src"

for candidate in (REPO_ROOT, CONTROL_PLANE_ROOT, SDK_SRC_ROOT):
    path = str(candidate)
    if path not in sys.path:
        sys.path.insert(0, path)
