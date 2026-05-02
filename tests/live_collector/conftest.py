import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = ROOT / "tests" / "fixtures" / "live_collector"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
