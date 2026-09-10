"""Caller-specified draw weights change only the blend, never the frozen expert."""
import sys
from fractions import Fraction
from copy import deepcopy
import numpy as np
import pytest
from tests.test_fundamentals_calibrated_draw import frozen
from tests.test_fundamentals_draw_versions import catalog
from src.fundamentals_calibrated_draw import load_calibrated_draw, predict_calibrated_draw
from src.fundamentals_draw_versions import predict_draw_version
from src.fundamentals_signal_rates import validate_draw_weight


@pytest.mark.parametrize('value',[0,1,.3,np.float64(.7),np.int64(1),Fraction(1,2)])
def test_weight_contract_accepts_finite_real_scalars(value):
    assert validate_draw_weight(value)==float(value)
    assert type(validate_draw_weight(value)) is float


@pytest.mark.parametrize('value',[-.01,1.01,float('nan'),float('inf'),-float('inf'),True,np.bool_(False),'0.5',[.5],None,10**400])
def test_weight_contract_rejects_invalid_values(value):
    with pytest.raises(ValueError,match='draw_weight'):
        validate_draw_weight(value)


def test_weight_endpoints_arbitrary_values_defaults_and_receipts(frozen):
    path,root,frame,cutoff=frozen
    model=load_calibrated_draw(path,expected_version='1.1.0',repository_root=root)
    original=deepcopy(model['receipt'])
    default=predict_calibrated_draw(model,frame,cutoff)
    for weight in [0,.3,.5,.7,1,Fraction(1,2)]:
        output=predict_calibrated_draw(model,frame,cutoff,draw_weight=weight)
        reference=output.boosted_reference.fillna(frame.baseline_draw)
        expected=(1-float(weight))*frame.baseline_draw+float(weight)*reference
        np.testing.assert_allclose(output.draw_target_probability,expected,rtol=0,atol=1e-14)
        assert output.draw_weight.eq(weight).all()
        assert output.draw_signal.equals(default.draw_signal)
        assert output.raw_draw_probability.equals(default.raw_draw_probability)
        assert output.calibration_status.equals(default.calibration_status)
        # Missing expert features and unsupported bands keep the baseline even at weight=1.
        assert output.draw_target_probability.iloc[1:].tolist()==frame.baseline_draw.iloc[1:].tolist()
        receipt=output.attrs['prediction_receipt']
        assert receipt['policy']['blend_weight']==weight
        assert receipt['frozen_policy']==original['policy'] and receipt['policy_source']=='CALLER_WEIGHT'
        assert receipt['input_sha256']==default.attrs['prediction_receipt']['input_sha256']
        if weight!=original['policy']['blend_weight']:
            assert output.attrs['prediction_seal']!=default.attrs['prediction_seal']
        else:
            assert output.draw_target_probability.equals(default.draw_target_probability)
    assert model['receipt']==original
    assert default.attrs['prediction_receipt']['policy_source']=='FROZEN_CV_DEFAULT'
    for invalid in [True,.0-1,2,float('nan'),'0.5']:
        with pytest.raises(ValueError,match='draw_weight'):
            predict_calibrated_draw(model,frame,cutoff,draw_weight=invalid)


def test_router_forwards_weight_and_rejects_old_versions(catalog):
    path,root,frame,cutoff=catalog
    kwargs=dict(cutoffs=[cutoff]*len(frame),catalog_path=path,repository_root=root,python=sys.executable)
    result=predict_draw_version('1.1.0',frame,draw_weight=np.int64(0),**kwargs)
    np.testing.assert_allclose(result.draw_target_probability,frame.baseline_draw)
    assert result.draw_weight.eq(0).all()
    assert result.attrs['prediction_receipt']['draw_weight_override']==0
    one=predict_draw_version('1.1.0',frame,draw_weight=Fraction(7,10),**kwargs)
    assert one.draw_weight.eq(.7).all()
    assert one.attrs['prediction_receipt']['draw_weight_override']==.7
    for old in ['0.1.0','0.2.0','1.0.0','1.0.1']:
        with pytest.raises(ValueError,match='does not support draw_weight'):
            predict_draw_version(old,frame,draw_weight=.7,**kwargs)
    with pytest.raises(ValueError,match='draw_weight'):
        predict_draw_version('1.1.0',frame,draw_weight=True,**kwargs)
