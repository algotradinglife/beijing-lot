from pathlib import Path
import shutil
import pytest
from beidan_backend.temporal_learning import Cutoff, TemporalContractError
from beidan_backend.temporal_learning.provenance import implementation_closure, verify_implementation_closure
import beidan_backend


def test_cutoff_preserves_identity_and_requires_target_issue():
    cutoff = Cutoff.decision_epoch('00123', '2026-09-22T12:00:00Z')
    assert cutoff.target_issue == '00123'
    with pytest.raises(TemporalContractError):
        Cutoff.decision_epoch('', '2026-09-22T12:00:00Z')


def test_installed_backend_closure_is_root_bound_and_detects_mutation(tmp_path):
    source = Path(beidan_backend.__file__).parent
    shutil.copytree(source, tmp_path / 'beidan_backend', ignore=shutil.ignore_patterns('__pycache__'))
    receipt = implementation_closure(tmp_path, ['beidan_backend.temporal_learning'])
    assert 'beidan_backend/temporal_learning/core.py' in receipt['files']
    verify_implementation_closure(tmp_path, receipt)
    core = tmp_path / 'beidan_backend/temporal_learning/core.py'
    core.write_text(core.read_text() + '\n# changed implementation\n')
    with pytest.raises(TemporalContractError, match='differs'):
        verify_implementation_closure(tmp_path, receipt)
    with pytest.raises(TemporalContractError, match='missing'):
        implementation_closure(tmp_path / 'missing-root', ['beidan_backend.temporal_learning'])


def test_parent_initializers_are_bound_for_direct_submodule_import(tmp_path):
    source = Path(beidan_backend.__file__).parent
    shutil.copytree(source, tmp_path / 'beidan_backend', ignore=shutil.ignore_patterns('__pycache__'))
    receipt = implementation_closure(tmp_path, ['beidan_backend.temporal_learning.core'])
    assert 'beidan_backend/__init__.py' in receipt['files']
    assert 'beidan_backend/temporal_learning/__init__.py' in receipt['files']
    parent = tmp_path / 'beidan_backend/__init__.py'
    parent.write_text(parent.read_text() + '\n# changed parent initializer\n')
    with pytest.raises(TemporalContractError, match='differs'):
        verify_implementation_closure(tmp_path, receipt)


def test_a_different_checkout_cannot_describe_the_loaded_backend(tmp_path):
    source = Path(beidan_backend.__file__).parent
    declared = tmp_path / 'packages/beidan/inst/python/beidan_backend'
    shutil.copytree(source, declared, ignore=shutil.ignore_patterns('__pycache__'))
    implementation_closure(tmp_path, ['beidan_backend.temporal_learning.core'])
    core = declared / 'temporal_learning/core.py'
    core.write_text(core.read_text() + '\n# divergent checkout\n')
    with pytest.raises(TemporalContractError, match='loaded backend implementation differs'):
        implementation_closure(tmp_path, ['beidan_backend.temporal_learning.core'])


def test_changing_loaded_files_after_import_is_rejected(tmp_path):
    import subprocess
    import sys
    source = Path(beidan_backend.__file__).parent
    shutil.copytree(source, tmp_path / 'beidan_backend', ignore=shutil.ignore_patterns('__pycache__'))
    program = r"""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from beidan_backend.temporal_learning.provenance import implementation_closure
from beidan_backend.temporal_learning import TemporalContractError
root = Path(sys.argv[1])
core = root / 'beidan_backend/temporal_learning/core.py'
core.write_text(core.read_text() + '\n# changed after import\n')
try:
    implementation_closure(root, ['beidan_backend.temporal_learning.core'])
except TemporalContractError as error:
    assert 'loaded backend implementation differs' in str(error)
else:
    raise AssertionError('accepted code changed after import')
"""
    result = subprocess.run([sys.executable, '-I', '-c', program, str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
