"""Small, shared transaction boundary for admission and frozen publication."""

import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def snapshot_lock(root):
    with (Path(root) / "snapshot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield
