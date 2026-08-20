# #248 source-retention and cross-source probe

Date: 2026-08-19. This is a capability report, not a live-data claim.

## Verified by committed parser/tests

- Nowscore issue URL shape is `DanChang.aspx?all=1&TypeID=5&issueNum={issue}`.
- The issue-row parser records source match key, native handicap, sale flag,
schedule/kickoff text and `sp_url`.
- Per-match source URL shape is `sp/danchang/{issue}_{match_idx}_5.html`.
- The parser fails closed unless the page title includes `Sp值变化表` and the
header is exactly `胜 / 平 / 负 / 变化时间`; it rejects incomplete, non-finite,
<=1 and 0.65 vectors.
- Change times are inferred only against the fixture kickoff and rejected when
not strictly pre-kickoff or more than 45 days before it.

## Unverified candidates requiring observation

- Source retention horizon and whether every active issue remains retrievable.
- Page update frequency versus source change time.
- Agreement between Nowscore native handicap/SP and 500/ZGZCW cross-checks.
- Availability of Nowscore Asian/total pages for every canonical fixture.

500/ZGZCW are intentionally not used to fill the primary Nowscore lane. A
future cross-source comparison should publish one-to-one identity candidate
bounds (issue + match index + pre-event schedule/team tuple), coverage, line
agreement, SP deltas and all unmatched/ambiguous rows. It must not fuzzy-join or
collapse duplicates. `bjlot.cn` remains excluded pending separate qualification.
