# Adhoc input freshness

`scripts/refresh_adhoc_inputs.py` is the one-shot input-correctness gate for
Freeze v0 or direct adhoc PDF generation. Run it immediately before generation:

```bash
uv run python scripts/refresh_adhoc_inputs.py \
  --issue 26078 \
  --db data/derived/500_bjdc/500_bjdc.sqlite
```

The command fetches the official 500 issue page, the Nowscore issue page and
the playid-34 SP XML. It performs all network reads before opening one SQLite
write transaction. The published rows bind:

- explicit timezone-aware UTC collection clocks;
- the three raw-source SHA-256 values and their bounded clock skew;
- the complete `3/1/0` SP vector;
- the official sale cutoff and row sale flags;
- the official `自由过关` marker and Nowscore sale status.

The receipt is written under
`results/adhoc_input_freshness/<issue>/<batch_id>.json`. The batch ID is the
canonical digest of the three source clocks, three source hashes, issue and
parlay modes.

Generation fails closed per match when the batch, source clock, sale cutoff,
three-outcome vector, sale status or parlay evidence is missing or
inconsistent. A complete decision artifact that exceeds the adhoc freshness
limit is still stale and cannot become ready merely because its row membership
is complete.

This command does not tune strategy, schedule future runs, mutate Freeze
ledgers, publish PDFs, send mail, add API/UI fields or authorize purchasing.
