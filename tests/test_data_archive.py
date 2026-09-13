import hashlib
import io
import tarfile

import pytest

from src.data_archive import read_archive_members


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / "raw.tar.zst"
    with tarfile.open(path, "w:zst") as out:
        for name, content in [("batch/raw.json", b"\xff\xfe\x00\x01"), ("batch/empty", b"")]:
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            out.addfile(entry, io.BytesIO(content))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_original_bytes_order_empty_and_no_extraction(archive):
    path, digest = archive
    result = read_archive_members(path, ["batch/empty", "batch/raw.json"], expected_sha256=digest)
    assert list(result) == ["batch/empty", "batch/raw.json"]
    assert result == {"batch/empty": b"", "batch/raw.json": b"\xff\xfe\x00\x01"}
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("names", [[], "batch/raw.json", ["../x"], ["/x"], ["a/./b"], ["a\\b"], ["x", "x"], [None]])
def test_invalid_member_requests(archive, names):
    path, digest = archive
    with pytest.raises(ValueError):
        read_archive_members(path, names, expected_sha256=digest)


def test_hash_and_missing_member_fail_closed(archive):
    path, digest = archive
    for expected in [None, "bad", "0" * 64]:
        with pytest.raises(ValueError):
            read_archive_members(path, ["batch/raw.json"], expected_sha256=expected)
    with pytest.raises(KeyError):
        read_archive_members(path, ["absent"], expected_sha256=digest)


@pytest.mark.parametrize("nonregular", [False, True])
def test_duplicate_or_link_member_rejected(tmp_path, nonregular):
    path = tmp_path / "bad.tar"
    with tarfile.open(path, "w") as out:
        entry = tarfile.TarInfo("item")
        if nonregular:
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/etc/passwd"
            out.addfile(entry)
        else:
            out.addfile(entry, io.BytesIO(b""))
            out.addfile(entry, io.BytesIO(b""))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        read_archive_members(path, ["item"], expected_sha256=digest)
