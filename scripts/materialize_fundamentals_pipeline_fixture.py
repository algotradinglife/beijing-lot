"""Materialize a sealed, network-free #408 integration bundle."""
from pathlib import Path
import argparse
import base64
import gzip
import hashlib
import json
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))

from src.fundamentals_census import analysis_record, canonical

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    root = arguments.output_dir
    root.mkdir(parents=True, exist_ok=False)
    fixtures = repo / "tests" / "fixtures" / "fundamentals_census"
    for scope in ("main", "regression"):
        subprocess.run([sys.executable, str(repo / "scripts" / "materialize_fundamentals_census_fixture.py"),
                        "--output-dir", str(root / f"raw_{scope}")], check=True)
    observations = []
    for source in ("nowscore", "titan"):
        raw = gzip.decompress((fixtures / f"{source}-1870517.html.gz").read_bytes())
        parsed = analysis_record(raw, source=source, provider_id="1870517")
        host = "live.nowscore.com" if source == "nowscore" else "zq.titan007.com"
        suffix = "html" if source == "nowscore" else "htm"
        observations.append({"source": source, "url": f"https://{host}/analysis/1870517cn.{suffix}",
                             "sha256": hashlib.sha256(raw).hexdigest(),
                             "received_at_utc": "2026-09-05T10:00:00Z",
                             "identity": {key: parsed[key] for key in ("home", "away", "home_id", "away_id", "kickoff_utc")}})
    official = b"Original club report: third goal was scored in extra time."
    official_hash = hashlib.sha256(official).hexdigest()
    official_url = "https://club.example/match-report"
    receipt = {"url": official_url, "final_url": official_url, "status": 200,
               "content_type": "text/plain; charset=UTF-8",
               "started_at_utc": "2026-09-05T10:01:00Z", "received_at_utc": "2026-09-05T10:01:01Z",
               "byte_count": len(official), "sha256": official_hash,
               "body_base64": base64.b64encode(official).decode("ascii")}
    (root / "official").mkdir()
    (root / "official" / "report.json").write_text(canonical(receipt) + "\n", encoding="utf-8")
    review = {"schema": "bj407_independent_audit_v1", "revision": 1, "case_kind": "regression",
              "issue": "20064", "slot": 293, "provider_id": "1870517", "observations": observations,
              "independent_evidence": [{"url": official_url, "final_url": official_url,
                                         "sha256": official_hash, "file": "official/report.json",
                                         "independence": "ORIGINAL_PARTICIPATING_CLUB_NARRATIVE",
                                         "statistical_upstream": "NOT_RELIED_ON"}],
              "disposition": "REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED",
              "rationale": "Independent club narrative distinguishes regulation and extra time.",
              "reviewer": "fixture reviewer", "reviewed_at_utc": "2026-09-05T10:02:00Z",
              "availability_class": "HISTORICAL_PROXY", "settlement_mutation": False, "model_admission": False}
    (root / "independent-cases.v1.json").write_text(canonical([review]) + "\n", encoding="utf-8")
    (root / "agreement-spotchecks.v1.json").write_text("[]\n", encoding="utf-8")
    files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.rglob("*")) if path.is_file()}
    manifest = {"schema": "bj407_census_bundle_v1", "sealed_at_utc": "2026-09-05T10:03:00Z",
                "historical_learning": "NONE", "files": files}
    manifest_path = root / "bundle-manifest.json"
    manifest_path.write_text(canonical(manifest) + "\n", encoding="utf-8")
    (root / "bundle-manifest.sha256").write_text(
        f"{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}  bundle-manifest.json\n", encoding="utf-8")
    print(json.dumps({"bundle_dir": str(root), "files": len(files)}, sort_keys=True))
