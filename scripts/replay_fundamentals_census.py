"""Thin offline census entry point; dependencies are installed during setup."""
from pathlib import Path
import argparse
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.fundamentals_census import build_outputs, canonical
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--generated-at-utc', required=True)
    args = parser.parse_args()
    print(canonical(build_outputs(args.input_dir, args.output_dir,
                                  generated_at_utc=args.generated_at_utc)))
