import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, List

import yaml

ALLOCATIONS_PATH = Path("/codeload/quantrocket.moonshot.allocations.yml")

# Serialise concurrent writes within this process to prevent YAML corruption.
_write_lock = threading.Lock()


class AllocationError(RuntimeError):
    pass


def _ensure_parent():
    ALLOCATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)


def read_allocations() -> Dict[str, List[Dict[str, float]]]:
    """
    Returns a dict of account -> list of {code, weight}.
    """
    if not ALLOCATIONS_PATH.exists():
        return {}
    try:
        raw = yaml.safe_load(ALLOCATIONS_PATH.read_text()) or {}
    except Exception as exc:
        raise AllocationError(f"Failed to read allocations file: {exc}") from exc

    out: Dict[str, List[Dict[str, float]]] = {}
    for account, strategies in raw.items():
        if not isinstance(strategies, dict):
            continue
        out[account] = []
        for code, weight in strategies.items():
            try:
                out[account].append({"code": str(code), "weight": float(weight)})
            except (TypeError, ValueError):
                continue
    return out


def _write_allocations(data: Dict[str, List[Dict[str, float]]]) -> None:
    structured: Dict[str, Dict[str, float]] = {}
    for account, entries in data.items():
        structured[account] = {item["code"]: float(item["weight"]) for item in entries}
    _ensure_parent()

    content = yaml.safe_dump(structured, sort_keys=True, default_flow_style=False)

    # Atomic write: write to a temp file in the same directory, then rename.
    # os.replace() is atomic on POSIX when src and dst are on the same filesystem.
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=ALLOCATIONS_PATH.parent,
            suffix=".yml.tmp",
        )
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, ALLOCATIONS_PATH)
    except Exception as exc:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise AllocationError(f"Failed to write allocations file: {exc}") from exc


def update_account_allocations(account: str, codes: List[str], weights: List[float]) -> None:
    if len(codes) != len(weights):
        raise AllocationError(
            f"Strategies and weights length mismatch ({len(codes)} vs {len(weights)})"
        )
    with _write_lock:
        existing = read_allocations()
        entries = [{"code": code, "weight": weight} for code, weight in zip(codes, weights)]
        existing[account] = entries
        _write_allocations(existing)
