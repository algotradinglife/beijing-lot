"""Validate explicit settlement output locations before any database writes."""
from pathlib import Path


def validate_settlement_storage(data_root, paths, *, mountpoint=None):
    """Return resolved output Paths under an existing data root.

    If mountpoint is supplied, require a mounted filesystem containing the root.
    Refuse missing roots, symlink escapes and duplicate destinations. No writes.
    Input evidence may live elsewhere; paths contains only database destinations.
    """
    root = Path(data_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Data root must be an existing directory')
    if mountpoint is not None:
        mount = Path(mountpoint).resolve(strict=True)
        if not mount.is_mount() or not root.is_relative_to(mount):
            raise ValueError('Expected storage mount is unavailable or outside data root')
    outputs = [Path(p).resolve() for p in paths]
    if not outputs or len(set(outputs)) != len(outputs):
        raise ValueError('Distinct output paths required')
    for output in outputs:
        if output == root or not output.is_relative_to(root):
            raise ValueError('Output escapes data root')
    return outputs
