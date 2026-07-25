#!/usr/bin/env python3
"""Render append-only BJ-FREEZE-REVIEW-001 HTML/PDF/CSV artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.freeze_review import FreezeReviewError, render_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-package", type=Path, required=True)
    parser.add_argument(
        "--source-reference",
        help="Repository-relative portable reference for the source package.",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--font-file", type=Path, required=True)
    parser.add_argument(
        "--font-reference",
        help="Repository-relative portable reference for the PDF font.",
    )
    parser.add_argument(
        "--generated-at",
        help="Timezone-aware ISO timestamp; recorded for reproducible evidence.",
    )
    args = parser.parse_args()
    try:
        generated_at = (
            datetime.fromisoformat(args.generated_at) if args.generated_at else None
        )
        if generated_at is not None and generated_at.tzinfo is None:
            raise FreezeReviewError("--generated-at must be timezone-aware")
        result = render_bundle(
            source_package=args.source_package,
            output_root=args.output_root,
            font_file=args.font_file,
            generated_at=generated_at,
            source_reference=args.source_reference,
            font_reference=args.font_reference,
        )
    except (FreezeReviewError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
