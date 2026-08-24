#!/usr/bin/env python3
import argparse
from pathlib import Path

from src.n6_corrected_all_r.contract import RESULT_PACKAGE
from src.n6_corrected_all_r.pipeline import build_notebook_and_report, build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / RESULT_PACKAGE
    print(build_package(root, target, args.data_root, force=True))
    build_notebook_and_report(root, target)
    print(build_package(root, target, args.data_root, force=True))


if __name__ == "__main__":
    main()
