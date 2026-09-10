import hashlib
import json
import pytest
from src.context_projection import project_feature_context


def test_projection_preserves_rows_binds_full_evidence_and_rejects_changes(tmp_path):
    payload = dict(rows=[{'issue':'100101','slot':1}],cutoffs={'100101':{'1':'2010-01-01T00:00:00Z'}},
        input_file_hashes={'raw':'sha'},implementation_hashes={'parser':'sha'},
        receipts=[dict(issue='100101',slot=1,provider_id='42',views={'home':dict(rows=[{'home_goals':2}],receipt={'large':'audit'})})])
    encoded = json.dumps(payload)
    full = dict(payload,canonical_json=encoded,seal=hashlib.sha256(encoded.encode()).hexdigest())
    source=tmp_path/'source.json';output=tmp_path/'projected.json'
    source.write_text(json.dumps(full));original=source.read_bytes()
    project_feature_context(source,output)
    result=json.loads(output.read_text())
    assert result['rows']==payload['rows'] and result['cutoffs']==payload['cutoffs']
    assert result['receipts'][0]['views']['home']['rows']==payload['receipts'][0]['views']['home']['rows']
    assert result['input_file_hashes'][str(source.resolve())]==hashlib.sha256(original).hexdigest()
    assert source.read_bytes()==original
    assert project_feature_context(source,output)==str(output)
    with pytest.raises(ValueError,match='Preserve'):
        project_feature_context(source,source)
    changed=json.loads(output.read_text());changed['rows']=[];output.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='Frozen'):
        project_feature_context(source,output)
    full['rows']=[];source.write_text(json.dumps(full))
    with pytest.raises(ValueError,match='Original'):
        project_feature_context(source,tmp_path/'bad.json')


def test_source_named_like_output_temporary_is_preserved(tmp_path):
    payload = dict(rows=[],cutoffs={},input_file_hashes={},implementation_hashes={},receipts=[])
    encoded=json.dumps(payload)
    original=json.dumps(dict(payload,canonical_json=encoded,seal=hashlib.sha256(encoded.encode()).hexdigest())).encode()
    source=tmp_path/'context.json.tmp';source.write_bytes(original)
    output=tmp_path/'context.json'
    project_feature_context(source,output)
    assert source.read_bytes()==original
    assert json.loads(output.read_text())['input_file_hashes'][str(source.resolve())]==hashlib.sha256(original).hexdigest()
    assert not list(tmp_path.glob('.context-projection-*'))
