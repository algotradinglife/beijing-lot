import copy
import pytest
from tests.test_fundamentals_repeated_double import source
from src.fundamentals_compression_variants import build_compression_variants, settle_compression_variants
from src.temporal_learning import Cutoff


@pytest.fixture(scope='module')
def params():
    return dict(n=7, budget_cny=512, unit_cny=2, payout_factor=.65,
        candidate_seed=41900, design_seed=41901, evaluation_seed=41902,
        pool_size=128, design_draws=128, evaluation_draws=256,
        gap_rules={'GAP02': .02, 'GAP05': .05, 'GAP10': .10, 'ALL': 1.},
        conflict_rules={'TAIL05': 0., 'TV10': .1, 'TV15': .15, 'TV20': .2}, minimum_market_tail_lead=.05)


def test_builder_reuses_existing_reference_and_settlement(source, params):
    frame, cuts, reference = source
    bundle = build_compression_variants(frame, cutoffs=cuts, **params)
    assert len(bundle) == 72
    for d in (1, 2):
        assert bundle[f'D{d}_COMPRESSED_FREE_BASE']['plan'] == reference[d]
    original = copy.deepcopy(bundle)
    audit = frame[['issue', 'slot', 'provider_id', 'handicap']].assign(status='READY', actual_direction='W', spf_sp=2.)
    rows = settle_compression_variants(bundle, audit)
    assert len(rows) == 72 and bundle == original
    for row in rows:
        assert row['stake'] + row['cash_cny'] == 512
        assert row['gross'] == pytest.approx(row['groups']*2*.65*2**7)
    audit.actual_direction = 'L'
    assert all(r['gross'] == 0 for r in settle_compression_variants(bundle, audit))
    assert bundle == original
    audit.status = 'PENDING'
    with pytest.raises(ValueError, match='READY'):
        settle_compression_variants(bundle, audit)
    audit.status = 'READY';audit.handicap = 1
    with pytest.raises(ValueError, match='handicap'):
        settle_compression_variants(bundle, audit)
    audit.handicap = 0
    with pytest.raises(ValueError, match='Unique'):
        settle_compression_variants(bundle, audit.iloc[[0, 0]])
    audit.actual_direction = 'W';audit.spf_sp = float('nan')
    with pytest.raises(ValueError, match='Incomplete'):
        settle_compression_variants(bundle, audit)


def test_builder_rejects_missing_scope_labels_and_changed_cutoffs(source, params):
    frame, cuts, _ = source
    for f in [frame.iloc[:6], frame.assign(actual_direction='W'), frame.assign(spf_sp=2)]:
        with pytest.raises(ValueError, match='forecast-only'):
            build_compression_variants(f, cutoffs=cuts, **params)
    with pytest.raises(ValueError):
        build_compression_variants(frame, cutoffs={}, **params)
    bad = dict(params, conflict_rules={'BASE': .1})
    with pytest.raises(ValueError, match='Unique'):
        build_compression_variants(frame, cutoffs=cuts, **bad)
