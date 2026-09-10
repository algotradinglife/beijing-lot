"""Publish portable bindings around verified existing model bytes; no refitting."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_portable_experts import freeze_portable_experts
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ['model-root','source-root','provenance-root','output']:p.add_argument('--'+name,required=True)
 a=p.parse_args()
 print(freeze_portable_experts(a.model_root,output_path=a.output,source_root=a.source_root,
       provenance_root=a.provenance_root,repository_root=Path.cwd(),version='2.0.0'))
