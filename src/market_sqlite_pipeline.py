"""Sequential preparation of an explicitly selected market migration batch."""
from pathlib import Path
import subprocess


def prepare_market_batch(project, *, python, data_root, batch_id, quarto, run=subprocess.run):
    """Run the five existing preparation entry points; stop on the first failure.

    Paths and batch identity are explicit. The caller owns the orchestration
    lock and environment (including R libraries). Each child enforces its own
    storage contract and stage locks. Reruns revalidate existing frozen inputs;
    no receipt is skipped merely because a file exists. Writes are performed by
    the authoritative child entry points. Does not accept, activate, or delete.
    Returns successfully completed stage names; child failures propagate.
    """
    if not batch_id or Path(batch_id).name != batch_id or batch_id in ('.', '..'):
        raise ValueError('unsafe batch identity')
    project=Path(project).resolve(strict=True)
    # Preserve the virtualenv entry path; resolving its symlink loses packages.
    python_path=Path(python).absolute()
    if not python_path.is_file():raise ValueError('Python executable missing')
    python=str(python_path)
    data_root=str(Path(data_root).resolve(strict=True))
    quarto=str(Path(quarto).resolve(strict=True))
    contract=str(project/'config/persistent_data_layout.json')
    stages=[
        ('import','migrate_market_sqlite_batch.py',['--data-root',data_root,'--batch',batch_id]),
        ('audit','retain_market_sqlite_audit.py',['--data-root',data_root,'--plan',
            f'audits/market-sqlite/{batch_id}/audit-retention-plan.json']),
        ('inventory','freeze_market_sqlite_inventories.py',['--contract',contract,'--batch-id',batch_id]),
        ('publication','stage_market_sqlite_publication.py',['--contract',contract,'--batch-id',batch_id]),
        ('report','render_market_sqlite_acceptance.py',['--contract',contract,'--batch-id',batch_id,'--quarto',quarto]),
    ]
    # Require the explicit evidence plan before starting an expensive import.
    plan=Path(data_root)/'audits/market-sqlite'/batch_id/'audit-retention-plan.json'
    if not plan.is_file():
        raise ValueError('explicit audit retention plan required')
    completed=[]
    for name,script,args in stages:
        print(f'MARKET_PREPARATION_STAGE {name}',flush=True)
        run([python,str(project/'scripts'/script),*args],cwd=project,check=True)
        completed.append(name)
    return completed
