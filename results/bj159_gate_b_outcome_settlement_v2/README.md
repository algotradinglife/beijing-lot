# #159 Gate B v2

Canonical outcome settlement of the accepted selected-baseline Q-informed WOR cross-N freeze. `M`/`nominal_M` is the frozen reporting label; `effective_M=min(nominal_M,3^N)` is the actual number of distinct tickets and actual stake. Saturated nominal cells are one allocation per identity/seed/effective_M, not duplicate WOR tickets. Replay with `python3 settlement_runner.py --output <new-dir>`; staging is beside the output and never uses `/tmp`.
