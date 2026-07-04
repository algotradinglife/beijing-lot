import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.decision_api import app as appmod  # noqa: E402

SPEC = importlib.util.spec_from_file_location("scrape_nowscore_bjdc", ROOT / "scripts/scrape_nowscore_bjdc.py")
assert SPEC and SPEC.loader
scrape_nowscore_bjdc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scrape_nowscore_bjdc)


def test_nowscore_halftime_is_not_finished() -> None:
    assert scrape_nowscore_bjdc.row_status("中场", "4-1", "false") == "live"
    assert appmod._nowscore_is_finished("finished", "中场") is False


def test_nowscore_fulltime_is_finished() -> None:
    assert scrape_nowscore_bjdc.row_status("完场", "4-1", "false") == "finished"
    assert appmod._nowscore_is_finished("finished", "完场") is True


def test_shadow_variant_hit_is_recomputed_from_current_result() -> None:
    row = {
        "shadow_arm": "shadow_vtest",
        "shadow_version": "llm_chain_bet_protect_stop_vtest",
        "shadow_selection_codes": "0+1",
        "shadow_primary": "0",
        "shadow_judgment": "负为押，保平",
        "shadow_stop_flag": "0",
        "shadow_primary_hit": "",
        "shadow_coverage_hit": "",
    }

    variant = appmod._shadow_decision_variant(row, "shadow.csv", result_code="1")

    assert variant["primary_hit"] is False
    assert variant["coverage_hit"] is True
    assert variant["prediction_hit"] is True
