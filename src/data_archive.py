"""Read immutable, hash-bound raw archives without extracting a working copy.

Requires Python 3.14 for standard-library Zstandard support. No import side effects.
"""
from __future__ import annotations

import hashlib
import re
import tarfile
from pathlib import Path, PurePosixPath


def read_archive_members(archive_path, members, *, expected_sha256):
    """Return ``{member_name: original_bytes}`` from a verified TAR archive.

    ``archive_path`` is explicit; ``members`` is a nonempty sequence of unique
    relative POSIX names. ``expected_sha256`` binds the entire archive to its
    migration receipt. Bytes retain their source encoding. This performs two
    sequential reads (hash verification, then member scan), without extraction,
    network access, or writes. Batch requests to avoid repeated archive scans.

    Raise ValueError for unsafe/duplicate names, invalid hash, hash mismatch,
    duplicate selected entries, or nonregular selected entries; KeyError for
    missing members. Filesystem and tar parsing errors propagate unchanged.
    """
    if isinstance(members, (str, bytes)):
        raise ValueError("members must be a sequence of names")
    names = list(members)
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise ValueError("nonempty member names required")
    if len(set(names)) != len(names):
        raise ValueError("duplicate requested member")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or str(path) != name or "\\" in name:
            raise ValueError("unsafe member name")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    result = {}
    with Path(archive_path).open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != expected_sha256:
            raise ValueError("archive hash mismatch")
        source.seek(0)
        with tarfile.open(fileobj=source, mode="r|*") as archive:
            for member in archive:
                if member.name not in names:
                    continue
                if member.name in result or not member.isfile():
                    raise ValueError("duplicate or nonregular selected archive member")
                with archive.extractfile(member) as content:
                    result[member.name] = content.read()
    missing = set(names) - result.keys()
    if missing:
        raise KeyError(f"archive members missing: {sorted(missing)}")
    return {name: result[name] for name in names}
