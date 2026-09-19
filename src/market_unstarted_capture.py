"""Verify a prepared collector output has never acquired capture state."""
from pathlib import Path


def verify_unstarted_capture(output):
    """Return an empty-output proof or reject any state, body or symlink.

    Caller must hold the worker lock and independently verify the stopped
    service, registry, frozen plan/index and request policy before rebinding
    storage pointers. An empty worker.lock is the only allowed directory entry.
    Reads filesystem metadata only; never initializes or fabricates progress.
    """
    output=Path(output)
    if any(p.is_symlink() for p in (output,*output.parents)) or not output.is_dir():
        raise ValueError('real collector directory required')
    for path in output.iterdir():
        if (path.name!='worker.lock' or path.is_symlink() or not path.is_file()
                or path.stat().st_size!=0):
            raise ValueError('collector output has state or unexpected content')
    return dict(state='UNSTARTED_CAPTURE_OUTPUT_VERIFIED',output=str(output.resolve()),
                progress_created=False,request_policy_changed=False)
