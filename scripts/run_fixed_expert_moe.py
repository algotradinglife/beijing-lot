#!/usr/bin/env python3
"""Run Issue #332 fixed-expert causal MoE."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fixed_expert_moe import build_package


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("BEIJING_LOT_RUNTIME_ROOT", str(root))
    print(json.dumps(build_package(root), indent=2, sort_keys=True))
