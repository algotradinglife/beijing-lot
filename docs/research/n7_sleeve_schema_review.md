# PR426 estimand schema remediation

Addresses PI re-review comment 5645805584 against e41afd8c. No new strategy search.

The sleeve portfolio boundary deletes the inherited mixed-unit `mean_coverage`.
It emits `mean_sleeve_coverage` only for sleeve arms and
`mean_ticket_probability` only for monolithic controls, with the other null.
Empty plans have both null. Individual ticket probabilities are independently
recomputed from selected fixture/outcome probabilities. Generic older research
functions outside this boundary and immutable historical artifacts are unchanged.
No compatibility alias, fallback, or artifact migration is introduced.

`tests/test_n7_sleeve_portfolio.py` covers producer fields, actual subset averages,
monolithic ticket averages and empty sleeve plans. `tests/test_n7_sleeve_checker.py`
exercises the real runner/checker, including fully resealed legacy-name injection,
non-applicable non-null fields, wrong monolithic mean and old factor-64 error.

Validation (project Python, TMPDIR=/dev/shm):

- `python -m pytest tests/test_n7_sleeve_portfolio.py tests/test_n7_sleeve_checker.py tests/test_n7_sleeve_runner.py tests/test_n7_sleeve_states.py -q`: 7 passed.
- `python scripts/check_cutoff_governance.py`: PASS.
- `quarto render quarto/138_n7_sleeve_review_corrections.qmd --execute --execute-dir /home/drwho1985/.codex/worktrees/0aac/beijing-lot`: PASS, clean execution and embedded HTML. Initial render without explicit execute-dir failed relative source lookup; corrected invocation passed.
- Prior-HEAD versus new producer: 33 fixture plans identical outside renamed metadata and seals, including tickets, allocation, simulation and financial metrics.
- Independent Codex review: no actionable findings; reviewer independently ran 2 tests, passed.
- Full R suite not repeated: no R function changes; the affected QMD uses the existing tested functions and was rerendered.

Logs and the diagnostic comparison script are in
`data/derived/fundamentals_417/n7-sleeve-schema-review/`.
Machine-readable source bindings and review conclusion:
`docs/research/n7_sleeve_schema_receipt.json`.

Remote CI remains disabled by owner instruction. PR stays Draft and #424 stays
OPEN / PI Review; broader scientific acceptance gaps remain. Historical admission
remains false. No old frozen plan or earlier acceptance receipt is rewritten.
