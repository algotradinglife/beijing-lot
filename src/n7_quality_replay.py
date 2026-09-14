"""Independent NumPy replay of #453's fixed, label-free quality selectors.

This is verification, not a historical fitting or chronology implementation.
The supplied cutoff map must equal the frozen scenario map. Inputs are frozen
R option records and 0/1 scenario matrices; returned option indices are R's
one-based indices in selection order. No IO, random sampling or side effects.
"""

import numpy as np


def validate_quality_manifest(receipt):
    """Require the complete 200-issue prediction artifact manifest; no IO."""
    if len(receipt.get("cutoffs", {})) != 200:
        raise ValueError("expected 200 cutoff-bound issues")
    seeds = receipt.get("config", {}).get("seeds")
    if seeds != [42501, 42502, 42503]:
        raise ValueError("unexpected fixed seeds")
    required = {"predictions.csv", "funded.csv", "actions.csv", "candidates.csv"}
    required.update(f"replay-{issue}-{seed}.json.gz"
                    for issue in receipt["cutoffs"] for seed in seeds)
    files = receipt.get("files", {})
    if not required.issubset(files) or any(
            not isinstance(files[name], str) or len(files[name]) != 64
            or any(c not in "0123456789abcdef" for c in files[name]) for name in required):
        raise ValueError("missing or invalid frozen artifact hashes")
    return required


def validate_quality_funded(snapshot, selected, records):
    """Bind every funded prefix/copy/amount to its replayed option; no IO."""
    if len(selected) != len(records):
        raise ValueError("funded group count differs")
    fields = {"depth": "depth", "copies": "unit_copies", "stake": "stake",
              "coverage": "coverage", "expected_gross": "expected_gross"}
    for j, record in zip(selected, records):
        option = snapshot["options"][j - 1]
        if record["sleeve_id"] != option["sleeve_id"]:
            raise ValueError("funded group identity differs")
        for field, source in fields.items():
            if not np.isclose(record[field], option[source], rtol=1e-12, atol=1e-12):
                raise ValueError(f"funded prefix differs: {field}")


def replay_quality(snapshot, cutoff, budget, fraction, selector):
    """Replay fixed quality selection; reject malformed inputs with ValueError."""
    if (not cutoff or snapshot["cutoffs"] != cutoff
            or snapshot["train"]["cutoffs"] != cutoff
            or selector not in {"UNION", "OVERLAP"}
            or not 0 < fraction <= 1
            or not np.isfinite(budget) or budget < 0 or budget % 2):
        raise ValueError("invalid fixed selector contract")
    options = snapshot["options"]
    costs = np.array([o["stake"] for o in options], dtype=float)
    coverage = np.array([o["coverage"] for o in options], dtype=float)
    expected = np.array([o["expected_gross"] for o in options], dtype=float)
    identities = [o["sleeve_id"] for o in options]
    hits = np.asarray(snapshot["train"]["hits"], dtype=float)
    if (hits.ndim != 2 or hits.shape[1] != len(options)
            or not hits.shape[0] or not np.isin(hits, [0, 1]).all()
            or len(set(identities)) != len(identities)
            or not np.isfinite(costs).all() or (costs <= 0).any()
            or (costs % 2).any() or not np.isfinite(coverage).all()
            or ((coverage < 0) | (coverage > 1)).any()
            or not np.isfinite(expected).all() or (expected < 0).any()):
        raise ValueError("invalid option or scenario contract")
    fixtures = [set(o["fixtures"]) for o in options]
    if any(len(f) != 7 for f in fixtures) or any(o["unit_copies"] != 1 for o in options):
        raise ValueError("expected unique seven-fixture single-copy groups")
    opening = np.atleast_1d(snapshot["opening_options"]).astype(int).tolist()
    selected = np.atleast_1d(snapshot["opportunity_options"]).astype(int).tolist()
    if (any(j < 1 or j > len(options) for j in opening + selected)
            or len(set(opening)) != len(opening) or len(set(selected)) != len(selected)):
        raise ValueError("invalid option indices")
    opening = [j - 1 for j in opening]
    selected = [j - 1 for j in selected]
    if costs[selected].sum() > budget:
        raise ValueError("initial allocation exceeds budget")
    while True:
        cash = budget - costs[selected].sum()
        available = [j for j in opening if j not in selected and costs[j] <= cash]
        if not available:
            return [j + 1 for j in selected]
        best = max(coverage[j] / costs[j] for j in available)
        admitted = [j for j in available if coverage[j] / costs[j] >= fraction * best]
        covered = hits[:, selected].sum(axis=1) > 0
        scores = []
        for j in admitted:
            gain = ((hits[:, j] > 0) & ~covered).mean() / costs[j]
            efficiency = coverage[j] / costs[j]
            overlap = [len(fixtures[j] & fixtures[k]) for k in selected]
            if selector == "UNION":
                key = (-gain, -(expected[j] - costs[j]) / costs[j], -efficiency, identities[j])
            else:
                key = (max(overlap, default=0), np.mean(overlap) if overlap else 0,
                       -gain, -efficiency, identities[j])
            scores.append((key, j))
        selected.append(min(scores)[1])
