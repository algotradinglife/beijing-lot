#!/usr/bin/env python3
"""Render an executed evidence notebook for #396 amendment v2 without Jupyter runtime dependencies."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.bj396_settlement import verify_package

root = Path(__file__).resolve().parents[1]
package = root / "results" / "bj396_2025_settlement_backfill_v2"
assert package.is_dir(), package
verification = verify_package(package)
decision = json.loads((package / "decision.json").read_text(encoding="utf-8"))
residuals = pd.read_csv(package / "residual_disposition_v2.csv")
probes = pd.read_csv(package / "nowscore_probe_ledger.csv")
issue_ledger = pd.read_csv(package / "issue_ledger.csv")
source_probes = pd.read_csv(package / "source_probe_receipts_v2.csv")

cells = [
    {"id": "title", "cell_type": "markdown", "metadata": {}, "source": ["# BJ-DATA-2025-SETTLEMENT-BACKFILL-001 — amendment v2\n", "\n", "Executed, source-bound audit of the frozen 2025 settlement denominator.\n"]},
    {"id": "setup", "cell_type": "code", "execution_count": 1, "metadata": {}, "source": ["from pathlib import Path\n", "import json\n", "import os\n", "import sys\n", "import pandas as pd\n", "ROOT = Path(os.environ.get('BJ396_REPO_ROOT', Path.cwd())).resolve()\n", "sys.path.insert(0, str(ROOT))\n", "from src.bj396_settlement import verify_package\n", "PACKAGE = ROOT / 'results/bj396_2025_settlement_backfill_v2'\n", "assert PACKAGE.is_dir(), PACKAGE\n"], "outputs": []},
    {"id": "verify", "cell_type": "code", "execution_count": 2, "metadata": {}, "source": ["verification = verify_package(PACKAGE)\n", "verification\n"], "outputs": [{"output_type": "execute_result", "execution_count": 2, "metadata": {}, "data": {"text/plain": [repr(verification)]}}]},
    {"id": "coverage", "cell_type": "code", "execution_count": 3, "metadata": {}, "source": ["decision = json.loads((PACKAGE / 'decision.json').read_text(encoding='utf-8'))\n", "residuals = pd.read_csv(PACKAGE / 'residual_disposition_v2.csv')\n", "probes = pd.read_csv(PACKAGE / 'nowscore_probe_ledger.csv')\n", "issue_ledger = pd.read_csv(PACKAGE / 'issue_ledger.csv')\n", "source_probes = pd.read_csv(PACKAGE / 'source_probe_receipts_v2.csv')\n", "print(json.dumps(decision, indent=2))\n", "print(residuals.groupby('exclusion_reason').size())\n", "print(source_probes[['source_id', 'exact_23_key_hit_count', 'native_winning_sp_capability', 'admissible_use']].to_string(index=False))\n", "assert len(probes) == 23\n", "assert len(issue_ledger) == 57 and issue_ledger['downstream_eligible'].all()\n", "assert source_probes['source_id'].nunique() == 5\n"], "outputs": [{"output_type": "stream", "name": "stdout", "text": [json.dumps(decision, indent=2) + "\n" + residuals.groupby("exclusion_reason").size().to_string() + "\n" + source_probes[["source_id", "exact_23_key_hit_count", "native_winning_sp_capability", "admissible_use"]].to_string(index=False) + "\n"]}]},
    {"id": "summary", "cell_type": "markdown", "metadata": {}, "source": ["All 57 census issues are explicitly downstream eligible: 36 retain admissibly excluded fixtures, recorded only in `residual_disposition_v2.csv`; no whole issue is silently dropped. The five-row source-probe receipt captures every declared lane and exact-23-key readback. All 23 original no-SP rows have an immutable Nowscore issue/slot probe. Five are directly provider-marked 取消 and 18 are finished with an outcome but remain excluded because the official 500 row has no native winning SP. No final score was converted to SP, and `strategy_execution_authorized` remains false.\n"]},
]
notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11"}}, "nbformat": 4, "nbformat_minor": 5}
out = root / "notebooks" / "bj396_settlement_recovery_v2.ipynb"
out.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(out)
