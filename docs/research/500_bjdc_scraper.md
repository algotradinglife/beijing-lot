# 500 BJDC Scraper

`scripts/scrape_500_bjdc.py` captures Beijing single-game football data from 500.com.

## Data Surfaces

- Historical HTML: `https://trade.500.com/bjdc/index.php?expect=<issue>`
- Live SP XML: `https://www.500.com/static/public/bjdc/xml/sp/just_<issue>_34.xml`

The historical page exposes issue, match index, 500 `fid`, league, teams, cutoff time, handicap, score, winning option, winning SP, visible SP values, and average European odds. If the page shows all three SP values after a score is known, the scraper infers the result from `score + handicap_line` and then selects the matching SP. The live XML can be polled for visible SP snapshots.

## Examples

Refresh the issue list:

```bash
python3 scripts/scrape_500_bjdc.py --list-only
```

Scrape a few historical issues:

```bash
python3 scripts/scrape_500_bjdc.py --issue 25042 --issue 140101 --issue 100101 --force --sleep 0
```

Scrape 2014+ into the default ignored SQLite DB:

```bash
python3 scripts/scrape_500_bjdc.py --all --year-from 2014 --force
```

Capture the current issue plus live SP XML:

```bash
python3 scripts/scrape_500_bjdc.py --issue 26068 --live-sp --force
```

Validate a small historical sample:

```bash
python3 scripts/scrape_500_bjdc.py \
  --db data/derived/500_bjdc/scraper_validation.sqlite \
  --issue 26068 --issue 25042 --issue 24011 --issue 140101 --issue 100101 --issue 070502 \
  --live-sp --force --sleep 0 --keep-going
```

Default DB:

```text
data/derived/500_bjdc/500_bjdc.sqlite
```

## Tables

- `issues`: issue ids exposed by 500.com, newest first.
- `matches`: parsed historical/current rows from the trade HTML.
- `live_sp_snapshots`: current XML SP snapshots.
- `fetch_log`: request audit trail and parser row counts.

## Caveats

- Historical settled pages usually expose only the winning option's official SP; non-winning official final SP values are not available there.
- Active rows expose visible SP for all three outcomes, but those are current display values, not guaranteed final settlement SP.
- Very old issues can have scores without winning SP. Sampling showed 2010+ and 2014+ are much more reliable than 2007-era pages, but a full coverage audit is still required before using the data for PnL research.
- Some cancelled/disabled rows have no score; these rows cannot be assigned a result or winning SP.

## Validation Snapshot

Validation on 2026-06-26 against six representative issues:

| issue | rows | rows with result | rows with winning SP | rows with score |
| --- | ---: | ---: | ---: | ---: |
| 070502 | 31 | 31 | 0 | 31 |
| 100101 | 78 | 66 | 66 | 66 |
| 140101 | 145 | 137 | 137 | 137 |
| 24011 | 114 | 112 | 112 | 112 |
| 25042 | 476 | 475 | 475 | 475 |
| 26068 | 24 | 17 | 17 | 17 |

The same run found XML rows for 2010, 2014, 2024, 2025, and 2026 issues; 2007 returned 404. For 2010/2014 the XML had rows but no source update timestamp, so coverage and field quality still need a full audit before using these snapshots as SP drift training data.
