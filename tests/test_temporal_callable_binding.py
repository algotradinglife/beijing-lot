import sys
import types
from unittest.mock import Mock
from pathlib import Path

import pytest

from src.n7_core_settlement import settle_core_layers
from src.temporal_learning.provenance import implementation_closure, verify_callable_binding
from src.temporal_learning.core import TemporalContractError

ROOT=Path(__file__).resolve().parents[1]


def test_loaded_callback_origin_and_code_are_bound(tmp_path, monkeypatch):
    receipt=implementation_closure(ROOT,['src.n7_core_settlement'])
    identity='src.n7_core_settlement:settle_core_layers'
    binding=verify_callable_binding(ROOT,receipt,settle_core_layers,expected_identity=identity)
    assert binding['identity']==identity
    assert 'src.n7_single_ticket_sampling:settle_single_tickets' in binding['executing_functions']
    with pytest.raises(TemporalContractError,match='qualified identity'):
        verify_callable_binding(ROOT,receipt,settle_core_layers,expected_identity='wrong')
    # Same qualified name, foreign code filename: the original reported defect.
    foreign=compile('def settle_core_layers(plan, audit):\n return {}\n',str(tmp_path/'n7_core_settlement.py'),'exec')
    namespace={};exec(foreign,namespace)
    bad=types.FunctionType(namespace['settle_core_layers'].__code__,settle_core_layers.__globals__)
    bad.__module__=settle_core_layers.__module__
    with pytest.raises(TemporalContractError,match='source differs'):
        verify_callable_binding(ROOT,receipt,bad,expected_identity=identity)
    # Even a forged correct filename cannot hide altered executing code.
    forged=compile('def settle_core_layers(plan, audit):\n return {}\n',settle_core_layers.__code__.co_filename,'exec')
    namespace={};exec(forged,namespace)
    bad=types.FunctionType(namespace['settle_core_layers'].__code__,settle_core_layers.__globals__)
    bad.__module__=settle_core_layers.__module__
    with pytest.raises(TemporalContractError,match='code differs'):
        verify_callable_binding(ROOT,receipt,bad,expected_identity=identity)
    # Imported local settlement helpers are bound too.
    import src.n7_core_settlement as module
    monkeypatch.setattr(module,'settle_single_tickets',bad)
    with pytest.raises(TemporalContractError):
        verify_callable_binding(ROOT,receipt,settle_core_layers,expected_identity=identity)


@pytest.mark.parametrize('replacement',[lambda plan,audit: {}, object(), Mock(return_value={})])
def test_nonlocal_replacement_cannot_disappear_from_binding(monkeypatch,replacement):
    import src.n7_core_settlement as module
    receipt=implementation_closure(ROOT,['src.n7_core_settlement'])
    monkeypatch.setattr(module,'settle_single_tickets',replacement)
    with pytest.raises(TemporalContractError,match='helper reference'):
        verify_callable_binding(ROOT,receipt,settle_core_layers,
            expected_identity='src.n7_core_settlement:settle_core_layers')
