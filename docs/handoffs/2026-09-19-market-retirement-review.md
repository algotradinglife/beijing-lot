**Final review: not passed — 3 actionable P2 findings.** Reviewed the actual [final bundle](/run/media/drwho1985/Sandisk/data/beijing-lot/audits/market-sqlite/batch-0003-v1/final-retirement-bundle.json), SHA256 `24f2854a5f005da055a6672f6a08479ed6090f24a1b83e7b338bae318de88fcc`.

1. **P2 — Effective systemd checks discard repeated commands. Confidence: 10/10.**
   [market_retirement_consumers.py:66](/home/drwho1985/.codex/worktrees/0aac/beijing-lot/src/market_retirement_consumers.py:66) uses `properties = dict(line.split('=', 1) for line in actual.splitlines() if '=' in line)`. The deployment evidence contains **three** `ExecStartPre` entries, but the [bundle:2705](/run/media/drwho1985/Sandisk/data/beijing-lot/audits/market-sqlite/batch-0003-v1/final-retirement-bundle.json:2705) retains only the last. An independent, in-memory simulation changed the first mount check; verification still returned `INSTALLED_COLLECTOR_REVERIFIED`.
   **Fix:** preserve and compare every command in order; add a regression test changing an earlier entry.

2. **P2 — Deployed implementation identity omits executable package initialization. Confidence: 10/10.**
   [market_retirement_consumers.py:50](/home/drwho1985/.codex/worktrees/0aac/beijing-lot/src/market_retirement_consumers.py:50) checks only `frozen['implementation_hashes']`. The deployed [55-file manifest](/home/drwho1985/.local/lib/beijing-lot/market-capture/sqlite-7fa8d2b9a32c2afe/sqlite-deployment-staging.json:4) omits the existing `src/__init__.py`, which executes when the collector imports `src.market_capture_recovery`. Changes to that initializer therefore escape verification. The final executor’s own initializer protection does not cover this separate deployed copy.
   **Fix:** bind all executed package initializers in the deployment manifest and test initializer mutation.

3. **P2 — Final gates do not revalidate the collector’s epoch inputs. Confidence: 9/10.**
   [market_retirement_final.py:72](/home/drwho1985/.codex/worktrees/0aac/beijing-lot/src/market_retirement_final.py:72) requires registry/index snapshots, but this bundle omits the active collector `plan.json` and `epoch-receipt.json`. The collector gate never reads them, despite the deployment journal carrying an epoch-receipt hash. Simulated changes to these inputs still passed the collector gate. Their **current** hashes and inherited policy match; the defect is undetected subsequent drift.
   **Fix:** freeze and recheck the epoch receipt, its plan, and carried-attempt bindings under the execution locks.

Verification covered the exact 50 issues **110514–110805**, all record payload hashes and **6,066 frozen source inventories**: 2,139,076 quotes, 12,132 captures, 12,173 evidence records and 136 anomalies. Acceptance, retained-audit and backup bindings matched; lengthy full backup scans were not repeated.

I independently checked all **645 unconverted publication sources**, 158,508 rows, the active-index membership, 71 decision/followup documents including frozen archives, 1,944 monitored reference members, and all 707 snapshots. After relocation expansion, no deletion candidate intersected the protected paths. All **5,903 candidate files remain present**. Shared archives are outside the candidate plan and must remain.

The installed policy preserves budget identity, cap **994,386**, ledger and **2-second interval**. Eleven selected read-only tests passed; filesystem-mutating tests were inspected without execution. Lock acquisition, exact-path/hash checks and durable journal/resume logic were reviewed.

**Limits:** live systemd state and inherited environment could not be independently reread because sandbox access to the user bus was denied. No files, approvals or receipts were written; no collection or retirement executor ran.
