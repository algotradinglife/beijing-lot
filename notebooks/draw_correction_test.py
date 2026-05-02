"""Verify whether the proposed simple draw correction reduces the
calibration error on the integer-line probabilities.

If yes, Phase 1 should ship with the correction. If the correction is
heterogeneous (different for different probability buckets), we need
Dixon-Coles τ instead.
"""
import numpy as np
import pandas as pd

df = pd.read_csv("/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/big5_int_line_predictions.csv")
print(f"Rows: {len(df)}")

# Realized counts
y3 = (df["realized"] == 3).astype(int)
y1 = (df["realized"] == 1).astype(int)
y0 = (df["realized"] == 0).astype(int)


def metrics(p3, p1, p0, label):
    eps = 1e-9
    p3 = p3.clip(eps, 1-eps); p1 = p1.clip(eps, 1-eps); p0 = p0.clip(eps, 1-eps)
    brier = ((y3 - p3)**2 + (y1 - p1)**2 + (y0 - p0)**2).mean()
    ll = -(y3*np.log(p3) + y1*np.log(p1) + y0*np.log(p0)).mean()
    print(f"{label:30s}  Brier={brier:.5f}  LogLoss={ll:.5f}  "
          f"meanP1={p1.mean():.4f}  meanP3={p3.mean():.4f}  meanP0={p0.mean():.4f}")
    return brier, ll


# Baseline (no correction)
p3, p1, p0 = df["p3_int"], df["p1_int"], df["p0_int"]
metrics(p3, p1, p0, "no correction (raw)")

# Constant additive correction (proportional to residuals)
# Residuals: p1 +2.8pp, p3 -2.2pp, p0 -0.6pp (sum to 0)
delta = np.array([-0.022, +0.028, -0.006])
p3c = (p3 + delta[0]).clip(0, 1)
p1c = (p1 + delta[1]).clip(0, 1)
p0c = (p0 + delta[2]).clip(0, 1)
total = p3c + p1c + p0c
p3c, p1c, p0c = p3c/total, p1c/total, p0c/total
metrics(p3c, p1c, p0c, "constant additive correction")

# Multiplicative correction (boost p1 by factor 1.10, scale others)
boost = 0.275 / df["p1_int"].mean()
p1m = df["p1_int"] * boost
remain = (1 - p1m).clip(0, 1)
old_remain = df["p3_int"] + df["p0_int"]
p3m = remain * df["p3_int"] / old_remain
p0m = remain * df["p0_int"] / old_remain
metrics(p3m, p1m, p0m, "scale p1 to match overall")

# DC-style: shift mass from p3+p0 to p1 proportional to current p1 (more correction
# where p1 is already higher, since residual grows with p1)
shift_frac = 0.10  # take 10% of (p3+p0) and reallocate to p1
p1d = df["p1_int"] + shift_frac * (df["p3_int"] + df["p0_int"]) * 0.5  # symmetric shift
# normalize: but we only want to add — re-balance instead
add = shift_frac * (df["p3_int"] + df["p0_int"]) * (df["p1_int"] / (df["p3_int"] + df["p0_int"] + df["p1_int"]))
p1d = df["p1_int"] + add
p3d = df["p3_int"] - add * (df["p3_int"] / (df["p3_int"] + df["p0_int"]))
p0d = df["p0_int"] - add * (df["p0_int"] / (df["p3_int"] + df["p0_int"]))
metrics(p3d, p1d, p0d, "DC-like proportional shift")

# Bucketed analysis: residual by predicted-p1 bucket
df["p1_bin"] = pd.cut(df["p1_int"], bins=np.arange(0.20, 0.36, 0.02))
print("\nResidual by p1 bucket (helps decide if constant or DC-style is right):")
print(df.groupby("p1_bin", observed=True).apply(
    lambda x: pd.Series({
        "n": len(x),
        "mean_pred_p1": x["p1_int"].mean(),
        "rate_p1": (x["realized"] == 1).mean(),
        "residual": (x["realized"] == 1).mean() - x["p1_int"].mean(),
    }), include_groups=False
))
