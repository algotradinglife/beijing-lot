# Strength draw-only correction test

Scope: 100608–101120, 100 archived issues / 6,547 paired fixtures. The archived strength probabilities do not cover the recent drawdown sample. The input receipt pins the original archive and CSV. This is frozen historical evidence, not a new prospective model.

Fixed blends replace only market draw probability: D=(1-w)q_D+w*p_D, W/L split the remaining mass in the original market ratio. Weights 0/.25/.5/1 are compared without target-based selection. The full strength triplet is a reference arm; archived market×strength draw-grid predictions are a separate legacy arm, not a newly refitted ten-issue policy.

RAW Brier/log loss/Top2: .646064 / 1.068708 / 74.141%. 25% blend: .646386 / 1.069268 / 73.881%. 50%: .646954 / 1.070348 / 73.622%. 100%: .648831 / 1.074591 / 73.637%. Archived grid: .646307 / 1.069183 / 73.927%. None improves these overall metrics. Draw-only Brier also worsens: RAW .196620 versus pure strength .198454.

A descriptive gradient remains within the broad market draw20–30% bin: strength draw bins0–10,10–20,20–30,30–40% show actual draw17.0%(n53),24.5%(n972),27.4%(n5168),32.6%(n270). This may indicate useful ranking information, but does not isolate residual market variation or other confounders. It does not validate a target-label-filled calibration table. Future new mapping would require shared cutoff learning; none is claimed here.

Implementation: r/strength_draw_blend.R, tested by tests/testthat/test-strength-draw-blend.R (11 assertions). It accepts explicit shared Cutoff, validates exact frozen issue clock, rejects target outcome columns and invalid probability/identity/clock data, and preserves W:L. QMD191 is the report entry and uses existing proper-score/paired diagnostics. Independent NumPy replay checks39,282 predictions and six score summaries. Report and receipt include implementation and source hashes. Historical availability limits remain false; no data collection, expert fitting or purchase changes occur.
