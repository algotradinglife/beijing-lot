#!/usr/bin/env python3
"""Build and execute the thin, package-derived #204 Gate-B audit notebook."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/research/issue-204/bj204_track_a_gate_b.ipynb"
PACKAGE = "results/bj204_gate_b_retrospective_implementation_recovery_v1"


def main() -> None:
    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
        }
    )
    notebook.cells = [
        nbformat.v4.new_markdown_cell(
            "# #204 Track A Gate B — anchored-method correction preflight\n\n"
            "The immutable `RETROSPECTIVE_IMPLEMENTATION_RECOVERY` package is preserved as a nonconforming "
            "product-ensemble diagnostic: its ordinary classifier scores were composed with the market only after "
            "training and therefore cannot establish that market-anchored residual learning failed. This notebook "
            "audits those frozen bytes and runs a bounded synthetic fixture through the corrected reusable anchored-fit "
            "path. It does not refit or reopen the locked test, choose parameters, or create a replacement result."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport hashlib\nimport json\nimport pandas as pd\nfrom IPython.display import Image, Markdown, display\n\n"
            f"package = Path('{PACKAGE}')\n"
            "assert package.is_dir(), package\n"
            "manifest = json.loads((package / 'SHA256SUMS.json').read_text())\n"
            "bad = [name for name, expected in manifest.items() if hashlib.sha256((package / name).read_bytes()).hexdigest() != expected]\n"
            "assert not bad, bad\n"
            "print(f'Package manifest PASS: {len(manifest)} payloads')"
        ),
        nbformat.v4.new_markdown_cell("## Frozen contract and source binding"),
        nbformat.v4.new_code_cell(
            "config = json.loads((package / 'model_config.json').read_text())\n"
            "provenance = json.loads((package / 'provenance.json').read_text())\n"
            "display(pd.DataFrame([{'version': config['version'], 'execution_status': config['execution_status'], 'composition': config['probability_composition'], 'gate_a_manifest': config['gate_a_manifest_sha256'], 'label_source_sha256': provenance['official_label_source_sha256']}]))\n"
            "display(pd.DataFrame(config['models']).T)"
        ),
        nbformat.v4.new_markdown_cell("## Corrected training objective — bounded production-path fixture"),
        nbformat.v4.new_code_cell(
            "import sys\nimport numpy as np\nfrom sklearn.linear_model import LogisticRegression\n"
            "sys.path.insert(0, str(Path.cwd() / 'src'))\n"
            "from unified_model.gate_b import AnchoredResidualEstimator, _anchored_probabilities, _metrics\n\n"
            "rng = np.random.default_rng(204001)\n"
            "fixture_target = np.tile(np.arange(3), 60)\n"
            "fixture_features = np.column_stack([fixture_target + rng.normal(0, 0.35, len(fixture_target)), rng.normal(size=len(fixture_target))])\n"
            "fixture_market = np.tile(np.array([1/3, 1/3, 1/3]), (len(fixture_target), 1))\n"
            "anchored = AnchoredResidualEstimator(LogisticRegression(C=0.5, max_iter=300, random_state=204001)).fit(fixture_features, fixture_target, fixture_market)\n"
            "fixture_probabilities = _anchored_probabilities(fixture_market, anchored.predict_delta(fixture_features))\n"
            "fixture = pd.DataFrame([{'training_logits': 'log(p_market) + alpha * centered_direction(x)', 'alpha': anchored.residual_scale, 'market_loss': anchored.baseline_loss, 'anchored_loss': anchored.anchored_loss, 'recomputed_loss': _metrics(fixture_probabilities, fixture_target)['log_loss']}])\n"
            "assert anchored.optimizer_success and 0 <= anchored.residual_scale <= 1\n"
            "assert abs(fixture.loc[0, 'anchored_loss'] - fixture.loc[0, 'recomputed_loss']) <= 1e-12\n"
            "assert fixture.loc[0, 'anchored_loss'] < fixture.loc[0, 'market_loss']\n"
            "display(fixture)"
        ),
        nbformat.v4.new_markdown_cell("## Development-only selection and locked-test scores"),
        nbformat.v4.new_code_cell(
            "selection = pd.read_csv(package / 'model_selection.csv')\n"
            "metrics = pd.read_csv(package / 'metrics.csv')\n"
            "display(selection)\n"
            "locked = metrics[(metrics['split'] == 'LOCKED_TEST') & metrics['view'].isin(['PURE_MARKET', 'MODEL_ONLY_COVERED', 'FALLBACK_MIXED'])]\n"
            "locked_summary = locked.groupby(['model_id', 'view'], as_index=False)[['log_loss','brier','ece_equal_mass','top1','top2','sp_mae','model_used_rows','fallback_rows','ood_rows','mean_delta_logit_l1']].mean()\n"
            "display(locked_summary)\n"
            "context_safe = locked_summary[(locked_summary['model_id'] == 'ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL') & (locked_summary['view'] == 'FALLBACK_MIXED')]\n"
            "assert len(context_safe) == 1 and context_safe.iloc[0]['model_used_rows'] == 0 and context_safe.iloc[0]['fallback_rows'] == context_safe.iloc[0]['ood_rows'] == 16968\n"
            "display(Markdown('**Context-arm disclosure:** all 16,968 market-eligible locked-test rows are OOD fallback for every frozen seed; model-used coverage is 0%. Its raw model-only score is diagnostic and its safe-mixed path supplies no learned-model evidence.'))"
        ),
        nbformat.v4.new_markdown_cell("## Exact matched-baseline differences, calibration and coverage"),
        nbformat.v4.new_code_cell(
            "deltas = pd.read_csv(package / 'matched_baseline_deltas.csv')\n"
            "display(deltas[deltas['split'] == 'LOCKED_TEST'].groupby('model_id', as_index=False)[['lift_log_loss','lift_brier','lift_ece_equal_mass','lift_top1','lift_top2','lift_sp_mae']].mean())\n"
            "display(pd.read_csv(package / 'locked_test_calibration.csv'))\n"
            "for filename in ('locked_test_log_loss.png', 'locked_test_calibration.png', 'locked_test_coverage.png'):\n"
            "    display(Image(filename=str(package / filename)))"
        ),
        nbformat.v4.new_markdown_cell("## Frozen diagnostic report (superseded as residual evidence)"),
        nbformat.v4.new_code_cell("display(Markdown((package / 'DECISION_REPORT.md').read_text()))"),
    ]
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, NOTEBOOK)
    client = NotebookClient(notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
    client.execute()
    nbformat.write(notebook, NOTEBOOK)
    print(NOTEBOOK)


if __name__ == "__main__":
    main()
