# #137 Gate A: complete-issue probability sampling freeze

This immutable package freezes only pre-outcome selector, market-calibration, identity, and sampler inputs. Gate B is not authorized. Replay with `python3 freeze_runner.py --output <new-dir>`; temporary staging is created beside the output, never in `/tmp`.
