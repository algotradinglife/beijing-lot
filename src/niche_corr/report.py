"""HTML report writer for niche correlation + Markowitz analysis.
Re-uses the visual palette of `ANALYSIS_REPORT.html`.
"""
from __future__ import annotations

import os
from html import escape

import numpy as np
import pandas as pd

CSS = """
:root{--bg:#fafaf7;--fg:#1a1a1a;--muted:#666;--accent:#b04a2f;--accent-soft:#f6ebe5;
--warn:#a45a00;--warn-soft:#fdf3e3;--good:#2e6b4a;--good-soft:#e8f1ec;--bad:#8b2424;
--bad-soft:#f6e8e8;--code-bg:#f0ede6;--border:#d8d3c7;--table-border:#c8c2b3;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue","PingFang SC",
"Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.7;color:var(--fg);
background:var(--bg);max-width:980px;margin:0 auto;padding:32px 24px 80px;font-size:16px}
h1{font-size:28px;margin-top:0;border-bottom:2px solid var(--accent);padding-bottom:10px}
h2{font-size:22px;margin-top:40px;color:var(--accent);border-bottom:1px solid var(--border);padding-bottom:6px}
h3{font-size:18px;margin-top:26px}
code{font-family:"SF Mono",Menlo,Consolas,monospace;background:var(--code-bg);padding:1px 5px;border-radius:3px;font-size:13px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
th,td{border:1px solid var(--table-border);padding:6px 10px;text-align:left}
th{background:var(--accent-soft);font-weight:600}
tbody tr:nth-child(even){background:rgba(0,0,0,0.02)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
td.good{color:var(--good);font-weight:600}
td.bad{color:var(--bad);font-weight:600}
.callout{border-left:4px solid var(--accent);background:var(--accent-soft);padding:10px 16px;margin:14px 0;border-radius:0 6px 6px 0}
.callout.warn{border-color:var(--warn);background:var(--warn-soft)}
.callout.good{border-color:var(--good);background:var(--good-soft)}
.callout.bad{border-color:var(--bad);background:var(--bad-soft)}
.callout-title{font-weight:600;margin-bottom:4px}
.meta{color:var(--muted);font-size:14px;margin-bottom:24px}
.tag{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px}
.tag-pass{background:var(--good-soft);color:var(--good)}
.tag-fail{background:var(--bad-soft);color:var(--bad)}
.tag-info{background:var(--accent-soft);color:var(--accent)}
img.fig{max-width:100%;border:1px solid var(--border);border-radius:6px;margin:12px 0;background:#fff}
.footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--border);color:var(--muted);font-size:13px}
"""


