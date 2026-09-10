"""Isolated release worker; invoked by predict_draw_version with verified inputs."""
import hashlib
import json
import pickle
import sys
from pathlib import Path

# The parent chooses the frozen runtime; never inherit another version's src.
sys.path.insert(0,str(Path.cwd()))
import pandas as pd
from src.temporal_learning import Cutoff

if __name__=='__main__':
    request=json.load(sys.stdin);entry=request['entry'];root=Path(request['root'])
    rows=[];models={};receipts={}
    if entry['backend']=='CALIBRATED':
        from src.fundamentals_calibrated_draw import load_calibrated_draw,predict_calibrated_draw
        artifact=load_calibrated_draw(root/entry['model_dir'],
            expected_version=entry['implementation_version'],repository_root=Path.cwd())
        receipts['calibrated']=artifact['receipt']
    else:
        from src.fundamentals_retrained_experts import predict_frozen_file,predict_experts
    for name,module in list(sys.modules.items()):
        if name=='src' or name.startswith('src.'):
            if not getattr(module,'__file__',None) or not Path(module.__file__).resolve().is_relative_to(Path.cwd()/'src'):
                raise ValueError('Imported implementation escaped the frozen runtime: '+name)
    for record,decision in zip(request['records'],request['decisions']):
        cutoff=Cutoff.decision_epoch(record['issue_code'],decision)
        frame=pd.DataFrame([record])
        if entry['backend']=='CALIBRATED':
            options={}
            if request.get('draw_weight') is not None:
                options['draw_weight']=request['draw_weight']
            result=predict_calibrated_draw(artifact,frame,cutoff,**options)
        else:
            issue=record['issue_code'];path=root/entry['models'][issue]
            if issue not in models:
                # Original loader checks original sources/code/cutoff first.
                result=predict_frozen_file(path,frame,cutoff,repository_root=Path.cwd())
                metadata=json.loads(path.with_suffix('.json').read_text());raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=metadata['model_sha256']:
                    raise ValueError('Frozen model changed during load')
                models[issue]=pickle.loads(raw)
                receipts[issue]=metadata['receipt']
            else:
                result=predict_experts(models[issue],frame,cutoff)
        rows.extend(json.loads(result.to_json(orient='records',double_precision=15)))
    imported={}
    for name,module in list(sys.modules.items()):
        if name=='src' or name.startswith('src.'):
            if not getattr(module,'__file__',None) or not Path(module.__file__).resolve().is_relative_to(Path.cwd()/'src'):
                raise ValueError('Imported implementation escaped the frozen runtime: '+name)
            path=Path(module.__file__).resolve()
            imported[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    json.dump(dict(rows=rows,model_receipts=receipts,runtime_root=str(Path.cwd()),imported_sources=imported),sys.stdout)
