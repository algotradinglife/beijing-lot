"""Read-only storage contract checks. Paths are explicit; no import side effects."""
import json
import os
from pathlib import Path, PurePosixPath


def confined_path(root, relative):
    """Return a resolved path within root; reject absolute, traversal and escaped links.

    Inputs are a root path and nonempty POSIX relative string. Raises ValueError
    for invalid paths. Does not create files or require the target to exist.
    """
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"Invalid relative path: {relative!r}")
    part = PurePosixPath(relative)
    if part.is_absolute() or ".." in part.parts or str(part) == ".":
        raise ValueError(f"Unsafe relative path: {relative!r}")
    root = Path(root).resolve()
    path = root.joinpath(*part.parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes data root: {relative}")
    return path


def check_layout(contract_path):
    """Validate mount, directories and declared current-reference paths, read-only.

    Takes a JSON contract path; returns a JSON-compatible receipt with checked
    paths. Raises ValueError/OSError/KeyError on invalid, missing or inaccessible
    inputs. No fallback, writes, hash/content validation or collection occurs.
    """
    contract = json.loads(Path(contract_path).read_text())
    if contract['version'] != 1:
        raise ValueError('Unsupported storage contract version')
    mount = Path(contract['mountpoint'])
    root = Path(contract['data_root'])
    if not mount.is_absolute() or not root.is_absolute():
        raise ValueError('Mount and data root must be absolute')
    if not os.path.ismount(mount):
        raise ValueError(f'External disk is not mounted: {mount}')
    if mount.is_symlink() or root.is_symlink() or not root.resolve().is_relative_to(mount.resolve()):
        raise ValueError('Data root must remain on the declared mount')
    checked = []
    for relative in contract['directories']:
        path = confined_path(root, relative)
        if not path.is_dir():
            raise ValueError(f'Missing data directory: {relative}')
        checked.append(relative)
    for name, fields in contract['references'].items():
        reference = json.loads(confined_path(root, name).read_text())
        for field, rule in fields.items():
            prefix = rule["prefix"]
            if rule["type"] not in {"file", "directory"}:
                raise ValueError(f"Invalid reference type: {name}:{field}")
            value = reference
            for key in field.split('.'):
                value = value[key]
            path = confined_path(root, value)
            if not path.is_relative_to(confined_path(root, prefix)):
                raise ValueError(f'{name}:{field} is outside {prefix}')
            valid_type = path.is_file() if rule["type"] == "file" else path.is_dir()
            if not valid_type:
                raise ValueError(f'Missing or wrong reference type: {name}:{field}: {value}')
            checked.append(value)
    return {'status': 'PASS', 'data_root': str(root), 'checked_paths': checked,
            'scope': 'mount, directory and declared current-reference paths only'}
