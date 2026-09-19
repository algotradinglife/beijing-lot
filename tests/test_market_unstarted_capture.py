import pytest
from src.market_unstarted_capture import verify_unstarted_capture


def test_empty_output_and_worker_lock_are_not_progress(tmp_path):
    assert verify_unstarted_capture(tmp_path)['progress_created'] is False
    (tmp_path/'worker.lock').touch()
    assert verify_unstarted_capture(tmp_path)['request_policy_changed'] is False
    (tmp_path/'worker.lock').write_text('unexpected')
    with pytest.raises(ValueError): verify_unstarted_capture(tmp_path)


@pytest.mark.parametrize('name',['progress.json','policy.json','responses','unknown'])
def test_any_capture_state_prevents_unstarted_rebinding(tmp_path,name):
    (tmp_path/name).touch()
    with pytest.raises(ValueError): verify_unstarted_capture(tmp_path)


def test_symlink_is_rejected(tmp_path):
    actual=tmp_path/'actual';actual.mkdir()
    alias=tmp_path/'alias';alias.symlink_to(actual,target_is_directory=True)
    with pytest.raises(ValueError): verify_unstarted_capture(alias)
    (actual/'capture').mkdir()
    with pytest.raises(ValueError): verify_unstarted_capture(alias/'capture')
    (actual/'worker.lock').symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError): verify_unstarted_capture(actual)
