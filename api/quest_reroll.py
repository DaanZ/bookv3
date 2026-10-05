"""New quests for a book, made on request from its finish screen.

A reroll is several model calls (the methods, the quests, the judge, and up to two retries)
and takes a minute or two, so it runs on its own worker thread and the finish screen asks
how it is going. One thread, so two rerolls never race to write the same file, and its own
rather than the ingest worker's, so a reroll does not wait behind a book being summarised.

Like `jobs.py`, the pipeline is imported inside the worker, never at module scope:
`util/chatgpt.py` reads the API key at import time, and the reader must start without one.

The state lives in memory. A restart forgets a reroll in flight, and that is the honest
answer: nothing resumes it, and the set on disk is still the old one.
"""
import importlib
import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from util.files import json_read_file

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quest-reroll")
_lock = threading.Lock()
_state: dict[str, dict] = {}


def has_key() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def status(key: str) -> dict | None:
    """{"state": "running" | "failed", "startedAt", "error"?}, or None when there is nothing to say."""
    with _lock:
        found = _state.get(key)
        return dict(found) if found else None


def submit(key: str, path: str, by: str, direction: str | None = None) -> dict | None:
    """Queue a reroll; None when one is already running for this book."""
    with _lock:
        if (_state.get(key) or {}).get("state") == "running":
            return None
        _state[key] = {"state": "running", "startedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        started = dict(_state[key])
    _executor.submit(_run, key, path, by, direction)
    return started


def _run(key: str, path: str, by: str, direction: str | None):
    try:
        # The top-level quests.py, not api/quests.py: the script owns the prompts.
        maker = importlib.import_module("quests")
        maker.reroll(key, json_read_file(path), by, direction=direction)
        with _lock:
            _state.pop(key, None)
    except Exception as ex:  # noqa: BLE001 — every failure is reported to the screen
        rejected = type(ex).__name__ == "QuestsRejected"
        if not rejected:
            traceback.print_exc()
        with _lock:
            _state[key] = {
                "state": "failed",
                "startedAt": (_state.get(key) or {}).get("startedAt"),
                # A rejection is the checks working: say which rule no set could meet.
                "error": f"No new set passed the checks: {ex}" if rejected else f"{type(ex).__name__}: {ex}",
            }
