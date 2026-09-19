"""Read hash-bound CSV labels through an issue-level prior-availability barrier."""
import csv
import hashlib
import io
from pathlib import Path

from .core import Cutoff, TemporalContractError
from .diagnostic_labels import diagnostic_label_clock


def read_prior_label_rows(path, expected_sha256, *, cutoff, issue_clocks,
                          excluded_issues, delay_hours, issue_column):
    """Return CSV dictionaries ONLY for prior, nonexcluded issue identities.

    issue_clocks maps exact issue IDs to last fixture decision clocks. Labels
    never authorize their own availability. Whole-file bytes are verified once;
    target/later row values never leave this shared admission boundary. This is
    diagnostic proxy evidence only, not observed label availability. No writes.
    """
    if not isinstance(cutoff, Cutoff) or not issue_clocks:
        raise TemporalContractError('Explicit cutoff and issue clocks required')
    allowed = set()
    for issue, timestamp in issue_clocks.items():
        if issue == cutoff.target_issue or issue in excluded_issues:
            continue
        try:
            diagnostic_label_clock(timestamp, cutoff=cutoff, delay_hours=delay_hours)
        except TemporalContractError as exc:
            if str(exc) != 'Diagnostic label clock must precede cutoff':
                raise
        else:
            allowed.add(issue)
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise TemporalContractError('Prior label source hash mismatch')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8')))
    if not reader.fieldnames or issue_column not in reader.fieldnames:
        raise TemporalContractError('Label CSV lacks issue identity')
    return [row for row in reader if row[issue_column] in allowed]
