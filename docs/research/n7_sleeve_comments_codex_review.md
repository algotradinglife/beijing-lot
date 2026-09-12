No actionable defects remain in the scoped remediation against `db4723d6`. The prior P2 documentation finding is resolved.

- Both documents distinguish Top64-PROB depth from actual selected-subset coverage. Reconstruction uses `sleeve_keys` `(id, option)`, canonical selected IDs or exact `selected_rules` tokens, sums `long.prob`, then averages sleeves.
- Ran the project Python with `-m pytest -p no:cacheprovider tests/test_n7_sleeve_portfolio.py tests/test_n7_sleeve_checker.py -q`: **2 passed**. Coverage includes all sleeve-arm means, RANDOM_STATES versus PROB on identical fixture sets, empty exposure, and resealed incorrect-mean rejection.
- Reused earlier independent evidence for unchanged code. Inspected the completed full R log and successful QMD138/final QMD134 render logs; did not rerun those checks. QMD138 receipt hashes match current inputs and implementations. The earlier custom-filename render failure was superseded by the successful normal-filename retry.

This verdict covers local remediation; remote PR426 still points to `db4723d6`. Live #424 remains **OPEN / PI Review**, parent #202, with no dependency edges or subissues.

**Historical-only · KEEP DRAFT / NO MERGE.** The broader #424 contract remains incomplete. CI remains intentionally disabled. No edits or GitHub mutations performed.