def _df_to_html(df: pd.DataFrame, num_cols: list[str] | None = None,
                fmt: dict | None = None) -> str:
    num_cols = num_cols or []
    fmt = fmt or {}
    rows_html = []
    head = "<tr>" + "".join(f"<th>{escape(str(c))}</th>" for c in df.columns) + "</tr>"
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            cls = "num" if c in num_cols else ""
            if c in fmt and pd.notna(v):
                txt = fmt[c](v)
            elif isinstance(v, float) and pd.notna(v):
                txt = f"{v:.4f}"
            else:
                txt = "" if pd.isna(v) else str(v)
            cells.append(f"<td class='{cls}'>{escape(txt)}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return "<table><thead>" + head + "</thead><tbody>" + "".join(rows_html) + "</tbody></table>"


def render_report(out_path: str, *,
                  niche_meta: list[dict],
                  R: pd.DataFrame,
                  corr: pd.DataFrame,
                  cluster_summary: pd.DataFrame,
                  bootstrap_w: pd.DataFrame,
                  efficient_frontier: pd.DataFrame,
                  strategies: dict,
                  fig_paths: dict,
                  caveats: list[str],
                  verdict: str):
    n_weeks = len(R)
    coverage = (R.notna().sum() / n_weeks * 100).round(1)
    coverage_df = pd.DataFrame(dict(
        id=R.columns,
        label=[next((m["label"] for m in niche_meta if m["id"] == nid), nid) for nid in R.columns],
        weeks_with_bet=R.notna().sum().values,
        coverage_pct=coverage.values,
        mean_r=R.mean(axis=0).values,
        std_r=R.std(axis=0).values,
        hit_rate=(R > 0).sum(axis=0).values / R.notna().sum(axis=0).clip(lower=1).values,
    ))

    # Strategy summary
    strat_rows = []
    for key, s in strategies.items():
        strat_rows.append(dict(
            strategy=s["name"],
            CAGR=s["CAGR"], Sharpe=s["Sharpe"],
            MaxDD=s["MaxDD"], Calmar=s["Calmar"],
            final=s["final"],
        ))
    strat_df = pd.DataFrame(strat_rows)

    # Pretty corr table (off-diagonal abs mean)
    C = corr.values.copy()
    n = C.shape[0]
    iu = np.triu_indices(n, k=1)
    off = C[iu]
    off_clean = off[~np.isnan(off)]
    mean_abs = float(np.nanmean(np.abs(off_clean))) if len(off_clean) else float("nan")
    mean_signed = float(np.nanmean(off_clean)) if len(off_clean) else float("nan")

    n_clusters = int(cluster_summary["cluster"].nunique())

    pct_fmt = lambda v: f"{v*100:+.2f}%"
    money_fmt = lambda v: f"¥{v:,.0f}"
    ratio_fmt = lambda v: f"{v:.3f}"

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>Niche Correlation + Markowitz Portfolio Analysis</title>
<style>{CSS}</style></head><body>
<h1>Niche Correlation + Markowitz Portfolio Analysis</h1>
<p class="meta">Inputs: 16 OOS-survived niches from
<code>niche_analysis_real_sp.html</code>; weekly N=3 combo returns built per
niche from <code>data/raw/beidan_full_3sp.csv</code>.</p>

<div class="callout"><div class="callout-title">TL;DR verdict</div>
{escape(verdict)}</div>

<h2>1. Per-niche weekly coverage</h2>
<p>Total weeks in span: <strong>{n_weeks}</strong>. A niche only contributes
in weeks with ≥3 qualifying picks; sparse coverage limits the value of
correlation-based diversification.</p>
{_df_to_html(coverage_df.round(4), num_cols=['weeks_with_bet','coverage_pct','mean_r','std_r','hit_rate'],
             fmt=dict(coverage_pct=lambda v: f"{v:.1f}%",
                      mean_r=pct_fmt, std_r=lambda v: f"{v:.3f}",
                      hit_rate=lambda v: f"{v*100:.1f}%"))}

<h2>2. Pairwise correlation</h2>
<p>Mean off-diagonal correlation: <strong>{mean_signed:+.3f}</strong>;
mean |corr|: <strong>{mean_abs:.3f}</strong>.</p>
<img class="fig" src="figures/{os.path.basename(fig_paths['heatmap'])}" alt="correlation heatmap">

<h2>3. Hierarchical clustering</h2>
<p>Distance = 1 − |corr|; linkage = average; cluster cut at d=0.7.
Independent groups identified: <strong>{n_clusters}</strong>.</p>
{_df_to_html(cluster_summary, num_cols=['cluster'])}
<img class="fig" src="figures/{os.path.basename(fig_paths['dendrogram'])}" alt="dendrogram">

<h2>4. Markowitz portfolio</h2>
<h3>4.1 Efficient frontier</h3>
<img class="fig" src="figures/{os.path.basename(fig_paths['frontier'])}" alt="efficient frontier">

<h3>4.2 Min-variance weights — bootstrap stability (n=200)</h3>
<p>Sparse weekly P&L makes Markowitz weights unstable. The columns below
show the across-bootstrap mean weight and 5/95 percentiles per niche.</p>
{_df_to_html(bootstrap_w.round(4), num_cols=['mean_w','std_w','p05','p95'])}

<h2>5. Backtest (¥100,000 bankroll, 8 yrs, f=2% per week)</h2>
{_df_to_html(strat_df, num_cols=['CAGR','Sharpe','MaxDD','Calmar','final'],
             fmt=dict(CAGR=pct_fmt, Sharpe=ratio_fmt,
                      MaxDD=pct_fmt, Calmar=ratio_fmt,
                      final=money_fmt))}
<img class="fig" src="figures/{os.path.basename(fig_paths['equity'])}" alt="equity curves">

<h2>6. Caveats</h2>
<ul>
{''.join(f'<li>{escape(c)}</li>' for c in caveats)}
</ul>

<div class="footer">Generated by <code>src/niche_corr/</code> on
{escape(pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'))}. Source data:
<code>data/raw/beidan_full_3sp.csv</code>. Niche definitions:
<code>src/niche_corr/niches.py</code>.</div>
</body></html>
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
