# REPLAY — exact reproduction commands

Run from a checkout of the branch that produced this package (the commands
use `python3` on the repo's venv; `DATA_ROOT` defaults to the census data
root, override with `DATA_ROOT=/path/to/data`).

```bash
# 1. fresh census + build (read-only on sources)
python3 scripts/build_bj234_source_schema.py build

# 2. full semantic verify (must print VERIFIED)
python3 scripts/build_bj234_source_schema.py verify

# 3. focused + full tests (tests never write the committed package — E1)
python3 -m pytest tests/test_bj234_source_schema.py -q

# 4. notebook clean-run
python3 scripts/execute_bj234_notebook.py
```

Package target: `/home/drwho1985/beijing-lot-234-r2/results/bj234_source_schema_contract_v1` (relative to repo root).
