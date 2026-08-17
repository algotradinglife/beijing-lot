#!/usr/bin/env python3
"""Deterministically merge complete #145 marginal shards by frozen config."""

from __future__ import annotations

import argparse
import csv
import gzip
import heapq
import io
from collections import Counter, defaultdict
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path


CODES = {"3": 0, "1": 1, "0": 2}
EXPECTED_CONFIGS = 2892
EXPECTED_ROWS = EXPECTED_CONFIGS * 2187


def ordinal(code: str) -> int:
    value = 0
    for digit in code:
        value = value * 3 + CODES[digit]
    return value


def key(row: dict[str, str]) -> tuple[object, ...]:
    return (
        row["arm_id"],
        row["weight_source"],
        row["mechanism"],
        row["cap"],
        row["seed"],
        int(row["M"]),
        ordinal(row["ticket_code"]),
    )


def config(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        row[field]
        for field in (
            "arm_id",
            "weight_source",
            "mechanism",
            "sampling_role",
            "cap",
            "M",
            "seed",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("shards", type=Path, nargs="+")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[tuple[str, ...]] = Counter()
    target = defaultdict(Decimal)
    realized = defaultdict(Decimal)
    delta = defaultdict(Decimal)
    actual_ids = Counter()
    identity_denominator: dict[tuple[str, ...], int] = {}
    row_count = 0
    with ExitStack() as stack:
        readers = []
        for path in args.shards:
            handle = stack.enter_context(
                gzip.open(path, "rt", newline="", encoding="utf-8")
            )
            readers.append(csv.DictReader(handle))
        first_fields = tuple(readers[0].fieldnames or ())
        if not first_fields or any(
            tuple(reader.fieldnames or ()) != first_fields for reader in readers
        ):
            raise RuntimeError("shard header drift")
        raw = stack.enter_context(args.output.open("wb"))
        zipped = gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
        )
        stack.callback(zipped.close)
        text = io.TextIOWrapper(zipped, newline="", encoding="utf-8")
        stack.callback(text.detach)
        writer = csv.DictWriter(
            text, fieldnames=first_fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        previous = None
        for row in heapq.merge(*readers, key=key):
            current = key(row)
            if previous is not None and current <= previous:
                raise RuntimeError(
                    f"non-increasing merged order: {previous} -> {current}"
                )
            previous = current
            writer.writerow(row)
            cfg = config(row)
            counts[cfg] += 1
            target[cfg] += Decimal(row["target_mass_mean"])
            realized[cfg] += Decimal(row["realized_frequency"])
            delta[cfg] += Decimal(row["frequency_delta"])
            actual_ids[cfg] += int(row["actual_outcome_identity_count"])
            identity_denominator[cfg] = int(row["identity_count"])
            row_count += 1
        text.flush()
    if (
        row_count != EXPECTED_ROWS
        or len(counts) != EXPECTED_CONFIGS
        or set(counts.values()) != {2187}
    ):
        raise RuntimeError(
            f"marginal denominator drift: rows={row_count}, configs={len(counts)}, per_config={set(counts.values())}"
        )
    tolerance = Decimal("0.00000001")
    for cfg in counts:
        if (
            abs(target[cfg] - 1) > tolerance
            or abs(realized[cfg] - 1) > tolerance
            or abs(delta[cfg]) > tolerance
        ):
            raise RuntimeError(
                f"mass conservation drift: {cfg}: {target[cfg]}, {realized[cfg]}, {delta[cfg]}"
            )
        if actual_ids[cfg] != identity_denominator[cfg]:
            raise RuntimeError(f"actual-outcome identity denominator drift: {cfg}")
    print(
        {
            "rows": row_count,
            "configs": len(counts),
            "per_config_codes": 2187,
            "mass_conservation": "PASS",
        }
    )


if __name__ == "__main__":
    main()
