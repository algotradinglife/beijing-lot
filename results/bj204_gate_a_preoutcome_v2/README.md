# #204 Gate A v2 — market-anchored residual model preregistration

This immutable package is **outcome-unexposed**.  It uses the #203 inference
namespace only for development/CV through issue `25042`.
The one-shot retrospective window is `25043–25125` plus `26011–26049`; it is
represented by a clearly graded `RETROSPECTIVE_PROXY` market panel.  Issues `26051+`
remain reserved for #210.

`predicted_final_sp` is a pre-event proxy input, not a target.  The supervised
SP target is the official 3/1/0 final-SP vector under
`TARGET_ONLY_OFFICIAL_3SP_NOT_OPENED_GATE_A` and is not opened here.  The target-only census
records the known post-kickoff update prevalence precisely to prevent a
retrospective proxy from being misrepresented as a live capture.

The hard action gate is `BJ204_MARKET_OR_NO_BET_V1`: an incomplete/nonfinite
proxy row uses a valid frozen market vector if one exists; otherwise it is
`NO_BET_FROZEN`.  Gate B requires PI acceptance of this exact package.
