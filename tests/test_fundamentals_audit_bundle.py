import hashlib
import json
from pathlib import Path
import pytest
from src.fundamentals_audit_bundle import publish_fundamentals_audit
from beidan_backend import versioning
from beidan_backend.catalog.paths import LocationError


@pytest.fixture
def inputs(tmp_path):
    nas = tmp_path / "nas"
    hot = tmp_path / "hot"
    nas.mkdir()
    hot.mkdir()
    source = hot / "source.txt"
    source.write_bytes(b"original evidence\x00\n")
    files = {"data/source.txt": {"path": str(source), "sha256":
        hashlib.sha256(source.read_bytes()).hexdigest()}}
    return dict(files=files,issue="26098",label="20261018T150000000000Z",
        receipt={"historical_admission":False,"base_dataset_modified":False},
        environ={"BEIDAN_PARQUET_ROOT":str(nas),"BEIDAN_HOT_ROOT":str(hot)})


def test_publish_readback_and_repeat_are_identical(inputs):
    first = publish_fundamentals_audit(**inputs)
    second = publish_fundamentals_audit(**inputs)
    assert first["publication"]["status"] == "published"
    assert second["publication"]["status"] == "unchanged"
    assert first["asset_manifest_sha256"] == second["asset_manifest_sha256"]
    directory = Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"]) / first["relative"]
    manifest = json.loads((directory / "asset-manifest.json").read_text())
    assert manifest["members"]["data/source.txt"] == inputs["files"]["data/source.txt"]["sha256"]
    assert (directory / "data/source.txt").read_bytes() == b"original evidence\x00\n"


@pytest.mark.parametrize("name",["../escape","/absolute","a/../b","a//b","a\\b","asset-manifest.json","version.json",""])
def test_unsafe_names_are_rejected(inputs,name):
    inputs["files"] = {name:next(iter(inputs["files"].values()))}
    with pytest.raises(ValueError,match="unsafe"):
        publish_fundamentals_audit(**inputs)


def test_hash_mismatch_missing_root_and_name_collision(inputs):
    item=next(iter(inputs["files"].values()))
    good=item["sha256"]
    item["sha256"]="0"*64
    with pytest.raises(ValueError,match="hash mismatch"):
        publish_fundamentals_audit(**inputs)
    item["sha256"]=good
    inputs["files"]["data"]=dict(item)
    with pytest.raises(ValueError,match="collision"):
        publish_fundamentals_audit(**inputs)
    inputs["environ"].pop("BEIDAN_PARQUET_ROOT")
    with pytest.raises(LocationError,match="not set"):
        publish_fundamentals_audit(**inputs)


def test_changed_label_rejected_and_prior_pointer_preserved(inputs):
    first=publish_fundamentals_audit(**inputs)
    base=Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"])/"reports/26098-fundamentals-final"
    before=(base/"current.json").read_bytes()
    inputs["receipt"]["different"]=True
    with pytest.raises(versioning.VersionError,match="different content"):
        publish_fundamentals_audit(**inputs)
    assert (base/"current.json").read_bytes()==before
    assert not list((base/"versions").glob("*.staging"))
    assert first["verified_members"]==1


def test_copy_failure_rolls_back_and_can_retry(inputs,monkeypatch):
    import src.fundamentals_audit_bundle as module
    original=module.shutil.copyfile
    monkeypatch.setattr(module.shutil,"copyfile",lambda *args: (_ for _ in ()).throw(OSError("disk error")))
    with pytest.raises(OSError,match="disk error"):
        publish_fundamentals_audit(**inputs)
    base=Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"])/"reports/26098-fundamentals-final"
    assert not (base/"current.json").exists()
    monkeypatch.setattr(module.shutil,"copyfile",original)
    assert publish_fundamentals_audit(**inputs)["publication"]["status"]=="published"


def test_published_corruption_is_not_a_noop(inputs):
    first=publish_fundamentals_audit(**inputs)
    directory=Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"])/first["relative"]
    (directory/"data/source.txt").write_bytes(b"corrupt")
    with pytest.raises(versioning.VersionError,match="different content"):
        publish_fundamentals_audit(**inputs)


def test_json_only_evidence_participates_in_immutable_identity(inputs):
    item=next(iter(inputs["files"].values()))
    inputs["files"]={"response.json":item}
    publish_fundamentals_audit(**inputs)
    Path(item["path"]).write_bytes(b'{"changed":true}')
    item["sha256"]=hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()
    with pytest.raises(versioning.VersionError,match="different content"):
        publish_fundamentals_audit(**inputs)


def test_changed_bytes_during_copy_do_not_publish(inputs,monkeypatch):
    import src.fundamentals_audit_bundle as module
    monkeypatch.setattr(module.shutil,"copyfile",lambda source,target:Path(target).write_bytes(b"changed"))
    with pytest.raises(ValueError,match="changed during copying"):
        publish_fundamentals_audit(**inputs)
    base=Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"])/"reports/26098-fundamentals-final"
    assert not (base/"current.json").exists()


def test_empty_inventory_and_reserved_identity_rejected(inputs):
    item=next(iter(inputs["files"].values()))
    inputs["files"]={}
    with pytest.raises(ValueError,match="nonempty"):
        publish_fundamentals_audit(**inputs)
    inputs["files"]={"inventory.sha256":item}
    with pytest.raises(ValueError,match="reserved"):
        publish_fundamentals_audit(**inputs)


@pytest.mark.parametrize("member",["response.json","asset-manifest.json","inventory.sha256"])
def test_existing_json_or_identity_corruption_does_not_move_pointer(inputs,member):
    item=next(iter(inputs["files"].values()))
    inputs["files"]={"response.json":item}
    older=publish_fundamentals_audit(**inputs)
    original_label=inputs["label"]
    inputs["label"]="20261018T150001000000Z"
    publish_fundamentals_audit(**inputs)
    root=Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"])
    base=root/"reports/26098-fundamentals-final"
    before=(base/"current.json").read_bytes()
    (root/older["relative"]/member).write_bytes(b"{}\n")
    inputs["label"]=original_label
    with pytest.raises(versioning.VersionError):
        publish_fundamentals_audit(**inputs)
    assert (base/"current.json").read_bytes()==before


def test_postpublication_verification_failure_restores_pointer(inputs,monkeypatch):
    publish_fundamentals_audit(**inputs)
    base=Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"])/"reports/26098-fundamentals-final"
    before=(base/"current.json").read_bytes()
    original=versioning.publish_version
    def corrupt_after_publication(base,label,write):
        result=original(base,label,write)
        (versioning.version_directory(base,label)/"asset-manifest.json").write_bytes(b"{}\n")
        return result
    monkeypatch.setattr(versioning,"publish_version",corrupt_after_publication)
    inputs["label"]="20261018T150001000000Z"
    with pytest.raises(versioning.VersionError,match="manifest mismatch"):
        publish_fundamentals_audit(**inputs)
    assert (base/"current.json").read_bytes()==before
    assert not versioning.version_directory(base,inputs["label"]).exists()
    assert len(list(base.glob(".failed-*")))==1


def test_identity_write_is_verified_before_publication(inputs,monkeypatch):
    original=Path.write_bytes
    def damage_identity(path,data):
        return original(path,b"truncated" if path.name=="inventory.sha256.partial" else data)
    monkeypatch.setattr(Path,"write_bytes",damage_identity)
    with pytest.raises(ValueError,match="identity failed verification"):
        publish_fundamentals_audit(**inputs)
    base=Path(inputs["environ"]["BEIDAN_PARQUET_ROOT"])/"reports/26098-fundamentals-final"
    assert not (base/"current.json").exists()
