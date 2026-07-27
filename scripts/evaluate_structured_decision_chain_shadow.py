"""Legacy shadow CSV/report adapter for the version-neutral v3.3.3 engine."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.structured_v333_engine import *  # noqa: E402, F403
from src.structured_v333_engine import main  # noqa: E402


if __name__ == "__main__":
    main()
