#!/usr/bin/bash
set -euo pipefail
cd /home/drwho1985/workspace/algotradinglife/beijing-lot
source /home/drwho1985/workspace/algotradinglife/beijing-lot/docs/reviews/fm171-26103-count-policy-20261017/test-environment.sh
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
native_worker_pids=()
(
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-01/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-01/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-01/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-01/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-01 slots=1,2,3,4,5,6,7,8,9,10
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-01 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 1,2,3,4,5,6,7,8,9,10 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-01/run.log 2>&1
  echo DONE chunk-01
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-03/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-03/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-03/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-03/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-03 slots=21,22,23,24,25,26,27,28,29,30
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-03 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 21,22,23,24,25,26,27,28,29,30 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-03/run.log 2>&1
  echo DONE chunk-03
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-05/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-05/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-05/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-05/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-05 slots=41,42,43,44,45,46,47,48,49,50
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-05 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 41,42,43,44,45,46,47,48,49,50 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-05/run.log 2>&1
  echo DONE chunk-05
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-07/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-07/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-07/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-07/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-07 slots=61,62,63,64,65,66,67,68,69,70
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-07 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 61,62,63,64,65,66,67,68,69,70 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-07/run.log 2>&1
  echo DONE chunk-07
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-09/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-09/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-09/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-09/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-09 slots=81,82,83,84,85,86,87,88,89,90
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-09 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 81,82,83,84,85,86,87,88,89,90 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-09/run.log 2>&1
  echo DONE chunk-09
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-11/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-11/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-11/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-11/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-11 slots=101,102,103,104,105,106,107,108,109,110
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-11 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 101,102,103,104,105,106,107,108,109,110 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-11/run.log 2>&1
  echo DONE chunk-11
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-13/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-13/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-13/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-13/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-13 slots=121,122,123,124,125,126,127,128,129,130
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-13 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 121,122,123,124,125,126,127,128,129,130 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-13/run.log 2>&1
  echo DONE chunk-13
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-15/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-15/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-15/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-15/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-15 slots=141,142,143,144,145,146,147,148,149,150
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-15 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 141,142,143,144,145,146,147,148,149,150 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-15/run.log 2>&1
  echo DONE chunk-15
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-17/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-17/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-17/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-17/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-17 slots=161,162,163,164,165,166,167,168,169,170
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-17 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 161,162,163,164,165,166,167,168,169,170 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-17/run.log 2>&1
  echo DONE chunk-17
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-19/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-19/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-19/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-19/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-19 slots=181,182,183,184,185,186,187,188,189,190
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-19 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 181,182,183,184,185,186,187,188,189,190 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-19/run.log 2>&1
  echo DONE chunk-19
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-21/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-21/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-21/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-21/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-21 slots=201,202,203,204,205,206,207,208,209,210
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-21 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 201,202,203,204,205,206,207,208,209,210 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-21/run.log 2>&1
  echo DONE chunk-21
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-23/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-23/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-23/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-23/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-23 slots=221,222,223,224,225,226,227,228,229,230
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-23 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 221,222,223,224,225,226,227,228,229,230 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-23/run.log 2>&1
  echo DONE chunk-23
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-25/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-25/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-25/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-25/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-25 slots=241,242,243,244,245,246,247,248,249,250
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-25 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 241,242,243,244,245,246,247,248,249,250 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-25/run.log 2>&1
  echo DONE chunk-25
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-27/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-27/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-27/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-27/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-27 slots=261,262,263,264,265,266,267,268,269,270
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-27 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 261,262,263,264,265,266,267,268,269,270 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-27/run.log 2>&1
  echo DONE chunk-27
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-29/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-29/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-29/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-29/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-29 slots=281,282,283,284,285,286,287,288,289,290
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-29 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 281,282,283,284,285,286,287,288,289,290 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-29/run.log 2>&1
  echo DONE chunk-29
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-31/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-31/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-31/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-31/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-31 slots=301,302,303,304,305,306,307,308,309,310
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-31 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 301,302,303,304,305,306,307,308,309,310 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-31/run.log 2>&1
  echo DONE chunk-31
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-33/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-33/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-33/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-33/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-33 slots=321,322,323,324,325,326,327,328,329,330
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-33 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 321,322,323,324,325,326,327,328,329,330 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-33/run.log 2>&1
  echo DONE chunk-33
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-35/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-35/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-35/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-35/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-35 slots=341,342,343,344,345,346,347,348,349,350
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-35 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 341,342,343,344,345,346,347,348,349,350 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-35/run.log 2>&1
  echo DONE chunk-35
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-37/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-37/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-37/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-37/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-37 slots=361,362,363,364,365,366,367,368,369,370
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-37 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 361,362,363,364,365,366,367,368,369,370 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-37/run.log 2>&1
  echo DONE chunk-37
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-39/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-39/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-39/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-39/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-39 slots=381,382,383,384,385,386,387,388,389,390
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-39 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 381,382,383,384,385,386,387,388,389,390 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-39/run.log 2>&1
  echo DONE chunk-39
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-41/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-41/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-41/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-41/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-41 slots=401,402,403,404,405,406,407
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-41 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 401,402,403,404,405,406,407 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-41/run.log 2>&1
  echo DONE chunk-41
fi
) &
native_worker_pids+=("$!")
(
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-02/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-02/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-02/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-02/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-02 slots=11,12,13,14,15,16,17,18,19,20
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-02 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 11,12,13,14,15,16,17,18,19,20 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-02/run.log 2>&1
  echo DONE chunk-02
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-04/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-04/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-04/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-04/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-04 slots=31,32,33,34,35,36,37,38,39,40
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-04 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 31,32,33,34,35,36,37,38,39,40 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-04/run.log 2>&1
  echo DONE chunk-04
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-06/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-06/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-06/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-06/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-06 slots=51,52,53,54,55,56,57,58,59,60
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-06 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 51,52,53,54,55,56,57,58,59,60 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-06/run.log 2>&1
  echo DONE chunk-06
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-08/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-08/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-08/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-08/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-08 slots=71,72,73,74,75,76,77,78,79,80
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-08 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 71,72,73,74,75,76,77,78,79,80 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-08/run.log 2>&1
  echo DONE chunk-08
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-10/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-10/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-10/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-10/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-10 slots=91,92,93,94,95,96,97,98,99,100
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-10 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 91,92,93,94,95,96,97,98,99,100 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-10/run.log 2>&1
  echo DONE chunk-10
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-12/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-12/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-12/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-12/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-12 slots=111,112,113,114,115,116,117,118,119,120
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-12 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 111,112,113,114,115,116,117,118,119,120 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-12/run.log 2>&1
  echo DONE chunk-12
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-14/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-14/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-14/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-14/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-14 slots=131,132,133,134,135,136,137,138,139,140
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-14 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 131,132,133,134,135,136,137,138,139,140 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-14/run.log 2>&1
  echo DONE chunk-14
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-16/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-16/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-16/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-16/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-16 slots=151,152,153,154,155,156,157,158,159,160
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-16 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 151,152,153,154,155,156,157,158,159,160 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-16/run.log 2>&1
  echo DONE chunk-16
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-18/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-18/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-18/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-18/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-18 slots=171,172,173,174,175,176,177,178,179,180
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-18 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 171,172,173,174,175,176,177,178,179,180 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-18/run.log 2>&1
  echo DONE chunk-18
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-20/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-20/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-20/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-20/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-20 slots=191,192,193,194,195,196,197,198,199,200
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-20 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 191,192,193,194,195,196,197,198,199,200 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-20/run.log 2>&1
  echo DONE chunk-20
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-22/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-22/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-22/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-22/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-22 slots=211,212,213,214,215,216,217,218,219,220
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-22 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 211,212,213,214,215,216,217,218,219,220 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-22/run.log 2>&1
  echo DONE chunk-22
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-24/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-24/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-24/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-24/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-24 slots=231,232,233,234,235,236,237,238,239,240
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-24 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 231,232,233,234,235,236,237,238,239,240 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-24/run.log 2>&1
  echo DONE chunk-24
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-26/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-26/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-26/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-26/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-26 slots=251,252,253,254,255,256,257,258,259,260
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-26 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 251,252,253,254,255,256,257,258,259,260 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-26/run.log 2>&1
  echo DONE chunk-26
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-28/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-28/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-28/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-28/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-28 slots=271,272,273,274,275,276,277,278,279,280
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-28 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 271,272,273,274,275,276,277,278,279,280 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-28/run.log 2>&1
  echo DONE chunk-28
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-30/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-30/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-30/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-30/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-30 slots=291,292,293,294,295,296,297,298,299,300
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-30 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 291,292,293,294,295,296,297,298,299,300 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-30/run.log 2>&1
  echo DONE chunk-30
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-32/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-32/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-32/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-32/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-32 slots=311,312,313,314,315,316,317,318,319,320
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-32 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 311,312,313,314,315,316,317,318,319,320 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-32/run.log 2>&1
  echo DONE chunk-32
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-34/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-34/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-34/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-34/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-34 slots=331,332,333,334,335,336,337,338,339,340
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-34 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 331,332,333,334,335,336,337,338,339,340 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-34/run.log 2>&1
  echo DONE chunk-34
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-36/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-36/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-36/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-36/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-36 slots=351,352,353,354,355,356,357,358,359,360
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-36 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 351,352,353,354,355,356,357,358,359,360 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-36/run.log 2>&1
  echo DONE chunk-36
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-38/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-38/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-38/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-38/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-38 slots=371,372,373,374,375,376,377,378,379,380
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-38 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 371,372,373,374,375,376,377,378,379,380 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-38/run.log 2>&1
  echo DONE chunk-38
fi
if [[ -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-40/recent-receipt.json && -f /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-40/native-repair.rds ]]; then
  /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python - /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-40/recent-receipt.json /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-40/native-repair.rds <<'PYVERIFY'
import sys,json,hashlib
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text());assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()==r['sha256']
PYVERIFY
else
  echo START chunk-40 slots=391,392,393,394,395,396,397,398,399,400
  /opt/R/4.6.1/bin/Rscript r/fm171_26103_recent_repair.R /home/drwho1985/workspace/algotradinglife/beijing-lot /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-40 hot:fm171-26103-repair-20261017-v3/coverage-census.rds config/fm171_26103_count_recent_policy.json 391,392,393,394,395,396,397,398,399,400 > /home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/fm171-26103-full-recalc-20261017/native-chunks-v2/chunk-40/run.log 2>&1
  echo DONE chunk-40
fi
) &
native_worker_pids+=("$!")
native_any_failed=0
for native_worker_pid in "${native_worker_pids[@]}"; do
  wait "$native_worker_pid" || native_any_failed=1
done
if [[ "$native_any_failed" != 0 ]]; then
  echo FAILED_NATIVE_CHUNK
  exit 1
fi
echo ALL_NATIVE_CHUNKS_COMPLETE
