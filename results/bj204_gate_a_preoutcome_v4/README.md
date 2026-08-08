# #204 Gate A v4 — market-anchored residual model preregistration

This immutable package is **outcome-unexposed**.  It uses the #203 inference
namespace only for development/CV through issue `25042`.
The one-shot retrospective window is `25043–25125` plus `26011–26049`; it is
represented by a clearly graded `RETROSPECTIVE_PROXY` market panel.  Issues `26051+`
remain reserved for #210.

The common `X_i[J_i,3,F]` adapter is materialized for both development and
test in `common_cell_features.parquet` plus `common_cell_masks.parquet`.
Development uses the identity-bridged p_close proxy; the test side uses
normalized average-EU. Source-grade fields and coverage tables make that
transition explicit. `predicted_final_sp_input` is a pre-event proxy input,
not a target. The supervised
SP target is the official 3/1/0 final-SP vector under
`TARGET_ONLY_OFFICIAL_3SP_NOT_OPENED_GATE_A` and is not opened here.  The target-only census
records the known post-kickoff update prevalence precisely to prevent a
retrospective proxy from being misrepresented as a live capture.

`market_proxy_pclose_bridge.csv` freezes the normalized-inverse-average-EU to
`p_close` source transition on 20,837 complete historical overlaps. It joins
only `issue + match_idx` and official `match_uid` identifiers, retains source
grades, publishes the delta distribution, and never treats the vendors as
byte-identical. Missing/reference-outlier handling is preregistered in the
bridge summary; no official result or SP value is read.

The hard action gate is `BJ204_MARKET_OR_NO_BET_V1`: an incomplete/nonfinite
proxy row uses a valid frozen market vector if one exists; otherwise it is
`NO_BET_FROZEN`.  Gate B requires PI acceptance of this exact package.
