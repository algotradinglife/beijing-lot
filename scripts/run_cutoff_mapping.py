#!/usr/bin/env python3
import argparse
from pathlib import Path

from src.cutoff_mapping.contract import RESULT_PACKAGE
from src.cutoff_mapping.package import build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(build_package(root, root / RESULT_PACKAGE, args.data_root, force=True))


if __name__ == "__main__":
    main()
