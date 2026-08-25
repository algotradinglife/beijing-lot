#!/usr/bin/env python3
"""Render a source-bound, executed evidence notebook for #396 without Jupyter runtime dependencies."""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
from src.bj396_settlement import verify_package

root = Path(__file__).resolve().parents[1]
package = root / "results" / "bj396_2025_settlement_backfill_v1"
assert package.is_dir(), package
verification = verify_package(package)
decision = json.loads((package / "decision.json").read_text(encoding="utf-8"))
exclusions = pd.read_csv(package / "exclusion_ledger.csv")

cells = [
    {"cell_type": "markdown", "metadata": {}, "source": ["# BJ-DATA-2025-SETTLEMENT-BACKFILL-001\n", "\n", "Source-bound audit of the frozen 2025 500.com settlement recovery.\n"]},
    {"cell_type": "code", "execution_count": 1, "metadata": {}, "source": ["from pathlib import Path\n", "import json\n", "import pandas as pd\n", "from src.bj396_settlement import verify_package\n", "ROOT = Path.cwd()\n", "PACKAGE = ROOT / 'results/bj396_2025_settlement_backfill_v1'\n", "assert PACKAGE.is_dir(), PACKAGE\n"], "outputs": []},
    {"cell_type": "code", "execution_count": 2, "metadata": {}, "source": ["verification = verify_package(PACKAGE)\n", "verification\n"], "outputs": [{"output_type": "execute_result", "execution_count": 2, "metadata": {}, "data": {"text/plain": [repr(verification)]}}]},
    {"cell_type": "code", "execution_count": 3, "metadata": {}, "source": ["decision = json.loads((PACKAGE / 'decision.json').read_text(encoding='utf-8'))\n", "exclusions = pd.read_csv(PACKAGE / 'exclusion_ledger.csv')\n", "print(json.dumps(decision, indent=2))\n", "exclusions.groupby('exclusion_reason').size()\n"], "outputs": [{"output_type": "stream", "name": "stdout", "text": [json.dumps(decision, indent=2) + "\n"]}, {"output_type": "execute_result", "execution_count": 3, "metadata": {}, "data": {"text/plain": [exclusions.groupby("exclusion_reason").size().to_string()]}}]},
    {"cell_type": "markdown", "metadata": {}, "source": ["The package is intentionally **not** strategy-authorized. Its BLOCKED disposition is the reproducible decision input: 23 rows have no native 500.com settlement evidence, while 97 source rows are explicitly marked 改期 (postponed).\n"]},
]
notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11"}}, "nbformat": 4, "nbformat_minor": 5}
out = root / "notebooks" / "bj396_settlement_recovery.ipynb"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(out)
