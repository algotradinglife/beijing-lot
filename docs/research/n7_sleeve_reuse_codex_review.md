No actionable correctness findings in the specified diff against `219ecc32`, including the new document, configuration, fixture and QMD.

Live #424 graph read before and after review: **OPEN / PI Review**, parent #202, no dependencies or subissues.

Verified:

- U/P count fixture membership per sleeve; caps and affordability filter before renormalized RNG selection. Exhaustion retains cash without relaxation or global infeasibility claims.
- Candidate identity, budgets, cutoff/source/implementation bindings, independent checker reconstruction, reason handling, multiple-arm R joins and full-grid freeze-before-audit.
- **All 300** unrestricted plans reproduce old holdings, draws, simulation and economics. Old implementation hashes match `219ecc32`; no hash bypass or artifact rewriting.
- All 1,500 new ledger source/plan hashes pass. Independently replayed **36 plans** across three issues, four policies and three seeds.
- Native/archive result identity and all five report tables match exactly.

Checks I ran:

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python -m pytest -p no:cacheprovider tests/test_n7_sleeve_probability_cap.py tests/test_n7_sleeve_cap_runner.py -q
```

**18 passed.**

```sh
R_LIBS_USER=/home/drwho1985/workspace/algotradinglife/beijing-lot/r_lib TMPDIR=/dev/shm Rscript -e 'testthat::test_file("tests/testthat/test-n7-sleeve-cap-report.R", stop_on_failure=TRUE)'
```

**15 expectations passed**, no warnings/skips.

The other run’s full R-suite log now reports completion; native/archive render logs report success. Its **1,500-plan checker receipt** passes current implementation, freeze and result-hash verification. I did not rerun those full jobs.

Transitive selection inventory includes inherited draw calibration and prediction, probability-gate candidate generation/ranking, sleeve enumeration/TOP64 selection, candidate expansion, fixed64 sampling, capped-prefix selection, U/P filtering, weighted draws and shared-world evaluation. This change adds no fitting or chronology utilities.

**Verdict: acceptable for historical diagnostics only.** Preserve `historical_admission=false` and prior PI concerns about source availability, exposed-history selection, simultaneous-ticket causality, R-native computation and joint return/path-risk optimization. This does **not** complete #424’s broader contract.