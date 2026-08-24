#!/usr/bin/env python3
import argparse
from pathlib import Path

from src.n6_corrected_all_r.contract import RESULT_PACKAGE
from src.n6_corrected_all_r.pipeline import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(verify_package(root, root / RESULT_PACKAGE, args.data_root))


if __name__ == "__main__":
    main()
