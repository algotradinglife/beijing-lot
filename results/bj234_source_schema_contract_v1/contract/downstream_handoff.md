# Downstream handoff (REQ-DS08)

| Branch | Selected source | admissible_use | evidence |
|---|---|---|---|
| BJ_SP_TIMESERIES #235 | BEIDAN_LIVE_DB | STRICT_CAUSAL | src/live_collector/scraper.py:40-41 (URL_BJDC_500 = https://trade.500.com/bjdc/?expect={issue}); scripts/scrape_500_bjdc.py:47 (LIVE_SP_URL = https://www.500.com/static/public/bjdc/xml/sp/...) |
| INTEGRATION #238 | BEIDAN_500BJDC | STRICT_CAUSAL | src/live_collector/scraper.py:40-41 (URL_BJDC_500 = https://trade.500.com/bjdc/?expect={issue}); scripts/verify_settlements.py:42-64 (zqdc.php per-match scoreboard + wanchang.php date bucket); src/live_collector/scraper.py:44 (URL_KAIJIANG_500 = https://zx.500.com/zqdc/kaijiang.php...) |
| EU_ODDS #236 | ODDS_API_HISTORICAL | RETROSPECTIVE_PROXY | issue contract family 3; coverage evaluation pending |
| POWER_FEATURES #237 | INTERNAL_RESULTS_POWER | SETTLEMENT_ONLY | census identity + settlement sealing (C4) |

## Inputs/interfaces per downstream branch

- **#235 (BJ SP timeseries)**: consume `BEIDAN_LIVE_DB` snapshots (STRICT_CAUSAL, snapshot_ts UTC) + `BEIDAN_500BJDC` raw payload receipts; wire first-party interface when acquired.
- **#236 (EU odds)**: consume `ODDS_API_HISTORICAL` after coverage evaluation + purchase; clock stays RETROSPECTIVE_PROXY until raw receipts and vendor clock are independently proven.
- **#237 (power features)**: consume `INTERNAL_RESULTS_POWER` (SETTLEMENT_ONLY) with `(issue_code, match_idx)` identity mapping.
- **#238 (integration)**: consume the canonical schema package itself (`BEIDAN_500BJDC` receipts for replay provenance).
