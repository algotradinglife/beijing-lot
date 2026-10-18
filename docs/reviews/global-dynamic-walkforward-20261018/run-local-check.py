"""One explicit local command with an exit receipt; survives tool-session expiry."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
spec = json.loads(Path(sys.argv[1]).read_bytes())
started = datetime.now(timezone.utc).isoformat()
with open(spec['log'], 'w') as stream:
    result = subprocess.run(spec['command'], cwd=spec['cwd'], stdout=stream,
        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=os.environ.copy())
receipt = dict(command=spec['command'],cwd=spec['cwd'],exit_status=result.returncode,
    started_at_utc=started,finished_at_utc=datetime.now(timezone.utc).isoformat())
p = Path(spec['receipt']);temp=p.with_suffix('.tmp');temp.write_text(json.dumps(receipt,indent=2)+'\n');temp.replace(p)
sys.exit(result.returncode)
