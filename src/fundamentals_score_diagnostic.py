"""Small label-free score inputs from saved pages; shared temporal admission gate."""
from pathlib import Path
import pandas as pd
from src.fundamentals_issue_report import issue_capture_report
from src.fundamentals_pilot import pilot_tables
from src.fundamentals_home_away import home_away_windows
from src.fundamentals_roster_handicap import roster_handicaps
from src.temporal_learning import (Cutoff, AvailabilityFilter, AvailabilityPolicy,
    TemporalContractError, prepare_learning_context)
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_score_review import score_review_context


def prepare_score_diagnostic(roster_path, response_paths, *, issue, cutoffs,
                             expected_fixture_count, window, minimum,
                             repository_root, cache_dir, adjudications=None):
    """Return windows/lines/provenance, never target results or full raw DOM in R.

    All roster slots persist. Existing parsers, Titan selection and shared fixed
    windows own eligibility. Explicit per-slot cutoff map is required. Current
    saved-page evidence is HISTORICAL_PROXY: invoke the shared learning gate to
    demonstrate that it cannot authorize decision-facing fitting. This adapter
    does not invent earlier availability or fit/tune/calibration partitions.
    Read-only except for the existing content/code-bound optional parse cache.
    """
    report = issue_capture_report(roster_path, response_paths, issue=issue,
        expected_fixture_count=expected_fixture_count,
        expected_slots=[int(slot) for slot in cutoffs], cache_dir=cache_dir)
    pilot = pilot_tables(report, cutoffs=cutoffs, adjudications=adjudications)
    windows = home_away_windows(pilot, report['fixtures'], cutoffs=cutoffs,
        window=window, minimum=minimum, repository_root=repository_root)
    review = score_review_context(report,pilot,windows,cutoffs=cutoffs)
    observed = {o['evidence_class'] for o in report['observations'] if o.get('raw_sha256')}
    if observed - {'HISTORICAL_PROXY'}:
        raise ValueError('Unsupported source availability evidence; review admission contract')
    gates = []
    for f in report['fixtures']:
        cutoff = Cutoff.decision_epoch(issue, cutoffs[str(f['slot'])])
        try:
            prepare_learning_context(pd.DataFrame(), cutoff,
                source_hashes=report['input_file_hashes'], repository_root=Path(repository_root),
                implementation_modules=('src.fundamentals_score_diagnostic',),
                availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy('SAVED_ANALYSIS_PAGES')),
                intended_use='PROSPECTIVE_DECISION')
        except TemporalContractError as exc:
            gates.append(dict(issue=issue, slot=f['slot'], cutoff_utc=cutoff.cutoff_ts.isoformat(),
                status='UNAVAILABLE_FOR_FITTING', reason=str(exc), evidence_class='HISTORICAL_PROXY',
                source_availability='UNPROVEN', label_availability='UNPROVEN'))
        else:
            raise ValueError('Historical proxy unexpectedly passed shared admission gate')
    closure = implementation_closure(Path(repository_root),
        ('src.fundamentals_score_diagnostic',))
    return dict(issue=issue, windows=windows,
        handicaps=roster_handicaps(roster_path,issue=issue,slots=[f['slot'] for f in report['fixtures']]),
        gates=gates, source_policy=pilot['source_policy'], adjudications=pilot['adjudications'], historical_admission=False,
        review_context=review['fixtures'], review_queue=review['pending_queue'],
        input_file_hashes=report['input_file_hashes'],
        implementation_hashes=pilot['implementation_hashes'] | closure['files'])
