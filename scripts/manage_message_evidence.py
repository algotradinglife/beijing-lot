#!/usr/bin/env python3
"""Manage the append-only, timestamped pre-kickoff message evidence ledger."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.message_evidence import (  # noqa: E402
    FACT_KINDS,
    MAX_RAW_CAPTURE_BYTES,
    PROVENANCE_TIERS,
    MessageEvidenceError,
    MessageEvidenceLedger,
    canonical_json,
)


def _record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MessageEvidenceError(f"cannot read JSON record {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MessageEvidenceError(f"JSON record must be an object: {path}")
    return value


def _atomic_json(path: Path, value: object, *, database: Path) -> None:
    database_path = database.resolve(strict=False)
    protected_paths = {
        database_path,
        *(Path(f"{database_path}{suffix}") for suffix in ("-wal", "-shm", "-journal")),
    }
    if path.resolve(strict=False) in protected_paths:
        raise MessageEvidenceError("output path cannot replace the ledger database")
    path.parent.mkdir(parents=True, exist_ok=True)
    parent = path.parent.resolve(strict=True)
    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    temporary_name = f".{path.name}.{secrets.token_hex(8)}.tmp"
    try:
        protected_inodes: set[tuple[int, int]] = set()
        for protected_path in protected_paths:
            try:
                protected_stat = os.stat(protected_path, follow_symlinks=True)
            except FileNotFoundError:
                continue
            protected_inodes.add((protected_stat.st_dev, protected_stat.st_ino))
        try:
            output_stat = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=True)
        except FileNotFoundError:
            output_stat = None
        if (
            output_stat is not None
            and (
                output_stat.st_dev,
                output_stat.st_ino,
            )
            in protected_inodes
        ):
            raise MessageEvidenceError("output path cannot alias the ledger database")
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def _add_record_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    help_text: str,
) -> None:
    command = subparsers.add_parser(name, help=help_text)
    command.add_argument("--record", type=Path, required=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--readonly-replica",
        action="store_true",
        help="declare an immutable replica; permits export without a writer lock",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="initialize a new ledger")

    _add_record_command(commands, "register-source", "append a source registry row")
    _add_record_command(commands, "register-entity", "append an entity registry row")
    _add_record_command(commands, "register-alias", "append an entity alias row")
    _add_record_command(commands, "register-match", "append an issue/match binding")

    capture = commands.add_parser("capture", help="append immutable raw source bytes")
    capture.add_argument("--record", type=Path, required=True)
    capture.add_argument("--raw", type=Path, required=True)

    _add_record_command(commands, "fact", "append a normalized evidence fact")
    _add_record_command(commands, "relation", "append a correction/conflict relation")
    _add_record_command(commands, "missing", "append an explicit missingness record")
    _add_record_command(
        commands,
        "observation",
        "append an audited collection-completeness observation",
    )

    export = commands.add_parser("export", help="write a deterministic as-of export")
    export.add_argument("--cutoff", required=True)
    export.add_argument("--issue")
    export.add_argument("--match-idx", type=int)
    export.add_argument("--output", type=Path, required=True)

    coverage = commands.add_parser("coverage", help="write coverage/freshness metrics")
    coverage.add_argument("--cutoff", required=True)
    coverage.add_argument("--issue")
    coverage.add_argument(
        "--required-kind",
        action="append",
        choices=FACT_KINDS,
        required=True,
        dest="required_kinds",
    )
    coverage.add_argument("--max-age-seconds", type=int, required=True)
    coverage.add_argument(
        "--allowed-tier",
        action="append",
        choices=PROVENANCE_TIERS,
        dest="allowed_tiers",
        help="repeat to restrict eligible provenance; default permits all tiers",
    )
    coverage.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    ledger = MessageEvidenceLedger(
        args.db,
        readonly_replica=args.readonly_replica,
    )
    if args.command == "init":
        ledger.initialize()
        return {"status": "initialized", "database": str(args.db)}

    record_methods: dict[str, Callable[..., str]] = {
        "register-source": ledger.register_source,
        "register-entity": ledger.register_entity,
        "register-alias": ledger.register_alias,
        "register-match": ledger.register_match,
        "fact": ledger.append_fact,
        "relation": ledger.append_relation,
        "missing": ledger.append_missingness,
        "observation": ledger.append_collection_observation,
    }
    if args.command in record_methods:
        try:
            identifier = record_methods[args.command](**_record(args.record))
        except TypeError as exc:
            raise MessageEvidenceError(
                f"invalid fields for {args.command}: {exc}"
            ) from exc
        return {"status": "appended", "identifier": identifier}
    if args.command == "capture":
        raw_fd: int | None = None
        try:
            raw_fd = os.open(
                args.raw,
                os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            )
            file_stat = os.fstat(raw_fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise MessageEvidenceError("raw capture must be a regular file")
            if file_stat.st_size > MAX_RAW_CAPTURE_BYTES:
                raise MessageEvidenceError(
                    f"raw capture exceeds {MAX_RAW_CAPTURE_BYTES} bytes"
                )
            with os.fdopen(raw_fd, "rb") as handle:
                raw_fd = None
                raw_bytes = handle.read(MAX_RAW_CAPTURE_BYTES + 1)
        except OSError as exc:
            raise MessageEvidenceError(
                f"cannot read raw capture {args.raw}: {exc}"
            ) from exc
        finally:
            if raw_fd is not None:
                os.close(raw_fd)
        if len(raw_bytes) > MAX_RAW_CAPTURE_BYTES:
            raise MessageEvidenceError(
                f"raw capture exceeds {MAX_RAW_CAPTURE_BYTES} bytes"
            )
        try:
            identifier = ledger.append_capture(
                raw_bytes=raw_bytes,
                **_record(args.record),
            )
        except TypeError as exc:
            raise MessageEvidenceError(f"invalid fields for capture: {exc}") from exc
        return {
            "status": "appended",
            "identifier": identifier,
            "raw_path": str(args.raw),
        }
    if args.command == "export":
        payload = ledger.export_as_of(
            cutoff=args.cutoff,
            issue=args.issue,
            match_idx=args.match_idx,
        )
        _atomic_json(args.output, payload, database=args.db)
        return {
            "status": "exported",
            "output": str(args.output),
            "counts": payload["counts"],
        }
    if args.command == "coverage":
        payload = ledger.coverage_report(
            cutoff=args.cutoff,
            issue=args.issue,
            required_fact_kinds=args.required_kinds,
            max_age_seconds=args.max_age_seconds,
            allowed_provenance_tiers=args.allowed_tiers or PROVENANCE_TIERS,
        )
        _atomic_json(args.output, payload, database=args.db)
        return {
            "status": "reported",
            "output": str(args.output),
            "issues": payload["issues"],
        }
    raise MessageEvidenceError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parse_args(argv))
    except (MessageEvidenceError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
