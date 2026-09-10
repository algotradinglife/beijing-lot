import hashlib
import json
from pathlib import Path
import pytest
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_clean_receipts import verify_clean_file_bindings, verify_clean_validation_receipts


@pytest.fixture
def receipt_tree(tmp_path):
    root=tmp_path
    def write(name, value):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value));return hashlib.sha256(path.read_bytes()).hexdigest()
    code={p:write(p,{}) for p in ['scripts/predict_clean_validation.py','scripts/settle_clean_validation.py','r/audit.R','runtime/helper.py','model.pkl']}
    versions={v:dict(version=v,backend='RAW_TREE',files={'model.pkl':code['model.pkl']}) for v in ['0.1.0','1.1.0']}
    cat=dict(receipt=dict(versions=versions));cat['seal']=stable_json_hash(cat['receipt'])
    original=write('config/expert_versions/draw.json',cat);local=write('study/signals/catalog.json',cat)
    receipt=dict(version='1.1.0',catalog_seal=cat['seal'],imported_sources={'runtime/helper.py':code['runtime/helper.py']})
    signal_hash=write('study/signals/issue.json',dict(receipts=dict(draw=dict(prediction_receipt=receipt,prediction_seal=stable_json_hash(receipt)))))
    signal_receipt=write('study/signals/receipt.json',dict(files={'study/signals/issue.json':signal_hash},catalog_sha256=local,original_catalog_sha256=original,implementation_sha256=code['scripts/predict_clean_validation.py']))
    prepared=write('study/prepared.json',{});projected=write('study/projected/receipt.json',{})
    write('study/factors.json',dict(implementation={'runtime/helper.py':code['runtime/helper.py']},source_hashes=dict(prepared=prepared,projected=projected,signals=signal_receipt)))
    db=write('snapshot.sqlite',{});labels=write('study/labels.json',[]);plans=write('study/plans-frozen.json',{})
    audit=write('study/settlement-audit.json',dict(receipt=dict(implementation={'r/audit.R':code['r/audit.R']},db_path='snapshot.sqlite',db_sha256=db,labels_sha256=labels,plans_sha256=plans)))
    write('study/results.json',dict(implementation_sha256=code['scripts/settle_clean_validation.py'],audit_sha256=audit))
    return root


def test_receipt_chain_and_missing(receipt_tree):
    root=receipt_tree
    assert verify_clean_validation_receipts(root/'study',repository_root=root)
    with pytest.raises(FileNotFoundError):verify_clean_file_bindings({'missing':'x'},repository_root=root)


@pytest.mark.parametrize('path',['model.pkl','runtime/helper.py','r/audit.R','snapshot.sqlite','study/labels.json','study/plans-frozen.json','scripts/predict_clean_validation.py','scripts/settle_clean_validation.py','config/expert_versions/draw.json','study/signals/catalog.json','study/signals/issue.json','study/projected/receipt.json','study/settlement-audit.json'])
def test_transitive_mutation_rejected(receipt_tree,path):
    (receipt_tree/path).write_text('{}changed')
    with pytest.raises(ValueError,match='Changed|changed'):
        verify_clean_validation_receipts(receipt_tree/'study',repository_root=receipt_tree)
