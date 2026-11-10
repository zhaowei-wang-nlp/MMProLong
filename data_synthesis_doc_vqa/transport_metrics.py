"""HTTP stage timings without logging URLs, credentials, headers or payloads."""

import threading
import time

_local = threading.local()


def begin_attempt():
    _local.events = {}
    _local.starts = {}


def trace(event, info):
    if not hasattr(_local, "events"):
        return
    name, _, phase = event.rpartition(".")
    if phase == "started":
        _local.starts[name] = time.monotonic()
    elif phase in {"complete", "failed"} and name in _local.starts:
        elapsed = time.monotonic() - _local.starts.pop(name)
        _local.events[name] = _local.events.get(name, 0) + elapsed


def attach_trace(request):
    request.extensions["trace"] = trace


def end_attempt():
    return {k: round(v, 4) for k, v in getattr(_local, "events", {}).items()}
