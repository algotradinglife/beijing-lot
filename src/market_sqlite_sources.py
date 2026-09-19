"""Resolve retired workspace source paths using explicit archive receipts."""
import hashlib
import json
from pathlib import Path, PurePosixPath
from src.data_archive import read_archive_members


def read_archived_market_sources(data_root, sources, archive_receipts):
    """Return original bytes for missing paths, with per-file and archive hashes.

    sources maps historical relative paths to SHA256; archive_receipts is an
    explicit sequence of receipt paths. Existing files are not loaded here.
    Archived members are read in groups, never extracted. Missing or ambiguous
    mappings and unsafe paths fail. No filesystem changes or network requests.
    """
    root=Path(data_root).resolve(strict=True)
    receipts=[]
    for name in archive_receipts:
        p=(root/name).resolve(strict=True)
        if not p.is_relative_to(root):
            raise ValueError('archive receipt outside root')
        receipt=json.loads(p.read_text())
        if 'entries' in receipt:
            if (receipt.get('status') != 'ARCHIVE_VERIFIED_SOURCE_REMOVED' or
                    not isinstance(receipt['entries'], list) or
                    any(entry.get('state') != 'ARCHIVE_VERIFIED_SOURCE_REMOVED'
                        for entry in receipt['entries'])):
                raise ValueError('unsupported derived archive catalog')
            receipts.extend(receipt['entries'])
        elif not (receipt.get('schema')=='beijing_lot_archive_receipt_v1' or
                ('schema' not in receipt and receipt.get('state')=='ARCHIVE_VERIFIED_SOURCE_RETAINED')):
            raise ValueError('unsupported archive receipt')
        else:
            receipts.append(receipt)
    grouped={}
    for name,digest in sources.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe historical source path')
        direct=(root/name).resolve()
        if not direct.is_relative_to(root):
            raise ValueError('source outside root')
        if direct.exists():
            continue
        matches={}
        for receipt in receipts:
            origin=PurePosixPath(receipt['source'])
            for parent in (relative,*relative.parents):
                if str(parent)=='.':
                    continue
                if str(origin).endswith('/'+str(parent)):
                    member=str(PurePosixPath(origin.name)/relative.relative_to(parent))
                    matches[(receipt['archive'],receipt['archive_sha256'],member)]=(receipt,member)
        if len(matches)!=1:
            raise ValueError(f'expected one archive mapping: {name} ({len(matches)} found)')
        receipt,member=next(iter(matches.values()))
        grouped.setdefault((receipt['archive'],receipt['archive_sha256']),[]).append((name,member,digest))
    result={}
    for (name,digest),entries in grouped.items():
        archive=(root/name).resolve(strict=True)
        if not archive.is_relative_to(root):
            raise ValueError('archive outside root')
        content=read_archive_members(archive,[e[1] for e in entries],expected_sha256=digest)
        for original,member,expected in entries:
            body=content[member]
            if hashlib.sha256(body).hexdigest()!=expected:
                raise ValueError('archived source hash mismatch')
            result[original]=body
    return result
