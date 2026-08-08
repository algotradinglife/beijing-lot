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
            "# #204 Track A Gate B — market-anchored residual recovery\n\n"
            "This executed notebook is a thin audit of the immutable `RETROSPECTIVE_IMPLEMENTATION_RECOVERY` package. "
            "It does not refit models, read labels, or choose parameters: the reusable runner performed the frozen fit/evaluation and this notebook verifies and renders its saved outputs."
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
        nbformat.v4.new_markdown_cell("## Development-only selection and locked-test scores"),
        nbformat.v4.new_code_cell(
            "selection = pd.read_csv(package / 'model_selection.csv')\n"
            "metrics = pd.read_csv(package / 'metrics.csv')\n"
            "display(selection)\n"
            "locked = metrics[(metrics['split'] == 'LOCKED_TEST') & metrics['view'].isin(['PURE_MARKET', 'MODEL_ONLY_COVERED', 'FALLBACK_MIXED'])]\n"
            "display(locked.groupby(['model_id', 'view'], as_index=False)[['log_loss','brier','ece_equal_mass','top1','top2','sp_mae','model_used_rows','fallback_rows','ood_rows','mean_delta_logit_l1']].mean())"
        ),
        nbformat.v4.new_markdown_cell("## Exact matched-baseline differences, calibration and coverage"),
        nbformat.v4.new_code_cell(
            "deltas = pd.read_csv(package / 'matched_baseline_deltas.csv')\n"
            "display(deltas[deltas['split'] == 'LOCKED_TEST'].groupby('model_id', as_index=False)[['lift_log_loss','lift_brier','lift_ece_equal_mass','lift_top1','lift_top2','lift_sp_mae']].mean())\n"
            "display(pd.read_csv(package / 'locked_test_calibration.csv'))\n"
            "for filename in ('locked_test_log_loss.png', 'locked_test_calibration.png', 'locked_test_coverage.png'):\n"
            "    display(Image(filename=str(package / filename)))"
        ),
        nbformat.v4.new_markdown_cell("## Decision"),
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
