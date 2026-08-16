"""Figure generation for Issue #229 — every figure is a rendering of a
committed machine-readable table.

The contract requires "plots backed by machine-readable committed tables".
The durable evidence is the CSV/Parquet table; the PNG below is a rendering
of that table for the executed notebook and the report.  No figure invents
data: each ``*_figure(...)`` function reads one committed table and renders
it with matplotlib.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import contract, publication  # noqa: E402

FIG_WIDTH = 10
FIG_HEIGHT = 5


def _save(figure: plt.Figure, directory: Path, name: str) -> Path:
    target = directory / name
    publication.atomic_save_figure(figure, target, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return target


def _placeholder(directory: Path, name: str, message: str) -> Path:
    figure, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    axis.text(0.5, 0.5, message, ha="center", va="center", wrap=True)
    axis.set_axis_off()
    figure.tight_layout()
    return _save(figure, directory, name)


def _vector_columns(
    frame: pd.DataFrame, representation: str
) -> pd.DataFrame:
    """Explode a list-typed representation column into 3/1/0 columns."""
    available = frame[representation].apply(
        lambda v: isinstance(v, (list, tuple, np.ndarray)) and len(v) == 3
    )
    rows = []
    for _, value in frame.loc[available, representation].items():
        rows.append(np.asarray(value, dtype=np.float64))
    if not rows:
        return pd.DataFrame()
    vectors = np.vstack(rows)
    return pd.DataFrame(
        vectors, columns=[f"{representation}_{c}" for c in contract.OUTCOME_CODES]
    )


def census_figure(table: pd.DataFrame, directory: Path) -> Path:
    """Census by cohort: cells per year stacked by cohort."""
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    pivot = table.pivot_table(
        index="year", columns="cohort", values="cells", aggfunc="sum", fill_value=0
    )
    pivot.plot(kind="bar", stacked=True, ax=axis)
    axis.set_title("Cell census by year and cohort")
    axis.set_xlabel("year")
    axis.set_ylabel("cells")
    fig.tight_layout()
    return _save(fig, directory, "census_by_cohort.png")


def missingness_figure(table: pd.DataFrame, directory: Path) -> Path:
    """Missingness matrix bar chart."""
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    order = table.sort_values("missing_fraction", ascending=False)
    axis.barh(order["representation"], order["missing_fraction"])
    axis.set_title("Missingness fraction by probability representation")
    axis.set_xlabel("missing fraction")
    axis.set_xlim(0, 1)
    fig.tight_layout()
    return _save(fig, directory, "missingness_matrix.png")


def intersection_figure(table: pd.DataFrame, directory: Path) -> Path:
    """Intersection coverage bar chart."""
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    order = table.sort_values("cell_count", ascending=False)
    axis.barh(order["intersection"], order["cell_count"])
    axis.set_title("Intersection coverage (cells)")
    axis.set_xlabel("cells")
    fig.tight_layout()
    return _save(fig, directory, "intersection_coverage.png")


def probability_distribution_figure(
    table: pd.DataFrame, representation: str, directory: Path
) -> Path:
    """Per-outcome distribution of one representation (median + box)."""
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    parts = []
    labels = []
    for code in contract.OUTCOME_CODES:
        column = f"{representation}_{code}"
        if column not in table.columns:
            continue
        values = pd.to_numeric(table[column], errors="coerce").dropna()
        parts.append(values)
        labels.append(f"outcome {code}")
    if not parts or not any(len(values) for values in parts):
        plt.close(fig)
        return _placeholder(
            directory,
            f"prob_dist_{representation}.png",
            f"No causally available {representation} values",
        )
    axis.boxplot(parts, tick_labels=labels)
    axis.set_title(f"Distribution of {representation}")
    axis.set_ylabel("probability")
    fig.tight_layout()
    return _save(fig, directory, f"prob_dist_{representation}.png")


def eu_vs_bj_scatter_figure(table: pd.DataFrame, directory: Path) -> Path:
    """EU-vs-BJ scatter by native line (from the committed scatter table)."""
    if table.empty:
        return _placeholder(directory, "eu_vs_bj_scatter.png", "No causal EU/Q_BJ overlap")
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    for outcome in table["outcome"].unique():
        sub = table[table["outcome"] == outcome]
        axis.scatter(sub["qbj_prob"], sub["source_prob"], s=3, alpha=0.3, label=f"outcome {outcome}")
    limits = [0, 1]
    axis.plot(limits, limits, "k--", linewidth=0.8)
    axis.set_xlim(limits)
    axis.set_ylim(limits)
    axis.set_xlabel("Q_BJ_CALIBRATED probability")
    axis.set_ylabel("EU probability (BJ-line space)")
    axis.set_title("EU vs BJ calibrated probability by line")
    axis.legend(markerscale=4)
    fig.tight_layout()
    return _save(fig, directory, "eu_vs_bj_scatter.png")


def power_vs_bj_scatter_figure(table: pd.DataFrame, directory: Path) -> Path:
    """POWER-vs-BJ scatter by native line."""
    if table.empty:
        return _placeholder(directory, "power_vs_bj_scatter.png", "No causal POWER/Q_BJ overlap")
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    for outcome in table["outcome"].unique():
        sub = table[table["outcome"] == outcome]
        axis.scatter(sub["qbj_prob"], sub["source_prob"], s=3, alpha=0.3, label=f"outcome {outcome}")
    limits = [0, 1]
    axis.plot(limits, limits, "k--", linewidth=0.8)
    axis.set_xlim(limits)
    axis.set_ylim(limits)
    axis.set_xlabel("Q_BJ_CALIBRATED probability")
    axis.set_ylabel("POWER probability (BJ-line space)")
    axis.set_title("POWER vs BJ calibrated probability by line")
    axis.legend(markerscale=4)
    fig.tight_layout()
    return _save(fig, directory, "power_vs_bj_scatter.png")


def agreement_figure(table: pd.DataFrame, directory: Path) -> Path:
    """EU/POWER direction agreement matrix heatmap."""
    direction = table[table["table"] == "direction_matrix"]
    if direction.empty:
        return _placeholder(directory, "direction_agreement.png", "No causal EU/POWER divergence overlap")
    pivot = direction.pivot_table(
        index="divergence_eu_direction",
        columns="divergence_power_direction",
        values="cells",
        aggfunc="sum",
        fill_value=0,
    )
    fig, axis = plt.subplots(figsize=(6, 5))
    image = axis.imshow(pivot.to_numpy(dtype=float), cmap="Blues")
    axis.set_xticks(range(len(pivot.columns)), pivot.columns)
    axis.set_yticks(range(len(pivot.index)), pivot.index)
    axis.set_xlabel("POWER direction")
    axis.set_ylabel("EU direction")
    axis.set_title("EU/POWER direction agreement matrix")
    fig.colorbar(image, ax=axis)
    fig.tight_layout()
    return _save(fig, directory, "direction_agreement.png")


def drift_figure(table: pd.DataFrame, directory: Path) -> Path:
    """Chronological causal coverage for every probability source."""
    if table.empty:
        return _placeholder(directory, "drift.png", "No drift rows")
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    for representation, group in table.groupby("representation"):
        by_year = group.groupby("year", as_index=False)["causal_coverage_fraction"].mean()
        axis.plot(
            by_year["year"].astype(str), by_year["causal_coverage_fraction"],
            "o-", label=representation,
        )
    axis.set_ylim(0, 1.05)
    axis.set_xlabel("year")
    axis.set_ylabel("causal coverage fraction")
    axis.set_title("Chronological causal availability by probability source")
    axis.legend(fontsize=7)
    fig.tight_layout()
    return _save(fig, directory, "drift.png")


def exclusion_figure(table: pd.DataFrame, directory: Path) -> Path:
    """Exclusion summary horizontal bar chart."""
    if table.empty or "reason_code" not in table.columns:
        return _placeholder(directory, "exclusion_summary.png", "No exclusions")
    order = table.sort_values("count", ascending=False)
    fig, axis = plt.subplots(figsize=(10, max(4, 0.4 * len(order))))
    axis.barh(order["reason_code"], order["count"])
    axis.set_title("Exclusion ledger summary by reason code")
    axis.set_xlabel("count")
    fig.tight_layout()
    return _save(fig, directory, "exclusion_summary.png")


def simplex_figure(frame: pd.DataFrame, representation: str, directory: Path) -> Path:
    """Three-outcome simplex (barycentric) view of one representation.

    Uses the standard equilateral-triangle projection; the machine-readable
    source is the same cell frame used by every other profiling view.
    """
    columns = _vector_columns(frame, representation)
    if columns.empty:
        return _placeholder(directory, f"simplex_{representation}.png", "No raw probability vectors")
    a = pd.to_numeric(columns[f"{representation}_3"], errors="coerce").to_numpy()
    b = pd.to_numeric(columns[f"{representation}_1"], errors="coerce").to_numpy()
    c = pd.to_numeric(columns[f"{representation}_0"], errors="coerce").to_numpy()
    valid = np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    a, b, c = a[valid], b[valid], c[valid]
    if len(a) == 0:
        return _placeholder(directory, f"simplex_{representation}.png", "No finite probability vectors")
    x = 0.5 * (2 * b + c) / (a + b + c + 1e-12)
    y = (np.sqrt(3) / 2) * c / (a + b + c + 1e-12)
    fig, axis = plt.subplots(figsize=(6, 6))
    axis.scatter(x, y, s=1, alpha=0.15, rasterized=True)
    triangle_x = [0.0, 1.0, 0.5, 0.0]
    triangle_y = [0.0, 0.0, np.sqrt(3) / 2, 0.0]
    axis.plot(triangle_x, triangle_y, "k-", linewidth=0.8)
    axis.text(0.0, -0.04, "3 (home)", ha="center")
    axis.text(1.0, -0.04, "1 (draw)", ha="center")
    axis.text(0.5, np.sqrt(3) / 2 + 0.03, "0 (away)", ha="center")
    axis.set_xlim(-0.1, 1.1)
    axis.set_ylim(-0.1, np.sqrt(3) / 2 + 0.1)
    axis.set_aspect("equal")
    axis.axis("off")
    axis.set_title(f"Three-outcome simplex: {representation}")
    fig.tight_layout()
    return _save(fig, directory, f"simplex_{representation}.png")


def calibration_figure(table: pd.DataFrame, directory: Path) -> Path:
    """Development-only reliability/calibration plot (from committed table)."""
    if table.empty:
        return _placeholder(directory, "development_only_calibration.png", "No causal development-label overlap")
    available = table[table["status"] == "AVAILABLE"].dropna(
        subset=["mean_prob", "observed_freq"]
    )
    if available.empty:
        return _placeholder(directory, "development_only_calibration.png", "No causal development-label overlap")
    fig, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    for (representation, outcome), group in available.groupby(["representation", "outcome"]):
        axis.plot(
            group["mean_prob"], group["observed_freq"], "o-",
            label=f"{representation}:{outcome}", linewidth=0.8, markersize=3,
        )
    axis.plot([0, 1], [0, 1], "k--", linewidth=0.8, label="perfect")
    axis.set_xlabel("mean predicted probability (Q_BJ_CALIBRATED, dev <=2023)")
    axis.set_ylabel("observed outcome frequency")
    axis.set_title("Development-only reliability by probability source/outcome")
    axis.legend(fontsize=6, ncol=2)
    fig.tight_layout()
    return _save(fig, directory, "development_only_calibration.png")


def statistic_figure(
    table: pd.DataFrame, directory: Path, name: str, title: str
) -> Path:
    if table.empty:
        return _placeholder(directory, name, "Unavailable: no causal support")
    value_column = "value" if "value" in table else None
    label_column = "stat" if "stat" in table else "quantile" if "quantile" in table else None
    if value_column is None or label_column is None:
        return _placeholder(directory, name, "Machine-readable receipt has no plottable values")
    values = pd.to_numeric(table[value_column], errors="coerce")
    valid = values.notna()
    if not valid.any():
        return _placeholder(directory, name, "Unavailable: no finite metric values")
    figure, axis = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    axis.bar(table.loc[valid, label_column].astype(str), values.loc[valid])
    axis.tick_params(axis="x", rotation=30)
    axis.set_title(title)
    figure.tight_layout()
    return _save(figure, directory, name)


def write_all_figures(
    tables: dict[str, pd.DataFrame],
    cells: pd.DataFrame,
    directory: Path,
) -> list[Path]:
    """Render every required figure from committed tables into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if "census_by_cohort" in tables:
        written.append(census_figure(tables["census_by_cohort"], directory))
    if "missingness_matrix" in tables:
        written.append(missingness_figure(tables["missingness_matrix"], directory))
    if "intersection_coverage" in tables:
        written.append(intersection_figure(tables["intersection_coverage"], directory))
    distribution_keys = {
        contract.Q_BJ_CALIBRATED: "probability_distribution_qbj_calibrated",
        contract.Q_EU_BJLINE: "probability_distribution_eu_bjline",
        contract.P_POWER_BJLINE: "probability_distribution_power",
        contract.Q_EU_RAW_1X2: "probability_distribution_eu_raw",
        contract.Q_BJ_SP_DEVIG: "probability_distribution_sp_devig",
    }
    for representation, key in distribution_keys.items():
        table = tables.get(key)
        if table is not None:
            written.append(
                probability_distribution_figure(table, representation, directory)
            )
        written.append(simplex_figure(cells, representation, directory))
    if "eu_vs_bj_scatter_table" in tables:
        written.append(eu_vs_bj_scatter_figure(tables["eu_vs_bj_scatter_table"], directory))
    if "power_vs_bj_scatter_table" in tables:
        written.append(power_vs_bj_scatter_figure(tables["power_vs_bj_scatter_table"], directory))
    if "direction_agreement_matrix" in tables:
        written.append(agreement_figure(tables["direction_agreement_matrix"], directory))
    if "drift_table" in tables:
        written.append(drift_figure(tables["drift_table"], directory))
    if "exclusion_summary" in tables:
        written.append(exclusion_figure(tables["exclusion_summary"], directory))
    if "development_only_calibration" in tables:
        written.append(calibration_figure(tables["development_only_calibration"], directory))
    if "divergence_magnitude_tail" in tables:
        written.append(
            statistic_figure(
                tables["divergence_magnitude_tail"], directory,
                "divergence_tail.png", "Causal divergence magnitude tail",
            )
        )
    if "predicted_sp_vs_settlement_sp" in tables:
        written.append(
            statistic_figure(
                tables["predicted_sp_vs_settlement_sp"], directory,
                "predicted_sp_vs_settlement_sp.png", "Predicted vs settlement SP diagnostics",
            )
        )
    return written
