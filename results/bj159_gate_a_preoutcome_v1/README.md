# #159 Gate A — selected-baseline WOR cross-N

Outcome-unexposed freeze of the accepted #127 ESP300_GM305_LOWP20 selector for N=2..10 and the fixed #145 Q-informed WOR allocator at M=32/64/128 and seeds 137001/137002/137003. Gate B must consume this package without recomputing identities. Run `python3 freeze_runner.py --output <new-dir>` from a compatible checkout; staging remains beside the output under `.scratch` and never uses `/tmp`.
