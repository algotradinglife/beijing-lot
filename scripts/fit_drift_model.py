"""Fit + print the SP-drift model (ratio=final_sp/decision_sp by SP-band × MTK).

P1 of plan docs/superpowers/plans/2026-06-24-sp-drift-quantile-mvp.md.
Run:  PYTHONPATH=".:src" .venv/bin/python scripts/fit_drift_model.py
"""
from src.sp_drift import panel as P
from src.sp_drift.drift_model import fit_drift_model

LIVE = "data/beidan_live.db"
CACHE = "data/derived/sp_drift/panel.parquet"


def main():
    pan = P.build(LIVE, cache_path=CACHE, rebuild=True)
    model = fit_drift_model(pan)
    tbl = model.table()
    print(f"panel snapshots={len(pan)}  cells={len(tbl)}  "
          f"global_prior(mean,sd)=({model.global_prior[0]:.3f},"
          f"{model.global_prior[1]:.3f})\n")
    print("ratio = final_sp/decision_sp by (SP-band × MTK-bucket), shrunk to band prior:")
    print("(mean<1 = SP drifts DOWN from decision to close; sd = spread)\n")
    # pivot for readability: rows=band, cols=mtk_bucket
    piv_m = tbl.pivot(index="band", columns="mtk_bucket", values="mean_ratio")
    piv_n = tbl.pivot(index="band", columns="mtk_bucket", values="n")
    band_order = ["<3.5", "3.5-4.5", "4.5-5", "5-8", ">8"]
    bucket_order = ["0-120", "120-360", "360-720", "720-1440", "1440-inf"]
    piv_m = piv_m.reindex(index=[b for b in band_order if b in piv_m.index],
                          columns=[c for c in bucket_order if c in piv_m.columns])
    piv_n = piv_n.reindex(index=piv_m.index, columns=piv_m.columns)
    print("== mean ratio ==")
    print(piv_m.to_string(float_format=lambda x: f"{x:.3f}"))
    print("\n== n per cell ==")
    print(piv_n.to_string(float_format=lambda x: f"{x:.0f}"))
    print("\n== band priors (pooled over MTK) ==")
    for b in band_order:
        if b in model.band_prior:
            m, s = model.band_prior[b]
            print(f"  {b:8} mean={m:.3f} sd={s:.3f}")
    print("\nNote: thin cells shrink toward band prior (k=20). MTK in minutes; "
          "buckets 0-2h / 2-6h / 6-12h / 12-24h / 24h+.")


if __name__ == "__main__":
    main()
