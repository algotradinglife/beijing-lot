#!/usr/bin/env python3
"""Build the tracked, deterministic CJK font subset for BJ-FREEZE-REVIEW-001."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

OPENTYPE_UNIX_EPOCH = 2_082_844_800


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-font", type=Path, required=True)
    text_input = parser.add_mutually_exclusive_group(required=True)
    text_input.add_argument("--text-file", type=Path)
    text_input.add_argument(
        "--html-root",
        type=Path,
        help="Read every *.html below this generated evidence directory.",
    )
    parser.add_argument("--source-license", type=Path, required=True)
    parser.add_argument("--output-font", type=Path, required=True)
    parser.add_argument("--output-license", type=Path, required=True)
    parser.add_argument("--font-reference", required=True)
    parser.add_argument("--upstream-font-url", required=True)
    parser.add_argument("--upstream-license-url", required=True)
    parser.add_argument("--upstream-release", required=True)
    args = parser.parse_args()

    text_paths = (
        [args.text_file]
        if args.text_file is not None
        else sorted(args.html_root.rglob("*.html"))
    )
    if not text_paths:
        parser.error("font subset input contains no text files")
    text = "\n".join(path.read_text(encoding="utf-8") for path in text_paths)
    codepoints = sorted({ord(character) for character in text if ord(character) >= 32})
    options = subset.Options()
    options.recalc_timestamp = False
    options.retain_gids = False
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    font = TTFont(args.source_font, recalcTimestamp=False)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    if "head" in font:
        font["head"].created = OPENTYPE_UNIX_EPOCH
        font["head"].modified = OPENTYPE_UNIX_EPOCH
    args.output_font.parent.mkdir(parents=True, exist_ok=True)
    font.save(args.output_font, reorderTables=True)
    shutil.copyfile(args.source_license, args.output_license)

    provenance = {
        "schema_version": "freeze_review_font_subset_v1",
        "font_reference": args.font_reference,
        "font_sha256": file_hash(args.output_font),
        "license_sha256": file_hash(args.output_license),
        "source_font_sha256": file_hash(args.source_font),
        "source_license_sha256": file_hash(args.source_license),
        "upstream_font_url": args.upstream_font_url,
        "upstream_license_url": args.upstream_license_url,
        "upstream_release": args.upstream_release,
        "codepoint_count": len(codepoints),
        "codepoints_sha256": hashlib.sha256(
            ",".join(f"{value:06X}" for value in codepoints).encode("ascii")
        ).hexdigest(),
        "fonttools_version": __import__("fontTools").__version__,
        "subset_options": {
            "recalc_timestamp": False,
            "retain_gids": False,
            "name_IDs": ["*"],
            "name_legacy": True,
            "name_languages": ["*"],
            "head_created": OPENTYPE_UNIX_EPOCH,
            "head_modified": OPENTYPE_UNIX_EPOCH,
        },
    }
    provenance_path = args.output_font.with_suffix(".provenance.json")
    provenance_path.write_bytes(canonical(provenance) + b"\n")
    print(canonical(provenance).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
