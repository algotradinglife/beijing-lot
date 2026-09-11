# Zero-handicap converter gate

Fixed exposed historical diagnostic, not fitting or prospective acceptance.
The original paired and independently assembled plans are inventoried evidence.
Keep every primary component unchanged. Drop a complementary component only
when its C fixture has nonzero home handicap; all six other fixtures are irrelevant
to this gate. Hold freed cash. No regrouping, replacement, extra stake or quota transfer.

Interface: `src/fundamentals_converter_gate.py::gate_zero_converter`.
Requires an inventoried sealed plan, identical prediction frame, explicit native
fixture cutoffs, boolean zero_only and integer CNY budget. Returns sealed plan
with component ordering/bytes retained, upstream seal, dropped indices and cash.
No I/O. All source identity, probability and cutoff mismatches fail.
Tests: `tests/test_fundamentals_converter_gate.py`, zero/positive/negative,
mixed, empty, nonmutation, identity, cutoff, labels and budget failures.

Run with configured project Python:
```
python scripts/zero_converter.py freeze --study NEW_DIRECTORY
python scripts/zero_converter.py settle --study NEW_DIRECTORY
quarto render quarto/97_zero_converter.qmd --execute-dir . --execute --no-cache -P study:NEW_DIRECTORY
```
QMD uses existing R summary/equity functions, reports per-issue ROI and drawdown.
No new dependency. R/Python/Quarto versions remain declared in
config/compression_breadth_runtime.json.

All 576 plans (48 issues x 12 variants) freeze before settlement. Source inventories,
prediction hash, transitive current implementation and report files are bound.
The existing frozen audit locator is bound before label access. Production uses
settle_n7_twocover; runner independently reconciles hits and payout by raw audit
directions/SP with one ticket-level .65 factor. Retrospective proxy chronology
does not authorize prospective use or prove simultaneous ticket availability.
No fitting, threshold search, cache or model retraining; historical dependencies
stay inventoried and are not relabeled as current clean model interfaces.

v1 retained as evidence of an initial incompatible report-scope tag. v2 uses the
existing report reader's declared diagnostic scope and is the deliverable.
No original input is overwritten. Budget1024/issue; unit2; initial capital100000.

Initial results: paired ALL net15819.53, ROI60.96%, DD3113.14, hitissues21;
ZERO net17143.97, ROI92.85%, DD2121.14, hitissues19.
Independent25% ALL net10251.36 vs ZERO11627.36; independent75% falls
from3243.44 to2565.79. This is evidence about deletion, not new optimized zero-only
group assembly, and is not a general guarantee.

## Validation

- `/home/drwho1985/.codex/validation-envs/compression-bridge/bin/python -m pytest tests/test_fundamentals_converter_gate.py -q`: 6 passed.
- `python scripts/check_cutoff_governance.py`: PASS.
- Both freeze/settle phases completed: 576 plans, 576 independently reconciled results.
- Live QMD97 and restored archive-mode QMD97 both executed in fresh R processes,
  cache disabled and errors fatal. HTML has tables of12/10/576rows and2figures.
  Table/image presence inspected programmatically; no visual pixel inspection.
- Codex local technical review: no actionable findings. Reviewer ran5function tests
  before the sixth archive test was appended; root ran all6. Reviewer verified
  implementation/source/report bindings, result hashes, and exact filtering/cash
  across576plans. It did not rerun QMD or full settlement; root completed both.
- CI now runs gate/fixture tests and archived QMD97; remote CI not claimed passed.
- Existing R summary/equity functions unchanged. No new R function.
- Graph419/421 remains open;419 blockedBy421. This review is not issue acceptance.

Reproducible report input: `tests/fixtures/zero_converter.json.gz`, restored using
`scripts/prepare_n7_single_fixture.py`; archive rendering does not replay the model.
Current live result: `data/derived/fundamentals_417/zero-converter-v2`.
Review evidence: `data/derived/fundamentals_417/zero-converter-review.txt`.
