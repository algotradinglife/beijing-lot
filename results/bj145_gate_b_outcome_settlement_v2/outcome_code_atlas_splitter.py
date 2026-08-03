#!/usr/bin/env python3
"""Split the audited #145 code atlas into GitHub-safe immutable CSV parts.

The logical dataset remains one configuration-sorted CSV.  Parts are cut only
between complete 2,187-code configurations, have deterministic gzip headers,
and are indexed by a manifest-bound JSON control file.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path


EXPECTED_CONFIGS = 2_892
EXPECTED_CODES = 2_187
EXPECTED_ROWS = EXPECTED_CONFIGS * EXPECTED_CODES
CONFIG_FIELDS = (
    "arm_id",
    "weight_source",
    "mechanism",
    "sampling_role",
    "cap",
    "M",
    "seed",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--part-count", type=int, default=8)
    args = parser.parse_args()
    if args.part_count < 2:
        raise SystemExit("part-count must be at least two")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    names = [
        f"outcome_code_frequency.part-{index + 1:02d}-of-{args.part_count:02d}.csv.gz"
        for index in range(args.part_count)
    ]
    if any((args.output_directory / name).exists() for name in names):
        raise RuntimeError("refusing to overwrite an existing atlas part")

    raw_handle = gzip.open(args.input, "rt", newline="", encoding="utf-8")
    reader = csv.DictReader(raw_handle)
    fields = tuple(reader.fieldnames or ())
    if not fields:
        raise RuntimeError("missing atlas header")

    part_index = -1
    raw_output = zipped = text = writer = None
    parts: list[dict[str, object]] = []
    current_key = None
    config_index = -1
    config_rows = row_count = part_rows = part_configs = 0
    part_first = part_last = None

    def close_part() -> None:
        nonlocal \
            raw_output, \
            zipped, \
            text, \
            writer, \
            part_rows, \
            part_configs, \
            part_first, \
            part_last
        if text is None or zipped is None or raw_output is None:
            return
        text.flush()
        text.detach()
        zipped.close()
        raw_output.close()
        path = args.output_directory / names[part_index]
        parts.append(
            {
                "file": path.name,
                "rows": part_rows,
                "configurations": part_configs,
                "first_configuration": list(part_first or ()),
                "last_configuration": list(part_last or ()),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        )
        raw_output = zipped = text = writer = None
        part_rows = part_configs = 0
        part_first = part_last = None

    def open_part(index: int) -> None:
        nonlocal raw_output, zipped, text, writer
        path = args.output_directory / names[index]
        raw_output = path.open("wb")
        zipped = gzip.GzipFile(
            filename="", mode="wb", fileobj=raw_output, compresslevel=9, mtime=0
        )
        text = io.TextIOWrapper(zipped, newline="", encoding="utf-8")
        writer = csv.DictWriter(
            text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()

    try:
        for row in reader:
            key = tuple(row[field] for field in CONFIG_FIELDS)
            if key != current_key:
                if current_key is not None and config_rows != EXPECTED_CODES:
                    raise RuntimeError(
                        f"configuration row drift: {current_key}: {config_rows}"
                    )
                config_index += 1
                config_rows = 0
                target_part = min(
                    args.part_count - 1,
                    config_index // math.ceil(EXPECTED_CONFIGS / args.part_count),
                )
                if target_part != part_index:
                    close_part()
                    part_index = target_part
                    open_part(part_index)
                part_configs += 1
                part_first = part_first or key
                part_last = key
                current_key = key
            assert writer is not None
            writer.writerow(row)
            config_rows += 1
            part_rows += 1
            row_count += 1
        if current_key is not None and config_rows != EXPECTED_CODES:
            raise RuntimeError(f"configuration row drift: {current_key}: {config_rows}")
        close_part()
    finally:
        raw_handle.close()
        if text is not None:
            close_part()

    if (
        row_count != EXPECTED_ROWS
        or config_index + 1 != EXPECTED_CONFIGS
        or len(parts) != args.part_count
    ):
        raise RuntimeError(
            f"split denominator drift: rows={row_count}, configs={config_index + 1}, parts={len(parts)}"
        )
    if (
        sum(int(part["rows"]) for part in parts) != EXPECTED_ROWS
        or sum(int(part["configurations"]) for part in parts) != EXPECTED_CONFIGS
    ):
        raise RuntimeError("split index conservation drift")
    index = {
        "dataset": "bj145_complete_outcome_code_allocation_marginals_v2",
        "logical_format": "one configuration-sorted CSV; concatenate parts in listed order and retain only the first header",
        "configuration_fields": list(CONFIG_FIELDS),
        "fieldnames": list(fields),
        "total_rows": EXPECTED_ROWS,
        "configuration_count": EXPECTED_CONFIGS,
        "codes_per_configuration": EXPECTED_CODES,
        "part_count": args.part_count,
        "parts": parts,
    }
    index_path = args.output_directory / "outcome_code_frequency.index.json"
    index_path.write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "index": str(index_path),
                "rows": row_count,
                "configurations": config_index + 1,
                "parts": parts,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
