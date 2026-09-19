"""Resumable bounded queue over the authoritative immutable market capturer."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scope',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--market',choices=['euro','total'],required=True);args=parser.parse_args()
    scope=Path(args.scope);items=json.loads(scope.read_text());out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(scope.read_bytes()).hexdigest();receipt=out/'queue.json'
    contract=dict(scope=str(scope),scope_sha256=digest,market=args.market,chunk_size=20,items=len(items))
    if receipt.exists():
        if json.loads(receipt.read_text())!=contract:raise ValueError('Immutable queue scope changed')
    else:receipt.write_text(json.dumps(contract,indent=2))
    for index,start in enumerate(range(0,len(items),20),1):
        batch=out/f'batch-{index:04d}';manifest=batch/'capture-manifest.json';chunk=out/f'scope-{index:04d}.json'
        payload=items[start:start+20]
        if manifest.exists():
            saved=json.loads(manifest.read_text())
            for name,h in saved['file_hashes'].items():
                if hashlib.sha256((batch/name).read_bytes()).hexdigest()!=h:raise ValueError('Captured batch changed')
            if len(saved['documents'])!=len(payload):raise ValueError('Batch scope mismatch')
            continue
        if batch.exists():raise ValueError('Incomplete published batch; inspect before retry')
        if hashlib.sha256(scope.read_bytes()).hexdigest()!=digest:raise ValueError('Scope changed')
        chunk.write_text(json.dumps(payload))
        subprocess.run([sys.executable,'scripts/collect_fundamentals_market.py','--scope',str(chunk),'--output',str(batch),'--market',args.market],check=True,stdout=subprocess.DEVNULL)
        saved=json.loads(manifest.read_text())
        states={s:sum(r['state']==s for r in saved['documents']) for s in ['HTTP_OK','HTTP_FAILURE','TRANSPORT_FAILURE']}
        print(json.dumps(dict(market=args.market,batch=index,processed=min(start+20,len(items)),total=len(items),states=states)),flush=True)
        time.sleep(5)  # Retain existing5s source spacing across batch boundaries.
    print('QUEUE_COMPLETE',args.market,len(items),flush=True)
