"""Command-only capture of the receipt-bound Nowscore raw gap URLs at approved5s cadence."""
if __name__ == '__main__':
    import argparse,csv,hashlib,json,re
    from pathlib import Path
    from filelock import FileLock
    from beidan_backend.unified_sources import SourceClient,document_bytes
    from beidan_backend.transport import FetchError
    from beidan_backend.source_rate_policy import set_source_interval
    from beidan_backend import source_rate_policy
    from beidan_backend.catalog.paths import location
    from beidan_backend.versioning import write_json_atomically
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--policy-receipt',required=True)
    p.add_argument('--min-interval-seconds',type=int,choices=[5],required=True)
    a=p.parse_args()
    rows=list(csv.DictReader(Path(a.input).open()))
    if not rows or len(rows)>730 or len({r['url'] for r in rows})!=len(rows) or len({r['fixture_id'] for r in rows})>365:
        raise ValueError('Unique nonempty bounded Nowscore queue required')
    for r in rows:
        if r['source']!='nowscore' or not re.fullmatch(r'26105:[1-9]\d*',r['fixture_id']) or int(r['fixture_id'].split(':')[1])>365 or not re.fullmatch(r'[0-9]+',r['provider_id']) or not r['provider_id'].strip('0'):
            raise ValueError('Invalid issue/source/native identity')
        native=r['provider_id'].lstrip('0')
        routes=dict(analysis=f'https://live.nowscore.com/analysis/{native}cn.html',euro=f'https://1x2.nowscore.com/{native}.js',auxiliary=f'https://live.nowscore.com/analysisJs/data{native}.js')
        if r['kind'] not in routes or r['url']!=routes[r['kind']]:
            raise ValueError('Queue URL does not match exact native route')
    queue_receipt_path=Path(str(a.input)+'.json')
    qr=json.loads(queue_receipt_path.read_bytes())
    if qr['rows']!=len(rows) or qr['fixtures']!=len({r['fixture_id'] for r in rows}) or qr['output_sha256']!=hashlib.sha256(Path(a.input).read_bytes()).hexdigest():
        raise ValueError('Queue receipt mismatch')
    if len(qr['input_files'])!=3:raise ValueError('Three source tables required')
    for item in qr['input_files']+[qr['source_client']]:
        if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Queue transitive source binding mismatch')
    policy_path=Path(a.policy_receipt);policy=json.loads(policy_path.read_bytes())
    if policy['state']!='APPLIED' or policy['receipt']['source']!='nowscore' or policy['receipt']['interval_seconds']!=5 or not policy['receipt']['last_attempt_preserved']:
        raise ValueError('Applied Nowscore5second policy receipt required')
    if policy['receipt']['implementation_sha256']!=hashlib.sha256(Path(source_rate_policy.__file__).read_bytes()).hexdigest():
        raise ValueError('Policy implementation mismatch')
    work=location(a.output,require_exists=False);work.mkdir(parents=True,exist_ok=True)
    with FileLock(str(work/'capture.lock'),timeout=0):
        binding=dict(policy_receipt_sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),queue_receipt_sha256=hashlib.sha256(queue_receipt_path.read_bytes()).hexdigest(),input_sha256=hashlib.sha256(Path(a.input).read_bytes()).hexdigest(),client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope=len(rows),minimum_interval_seconds=5,maximum_transport_attempts_per_pass=2,maximum_passes=2,raw_only=True)
        bp=work/'input-binding.json'
        if bp.exists():
            if json.loads(bp.read_bytes())!=binding:raise ValueError('Immutable capture binding mismatch')
        else:write_json_atomically(binding,bp)
        client=SourceClient();results=[]
        # Explicit raw API below supplies5, instead of SourceClient.request's120 default.
        admission=set_source_interval(client.cache,'nowscore',5,expected_interval_seconds=5,reason='Verify already-authorized5second capture cadence')
        write_json_atomically(admission,work/'admission-policy.json')
        for i,r in enumerate(rows):
            target=work/(r['fixture_id'].replace(':','_')+'-'+r['kind']+'.json')
            prior=json.loads(target.read_bytes()) if target.exists() else None
            if prior and prior['state']=='CAPTURED_RAW_ONLY':results.append(prior);continue
            attempts=prior['passes'] if prior else 0
            if attempts>=2:results.append(prior);continue
            if prior:write_json_atomically(prior,work/(target.stem+f'-failed-pass{attempts}.json'))
            item=dict(**r,passes=attempts+1)
            try:
                cap=client.cache.extract('nowscore',r['url'],document_bytes,max_age=0,min_interval=5,retries=1,reuse_raw=True)
                item.update(state='CAPTURED_RAW_ONLY',receipt=cap['receipt'])
            except FetchError as error:
                item.update(state='REQUEST_FAILED',error=str(error),network_attempts=error.network_attempts)
            write_json_atomically(item,target);results.append(item)
            if (i+1)%10==0:print('PROGRESS',i+1,'/'+str(len(rows)),flush=True)
        summary=dict(binding=binding,total=len(results),captured=sum(r['state']=='CAPTURED_RAW_ONLY' for r in results),failed=sum(r['state']!='CAPTURED_RAW_ONLY' for r in results),raw_only=True,price_validation=False)
        write_json_atomically(summary,work/'completion.json');print(json.dumps(summary),flush=True)
        raise SystemExit(0 if summary['failed']==0 else 2)
