#!/usr/bin/env python3
"""Consolidate the persistent archive into one manifest with verification evidence.

Reads the per-tree transfer ledgers and the retention record, classifies every
tree as ``retained`` or ``reclaimed``, samples retained trees for sha256
verification (against the ledger, and against the source disk when it is still
present), and writes a single authoritative manifest.

Reclaimed trees are recorded explicitly so a later audit does not mistake a
deliberate policy decision for accidental data loss. Read-only on the archive;
writes only the manifest and its JSONL companion under ``registry/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path("/mnt/nas/Data/beijing-lot")
DEFAULT_SOURCE = Path("/run/media/drwho1985/Sandisk/data/beijing-lot")
CHUNK = 1 << 20
# Bound the hashing cost: the source is CIFS/exFAT and some retained files are
# tens of GB, so verification samples a few files per tree within a byte budget.
DEFAULT_SAMPLE_FILES = 5
DEFAULT_SAMPLE_BYTES = 2 * 1024**3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ledger_slug(name: str) -> str:
    return name.replace("/", "__")


def load_ledger(registry: Path, name: str) -> dict | None:
    path = registry / f"transfer-{ledger_slug(name)}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["_file"] = path.name
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--sample-files", type=int, default=DEFAULT_SAMPLE_FILES)
    parser.add_argument("--sample-bytes", type=int, default=DEFAULT_SAMPLE_BYTES)
    parser.add_argument("--seed", type=int, default=None, help="deterministic sampling")
    args = parser.parse_args(argv)

    root = args.root
    registry = root / "registry"
    if not registry.is_dir():
        print(f"registry is absent: {registry}", file=sys.stderr)
        return 2

    retention = json.loads((registry / "retention.json").read_text(encoding="utf-8"))
    reclaimed = {entry["path"].split("archive/", 1)[-1] for entry in retention["reclaim"]}

    # Every tree that has a transfer ledger, plus the archive's own directories.
    names = sorted(
        path.name[len("transfer-"):-len(".json")]
        for path in registry.glob("transfer-*.json")
    )
    rng = random.Random(args.seed)

    source_present = args.source.is_dir()
    trees: list[dict] = []
    sampled = matched = mismatched = unavailable = 0
    budget_per_tree = args.sample_bytes

    for slug in names:
        name = slug.replace("__", "/")
        ledger = load_ledger(registry, name)
        if ledger is None:
            continue
        retained = name not in reclaimed and (root / "archive" / name).exists()
        entry = {
            "name": name,
            "state": "retained" if retained else "reclaimed",
            "files": ledger["file_count"],
            "bytes": ledger["bytes"],
            "ledger": ledger["_file"],
            "source": ledger["source"],
        }
        if retained:
            # Deterministic sample within a byte budget.
            candidates = [f for f in ledger["files"] if f["bytes"] <= budget_per_tree]
            rng.shuffle(candidates)
            picked, spent = [], 0
            for candidate in candidates:
                if len(picked) >= args.sample_files or spent + candidate["bytes"] > budget_per_tree:
                    continue
                picked.append(candidate)
                spent += candidate["bytes"]
            checked: list[dict] = []
            for record in picked:
                destination = root / "archive" / name / record.get("destination", record["path"])
                probe = {"path": record["path"], "bytes": record["bytes"]}
                if not destination.is_file():
                    probe["nas"] = "absent"
                    unavailable += 1
                else:
                    nas_digest = sha256_file(destination)
                    probe["nas"] = "ok" if nas_digest == record["sha256"] else "mismatch"
                    sampled += 1
                    if nas_digest == record["sha256"]:
                        matched += 1
                    else:
                        mismatched += 1
                source_path = Path(ledger["source"]) / record["path"]
                if source_present and source_path.is_file():
                    probe["source"] = (
                        "ok" if sha256_file(source_path) == record["sha256"] else "mismatch"
                    )
                elif source_present:
                    probe["source"] = "absent"
                checked.append(probe)
            entry["sample"] = checked
        trees.append(entry)

    retained_trees = [t for t in trees if t["state"] == "retained"]
    reclaimed_trees = [t for t in trees if t["state"] == "reclaimed"]
    manifest = {
        "schema": "beijing_lot_archive_manifest_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "source_disk": str(args.source),
        "source_present": source_present,
        "policy": retention["policy"],
        "totals": {
            "retained_trees": len(retained_trees),
            "retained_files": sum(t["files"] for t in retained_trees),
            "retained_bytes": sum(t["bytes"] for t in retained_trees),
            "reclaimed_trees": len(reclaimed_trees),
            "reclaimed_files": sum(t["files"] for t in reclaimed_trees),
            "reclaimed_bytes": sum(t["bytes"] for t in reclaimed_trees),
        },
        "verification": {
            "method": "sha256 of sampled files against the transfer ledger"
                      + (" and the source disk" if source_present else ""),
            "sampled": sampled,
            "matched": matched,
            "mismatched": mismatched,
            "unavailable": unavailable,
        },
        "trees": trees,
    }

    out = registry / "archive-manifest.json"
    temporary = out.with_name(out.name + ".partial")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, out)

    print(f"root             : {root}")
    print(f"source disk      : {args.source} ({'present' if source_present else 'ABSENT'})")
    print(f"retained trees   : {len(retained_trees)}  "
          f"{manifest['totals']['retained_files']:,} files  "
          f"{manifest['totals']['retained_bytes']/1073741824:.2f} GB")
    print(f"reclaimed trees  : {len(reclaimed_trees)}  "
          f"{manifest['totals']['reclaimed_files']:,} files  "
          f"{manifest['totals']['reclaimed_bytes']/1073741824:.2f} GB")
    print(f"verification     : {matched} matched, {mismatched} mismatched, "
          f"{unavailable} unavailable (of {sampled} hashed)")
    print(f"manifest         : {out}")
    return 0 if mismatched == 0 and unavailable == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
