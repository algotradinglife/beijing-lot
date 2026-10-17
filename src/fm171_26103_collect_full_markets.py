"""Thin 26103 raw-history collection client; no estimation or cutoff admission.

Uses the authoritative shared cache and Titan60s rate limit. Existing original
captures are replayed; new raw bytes remain in that cache. One immutable receipt
per fixture/channel. Interrupted jobs resume without replacing completed work.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from filelock import FileLock
from beidan_backend.catalog.paths import location
from beidan_backend.extraction_cache import CacheMissError, CaptureIntegrityError, canonical_url
from beidan_backend.market_capture.history import (
    over_under_history_url, parse_over_under_history_json,
    parse_asian_handicap_history_json,
)
from beidan_backend.temporal_learning import implementation_closure, verify_implementation_closure
from beidan_backend.unified_sources import SourceClient, canonical
from beidan_backend.versioning import write_json_atomically


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", required=True, help="Explicit hot: catalog token")
    parser.add_argument("--slots", help="Optional bounded smoke-test slots")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if not args.output.startswith("hot:"):
        raise ValueError("Collection work must use an explicit hot: catalog token")
    out = location(args.output, require_exists=False)
    out.mkdir(parents=True, exist_ok=True)
    source = root / "results/fm171-26103-draw-20261017/inputs.json"
    acceptance = json.loads((source.parent / 'acceptance.json').read_bytes())
    expected = [p['sha256'] for p in acceptance['files']
                if p['path'] == 'results/fm171-26103-draw-20261017/inputs.json']
    if len(expected) != 1 or hashlib.sha256(source.read_bytes()).hexdigest() != expected[0]:
        raise ValueError('Frozen fixture input hash differs from original receipt')
    inputs = json.loads(source.read_bytes())
    fixtures = inputs["fixtures"]
    if len(fixtures) != 407 or {f["slot"] for f in fixtures} != set(range(1, 408)):
        raise ValueError("The exact407-fixture frozen scope is required")
    if len({f["fixture_id"] for f in fixtures}) != 407:
        raise ValueError("Duplicate fixture identity")
    if args.slots:
        slots = [int(v) for v in args.slots.split(",")]
        if len(slots) != len(set(slots)) or not set(slots) <= set(range(1, 408)):
            raise ValueError("Invalid bounded slots")
        fixtures = [f for f in fixtures if f["slot"] in slots]
    implementation = implementation_closure(root, (
        "beidan_backend.market_capture.history", "beidan_backend.unified_sources",
        "beidan_backend.versioning",
    ), distributions=("beautifulsoup4", "json5", "filelock"))
    binding = dict(inputs_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        implementation=implementation, company_id="8", slots=[f["slot"] for f in fixtures],
        cache_only=args.cache_only, purpose="RAW_POSTEVENT_CAPTURE_NOT_DECISION_ADMISSION")
    with FileLock(str(out / "run.lock"), timeout=0):
        manifest = out / "input-binding.json"
        if manifest.exists():
            if json.loads(manifest.read_bytes()) != binding:
                raise ValueError("Changed inputs/code/scope require a new output token")
        else:
            write_json_atomically(binding,manifest)
        client = SourceClient()
        completed = failures = empty = 0
        for f in fixtures:
            verify_implementation_closure(root, implementation)
            kickoff = datetime.fromisoformat(f["kickoff_at"])
            if kickoff.tzinfo is None:
                # Frozen R export declares these clocks UTC in its producer.
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            total_url = over_under_history_url(f["provider_id"], 8, kickoff)
            old_path = root / "results/fm16-upcoming-20261013/market-captures" / (f["fixture_id"].replace(":", "_") + ".json")
            old = json.loads(old_path.read_bytes()) if old_path.exists() else None
            for kind, url, parse in (
                ("total", total_url, parse_over_under_history_json),
                ("asian", total_url.replace("oddskind=1", "oddskind=0"), parse_asian_handicap_history_json),
            ):
                target = out / (f["fixture_id"].replace(":", "_") + "-" + kind + ".json")
                if target.exists():
                    envelope = json.loads(target.read_bytes())
                    payload = envelope['payload']
                    if envelope['sha256'] != hashlib.sha256(payload.encode('utf-8')).hexdigest():
                        raise ValueError("Completed receipt integrity check failed")
                    saved = json.loads(payload)
                    if saved["inputs_sha256"] != binding["inputs_sha256"] or saved["url"] != url:
                        raise ValueError("Existing receipt binding differs")
                    completed += saved["state"] == "PARSED"
                    empty += saved["state"] == "OBSERVED_EMPTY"
                    failures += saved["state"] not in {"PARSED", "OBSERVED_EMPTY"}
                    continue
                result = dict(fixture_id=f["fixture_id"], provider_id=f["provider_id"],
                    home_id=f["home_id"], away_id=f["away_id"], kind=kind, url=url,
                    cutoff_utc=f["cutoff_utc"], kickoff_utc=kickoff.isoformat(),
                    inputs_sha256=binding["inputs_sha256"], state="NOT_COLLECTED",
                    network_attempts=0, historical_admission=False)
                try:
                    originals = [] if old is None else [c for c in old["captures"]
                        if c["kind"] == kind and c.get("sha256") and canonical_url(c["url"]) == canonical_url(url)]
                    if len(originals) > 1:
                        raise ValueError("Ambiguous original capture")
                    if originals:
                        cap = originals[0]
                        raw = (root / cap["raw_path"]).read_bytes()
                        if hashlib.sha256(raw).hexdigest() != cap["sha256"]:
                            raise CaptureIntegrityError("Original raw capture hash mismatch")
                        result["raw_receipt"] = cap
                        result["origin"] = "EXISTING_PINNED_CAPTURE"
                    else:
                        cap = client.request("titan", url, max_age=0,
                            cache_only=args.cache_only, reuse_raw=True)
                        raw = cap["data"]
                        result["raw_receipt"] = cap["receipt"]
                        result["network_attempts"] = cap["receipt"]["network_attempts"]
                        result["origin"] = "SHARED_RAW_CACHE"
                    result['raw_sha256'] = hashlib.sha256(raw).hexdigest()
                    if json.loads(raw) == []:
                        result.update(state='OBSERVED_EMPTY', snapshots=[],
                            counters={'candidate_rows': 0, 'observed_empty': True})
                        empty += 1
                    else:
                        snapshots, counters = parse(raw, kickoff_hkt=kickoff)
                        result.update(state="PARSED", counters=counters,
                            snapshots=[asdict(s) for s in snapshots])
                        completed += 1
                except (ValueError, OSError, RuntimeError) as error:
                    state = ('CACHE_MISS' if isinstance(error, CacheMissError) else
                             'INTEGRITY_FAILURE' if isinstance(error, CaptureIntegrityError) else
                             'PARSE_FAILED' if 'raw_receipt' in result else 'FETCH_FAILED')
                    result.update(state=state,
                        error_type=type(error).__name__, error=str(error),
                        network_attempts=getattr(error, "network_attempts", result["network_attempts"]))
                    failures += 1
                payload = canonical(result)
                envelope = dict(payload=payload,sha256=hashlib.sha256(payload.encode('utf-8')).hexdigest())
                write_json_atomically(envelope,target)
                print(f["fixture_id"], kind, result["state"], "parsed", completed, "failures", failures, flush=True)
        status = dict(scope_fixtures=len(fixtures), expected_channels=2*len(fixtures),
            parsed_channels=completed, failed_or_missing_channels=failures,
            observed_empty_channels=empty,
            traversal_complete=True,
            collection_complete=failures == 0, full_fm_analysis_accepted=False,
            historical_admission=False)
        write_json_atomically(status,out / 'collection-status.json')
        print(json.dumps(status), flush=True)
        if failures:
            raise SystemExit(2)
