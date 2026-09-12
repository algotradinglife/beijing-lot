# Sleeve table interface v1 for #425 / #427

Authoritative projection: `r/n7_sleeve_tables.R::n7_sleeve_tables(bundle,
cutoff_receipt, model_id)`. It accepts a frozen candidate JSON list parsed with
`simplifyVector=FALSE`, that bundle's exact named slot-to-cutoff receipt and an
explicit model identifier. It performs no fitting, allocation, I/O or admission.
Incorrect identity, probabilities, state namespace or cutoff receipts fail.

The output names are `prob_mat`, `payout_hat_mat`, `value_mat`, `rank_idx`,
`summary`, `depth`, `long`. Each matrix has S rows and2,187 canonical columns;
rank_idx contains 1-based column indices. State digits0/1/2 map to official3/1/0.
Sorting never changes the canonical column identity. Empty candidate bundles
are rejected; this is not an empty-admission result.

| Table | Row and unique key | Required consumer fields |
|---|---|---|
| summary | One ordered seven-fixture set; issue + sleeve_id | fixture_slots, fixture_ids, model_id, coverage_16/32/64/128/256/512/2187, top1_state_prob, entropy, state_hhi, top64_expected_gross, top64_expected_roi, source_grade, price_grade, historical_admission, bundle_seal, enumeration_seal, cutoff_receipt |
| depth | One prefix depth; issue + sleeve_id + depth | depth1–2187, ticket_col_idx, ticket_code, cumulative coverage |
| long | One canonical state; issue + sleeve_id + ticket_col_idx | ticket_code, official_outcomes, prob, prob_rank, cum_prob, payout_hat, expected_gross_contribution, selected_rules |

`issue`, fixture IDs, ticket_code and official_outcomes are character identities;
seven-character state strings must retain leading zeros. sleeve_id, depth and
column/rank indices are integers. Probabilities/coverage/ROI are numeric fractions,
not percentages; payout and expected gross are CNY. Entropy is natural-log nats,
HHI dimensionless. `historical_admission` is logical FALSE in this exposed archive.
No missing numeric/identity fields in these tables. Empty selected_rules is a
valid empty string, meaning no selector included that state. Summary-to-depth
and summary-to-long relationships are one-to-many on issue/sleeve_id.

Native QMD134 exports `sleeve-summary.csv`, `state-tables/{issue}-depth.csv.gz`,
`state-tables/{issue}-long.csv.gz` and `state-table-receipt.json` containing all
export hashes, source freeze and R implementation identity. Existing201 exports
are diagnostic evidence, not new causal data. Verify receipt/file hashes before
reading; downstream learning must separately apply shared temporal admission.
Neither #425 nor #427 currently has a native blocking edge to #424; this document
does not invent one or change either issue's lifecycle.

Example after receipt verification, using caller-supplied paths:

```r
summary <- readr::read_csv(summary_path, col_types = readr::cols(
  .default = readr::col_double(), issue = readr::col_character(),
  sleeve_id = readr::col_integer(), origin = readr::col_character(),
  fixture_slots = readr::col_character(), fixture_ids = readr::col_character(),
  model_id = readr::col_character(), source_grade = readr::col_character(),
  price_grade = readr::col_character(), historical_admission = readr::col_logical(),
  bundle_seal = readr::col_character(), enumeration_seal = readr::col_character(),
  cutoff_receipt = readr::col_character()))
depth <- readr::read_csv(depth_path, col_types = readr::cols(
  issue = readr::col_character(), sleeve_id = readr::col_integer(),
  depth = readr::col_integer(), ticket_col_idx = readr::col_integer(),
  ticket_code = readr::col_character(), coverage = readr::col_double()))
stopifnot(nrow(readr::problems(summary)) == 0L,
          nrow(readr::problems(depth)) == 0L,
          !anyDuplicated(summary[c("issue", "sleeve_id")]),
          !anyDuplicated(depth[c("issue", "sleeve_id", "depth")]))
joined <- dplyr::left_join(depth, summary,
  by = c("issue", "sleeve_id"), relationship = "many-to-one")
stopifnot(!anyNA(joined$model_id))
```

The exact long-table CSV types and zero-preserving round trip are executable in
`tests/testthat/test-n7-sleeve-tables.R`, alongside matrix/long equality, rank
identity, monotone depth, C(2187)=1 and malformed-source rejection.

**Do not consume old portfolio `mean_coverage` as a quality primitive.** At or
before db4723d6, 8×64 plans divided summed sleeve coverage by512 instead of8.
For a **Top64 probability-depth quality comparison**, use summary.coverage_64
or depth at64. These describe PROB ordering only; they are not the selected mass
of FRONTIER, VALUE, RANDOM or DIVERSITY subsets. For an actual portfolio average,
join each `(sleeve_id, option)` from its `sleeve_keys` to that exact subset's
canonical state IDs, sum `long.prob` over those states, then average across
sleeves. `selected_rules` contains pipe-delimited exact option membership and can
also locate those states; match complete tokens, not substrings. Check each
selected subset has exactly64 unique states and retain issue/sleeve/option keys
plus a new derived receipt. Do not substitute a Top64 depth curve for a different
selected subset or modify/reseal old frozen plans. Monolithic plans' same
field refers to mean physical-ticket probability, a different observational unit.

Further allocation/calibration work belongs to the independently frozen #425 /
#427 contracts. No expanded threshold, U/P or cap search on the current100 issues
is part of this comment remediation.
