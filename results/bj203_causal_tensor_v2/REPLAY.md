# Deterministic replay

Create and use the repository's pinned environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PY=.venv/bin/python
$PY scripts/build_bj203_causal_tensor.py verify --package results/bj203_causal_tensor_v2
$PY scripts/build_bj203_causal_tensor.py verify-superseded   --package results/bj203_causal_tensor_v1
$PY scripts/execute_bj203_notebook.py

# Clean detached inference replay without the 6.8 GB runtime database.
# Replace the output placeholder with any new empty directory:
$PY scripts/build_bj203_causal_tensor.py build-inference \
  --output <empty-replay-directory> \
  --identity-extension results/bj203_causal_tensor_v2/sources/unavailable_match_identity.parquet \
  --heldout-identity-extension results/bj203_causal_tensor_v2/sources/heldout_match_identity.parquet
$PY scripts/build_bj203_causal_tensor.py compare-inference \
  --frozen results/bj203_causal_tensor_v2 \
  --replay <empty-replay-directory>
```

The comparison command requires an exact file census and byte identity for every
inference, source, audit, schema and feature-dictionary artifact. Label generation
is intentionally a separate command that requires the exact read-only runtime
database and excludes held-out issues in its SQL query.
