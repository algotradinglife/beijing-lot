import hashlib
import io
import json
import tarfile
import pytest
from src.market_sqlite_sources import read_archived_market_sources


def test_archived_paths_are_bound_to_receipts_and_content(tmp_path):
    archive=tmp_path/'source.tar'
    body=b'{"url":"https://example.com"}'
    with tarfile.open(archive,'w') as out:
        info=tarfile.TarInfo('capture/a.json');info.size=len(body)
        out.addfile(info,io.BytesIO(body))
    receipt=tmp_path/'receipt.json'
    receipt.write_text(json.dumps(dict(schema='beijing_lot_archive_receipt_v1',
        source='/old/worktree/data/raw/capture',archive=archive.name,
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))
    sources={'data/raw/capture/a.json':hashlib.sha256(body).hexdigest()}
    assert read_archived_market_sources(tmp_path,sources,[receipt.name])=={'data/raw/capture/a.json':body}
    with pytest.raises(ValueError,match='one archive mapping'):
        read_archived_market_sources(tmp_path,sources,[])
    assert read_archived_market_sources(tmp_path,sources,[receipt.name,receipt.name])=={'data/raw/capture/a.json':body}
    with pytest.raises(ValueError,match='source hash'):
        read_archived_market_sources(tmp_path,{'data/raw/capture/a.json':'0'*64},[receipt.name])
    with pytest.raises(ValueError,match='unsafe'):
        read_archived_market_sources(tmp_path,{'../x':'0'*64},[receipt.name])


def test_verified_retained_receipt_format(tmp_path):
    archive=tmp_path/'source.tar'
    body=b'{}'
    with tarfile.open(archive,'w') as out:
        info=tarfile.TarInfo('capture/a.json');info.size=len(body)
        out.addfile(info,io.BytesIO(body))
    receipt=tmp_path/'receipt.json'
    receipt.write_text(json.dumps(dict(state='ARCHIVE_VERIFIED_SOURCE_RETAINED',
        source='/old/data/raw/capture',archive=archive.name,
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))
    sources={'data/raw/capture/a.json':hashlib.sha256(body).hexdigest()}
    assert read_archived_market_sources(tmp_path,sources,[receipt.name])['data/raw/capture/a.json']==body


def test_derived_catalog_and_conflicting_mapping(tmp_path):
    body=b'historical evidence'
    archive=tmp_path/'derived.tar'
    with tarfile.open(archive,'w') as out:
        info=tarfile.TarInfo('batch/evidence.txt');info.size=len(body)
        out.addfile(info,io.BytesIO(body))
    entry=dict(state='ARCHIVE_VERIFIED_SOURCE_REMOVED',source='/old/data/derived/batch',
               archive=archive.name,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    catalog=tmp_path/'catalog.json'
    catalog.write_text(json.dumps(dict(status='ARCHIVE_VERIFIED_SOURCE_REMOVED',entries=[entry])))
    sources={'data/derived/batch/evidence.txt':hashlib.sha256(body).hexdigest()}
    assert read_archived_market_sources(tmp_path,sources,[catalog.name])=={'data/derived/batch/evidence.txt':body}
    receipt=tmp_path/'receipt.json'
    receipt.write_text(json.dumps(dict(entry,schema='beijing_lot_archive_receipt_v1')))
    assert read_archived_market_sources(tmp_path,sources,[catalog.name,receipt.name])=={'data/derived/batch/evidence.txt':body}
    receipt.write_text(json.dumps(dict(entry,schema='beijing_lot_archive_receipt_v1',archive='other.tar')))
    with pytest.raises(ValueError,match='one archive mapping'):
        read_archived_market_sources(tmp_path,sources,[catalog.name,receipt.name])
    entry['state']='UNVERIFIED'
    catalog.write_text(json.dumps(dict(status='ARCHIVE_VERIFIED_SOURCE_REMOVED',entries=[entry])))
    with pytest.raises(ValueError,match='unsupported derived archive catalog'):
        read_archived_market_sources(tmp_path,sources,[catalog.name])
