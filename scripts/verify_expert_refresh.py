"""Read-only boundary check called by the R report before parsing predictions."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_refresh_predictions import verify_refresh_predictions
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args()
 print(verify_refresh_predictions(a.study,repository_root=Path.cwd()))
