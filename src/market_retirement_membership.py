"""Verify complete reviewed reference directory inventories, including additions."""
import hashlib
from pathlib import Path


def verify_reference_membership(data_root, inventories):
    """Compare exact matched file names and bytes with reviewed inventories.

    Each inventory contains directory (persistent relative path), glob pattern
    and members (relative names to SHA256). The final reviewer establishes scope
    coverage; this function detects additions/removals/changes within that scope.
    Caller holds writer locks. Symlinks and escaping paths are rejected. No writes.
    """
    root = Path(data_root).resolve(strict=True)
    if not isinstance(inventories, list) or not inventories:
        raise ValueError('reference membership inventories required')
    count = 0
    for inventory in inventories:
        name = Path(inventory['directory'])
        pattern = inventory['pattern']
        if name.is_absolute() or '..' in name.parts or Path(pattern).is_absolute() or '..' in Path(pattern).parts:
            raise ValueError('unsafe reference inventory scope')
        directory = root / name
        if directory.absolute() != directory.resolve(strict=True):
            raise ValueError('reference inventory symlink')
        directory.resolve().relative_to(root)
        if not isinstance(inventory['members'], dict):
            raise ValueError('reference membership map required')
        actual = {}
        for path in directory.glob(pattern):
            if path.is_symlink() or path.absolute() != path.resolve():
                raise ValueError('reference member symlink')
            if path.is_file():
                with path.open('rb') as stream:
                    actual[str(path.relative_to(directory))] = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != inventory['members']:
            raise ValueError('reference inventory membership or content changed')
        count += len(actual)
    return dict(state='REFERENCE_MEMBERSHIP_VERIFIED', inventories=len(inventories), files=count)
