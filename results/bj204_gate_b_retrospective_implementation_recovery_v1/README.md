# #204 Gate B — market-residual retrospective implementation recovery

Gate-A manifest: `dfa14d42410d5513cbb07f832972e47fa1cf819a6f1eece13e1f92106e096ae1`

The former Gate-B v1 is invalid because the frozen residual/fallback/selection/model-name corrections were not applied. This is the single PI-authorized mechanical RETROSPECTIVE_IMPLEMENTATION_RECOVERY. It contains no ticket, ROI, production, or betting decision.

## Replay

```bash
PYTHONPATH=src python scripts/run_bj204_gate_b.py run \
  --package results/bj204_gate_a_preoutcome_v5 \
  --full-3sp-source data/raw/beidan_full_3sp.csv \
  --output results/bj204_gate_b_retrospective_implementation_recovery_v1
```
