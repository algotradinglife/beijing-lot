"""Thin post-freeze role coverage diagnostic entry point."""
import argparse
import json
from src.n7_core_coverage import package_core_coverage

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','report-archive','destination','repository-root','expected-report-sha256'):
        p.add_argument('--'+name,required=True)
    a=p.parse_args()
    print(json.dumps(package_core_coverage(a.study,a.report_archive,a.destination,
        repository_root=a.repository_root,expected_report_sha256=a.expected_report_sha256),sort_keys=True))
