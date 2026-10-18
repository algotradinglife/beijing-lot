"""One-shot, receipt-bound application of the user's explicit5second source policy."""
if __name__ == '__main__':
    import argparse,hashlib,json
    from pathlib import Path
    from beidan_backend import source_rate_policy
    from beidan_backend.unified_sources import SourceClient
    from beidan_backend.catalog.paths import location
    from beidan_backend.versioning import write_json_atomically
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',choices=['nowscore'],required=True)
    p.add_argument('--expected-seconds',type=float,required=True)
    p.add_argument('--seconds',type=float,choices=[5],required=True)
    p.add_argument('--reason',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args();target=location(a.output,require_exists=False)
    prepared=target.with_name(target.stem+'-prepared.json')
    if target.exists() or prepared.exists():raise ValueError('One-shot output already exists; inspect its receipt before another operation')
    plan=dict(source=a.source,expected_interval_seconds=a.expected_seconds,interval_seconds=a.seconds,reason=a.reason,
        client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        policy_sha256=hashlib.sha256(Path(source_rate_policy.__file__).read_bytes()).hexdigest())
    write_json_atomically(value=plan,path=prepared)
    try:
        client=SourceClient()
        # Administrative writers need to observe the brief gaps between capture calls.
        # Same FileLock object is reentrant inside the authoritative policy function.
        with client.cache.lock.acquire(timeout=120,poll_interval=0.001):
            receipt=source_rate_policy.set_source_interval(client.cache,a.source,a.seconds,
                expected_interval_seconds=a.expected_seconds,reason=a.reason)
    except BaseException as error:
        write_json_atomically(value=dict(plan=plan,state='FAILED',error_type=type(error).__name__,error=str(error)),path=target.with_name(target.stem+'-failed.json'))
        raise
    result=dict(state='APPLIED',plan=plan,receipt=receipt)
    print(json.dumps(result),flush=True)
    write_json_atomically(value=result,path=target)
