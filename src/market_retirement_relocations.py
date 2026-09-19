"""Resolve frozen relocation aliases for retirement planning; never delete files."""
from copy import deepcopy
from pathlib import Path


def bind_relocated_capture_aliases(captures, mappings, *, original_root, data_root):
    """Return copied capture records with explicitly mapped response aliases.

    ``mappings`` is an already hash-verified original absolute path → persistent
    absolute path map. Relative capture paths are relative to ``original_root``.
    Only content-addressed JSON destinations inside markets/raw/verified-responses
    are admitted; filename digest must equal the stored source digest. Does not
    verify file bytes or authorize retirement. Caller must bind the map receipt,
    protect aliases used by every consumer, and perform normal byte/backup gates.
    Missing map entries remain unchanged; malformed mappings raise ValueError.
    Inputs and the stored capture records are never mutated.
    """
    origin = Path(original_root)
    root = Path(data_root)
    if not origin.is_absolute() or not root.is_absolute():
        raise ValueError('absolute relocation roots required')
    result = []
    for item in captures:
        if item.get('kind') != 'capture':
            raise ValueError('capture records required')
        record = deepcopy(item)
        data = record['data']
        aliases = data.get('path_aliases', [data['path']])
        if (not isinstance(aliases, list) or data['path'] not in aliases or
                any(not isinstance(p, str) or not p for p in aliases)):
            raise ValueError('invalid capture aliases')
        digest = record['source_sha256']
        if (not isinstance(digest, str) or len(digest) != 64 or
                any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('invalid source digest')
        extra = []
        for name in aliases:
            path = Path(name)
            if '..' in path.parts:
                raise ValueError('unsafe original alias')
            original = path if path.is_absolute() else origin / path
            if str(original) not in mappings:
                continue
            target = mappings[str(original)]
            expected = root / 'markets/raw/verified-responses' / (digest + '.json')
            if not isinstance(target, str) or target != str(expected):
                raise ValueError('relocated capture identity mismatch')
            extra.append(str(expected.relative_to(root)))
        data['path_aliases'] = list(dict.fromkeys([*aliases, *extra]))
        result.append(record)
    return result


def protect_relocated_paths(protected_paths, mappings, *, original_root, data_root, captures=()):
    """Expand live old-path references to frozen persistent destinations.

    Returns original references plus mapped destinations, without removing any
    protection, including every alias of a capture with a protected alias.
    No filesystem access. Caller hash-verifies the mapping and keeps
    it frozen through retirement. Paths with traversal or destinations outside
    the declared data root fail; unmapped references remain protected verbatim.
    """
    origin, root = Path(original_root), Path(data_root)
    if not origin.is_absolute() or not root.is_absolute():
        raise ValueError('absolute relocation roots required')
    protected = set(protected_paths)
    bound = bind_relocated_capture_aliases(
        captures, mappings, original_root=origin, data_root=root)
    # Compare absolute and relative spellings, then propagate to all aliases of
    # that exact source. A relocation map need not list every historical alias.
    canonical = {str(Path(p) if Path(p).is_absolute() else origin / p)
                 for p in protected if isinstance(p, str)}
    for record in bound:
        aliases = record['data']['path_aliases']
        names = set(aliases)
        names.update(str(Path(p) if Path(p).is_absolute() else origin / p) for p in aliases)
        names.update(str(root / p) for p in aliases if p.startswith('markets/raw/verified-responses/'))
        if names.intersection(protected) or names.intersection(canonical):
            protected.update(names)
    for name in tuple(protected):
        if not isinstance(name, str) or not name or '..' in Path(name).parts:
            raise ValueError('unsafe protected path')
        path = Path(name)
        source = str(path if path.is_absolute() else origin / path)
        if source not in mappings:
            continue
        target = mappings[source]
        if (not isinstance(target, str) or not Path(target).is_absolute() or
                '..' in Path(target).parts or not Path(target).is_relative_to(root)):
            raise ValueError('unsafe relocation destination')
        protected.add(target)
    return protected
