"""
checkpoint_manager.py - Persistent state and resume manager for Ultimate Coding Agent.

Features:
- Saves full execution context (pipeline state, coder state, generated files, plan, research) to disk at every node boundary.
- Atomic file writes (.tmp -> replace) to prevent corruption during sudden power loss or process termination.
- Automatically captures SIGINT (Ctrl+C) and atexit to mark tasks as 'interrupted'.
- On next startup, detects interrupted tasks and prompts the user:
    1) Resume from last saved checkpoint (preserves research, plan, and partial code)
    2) Start fresh (archives previous task)
- Supports non-interactive CLI flags (--resume, --fresh).
"""

from __future__ import annotations

import atexit
import json
import logging
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("checkpoint_manager")

ROOT = Path(__file__).resolve().parent
CHECKPOINT_DIR = ROOT / ".checkpoints"
ACTIVE_FILE = CHECKPOINT_DIR / "active_session.json"
HISTORY_DIR = CHECKPOINT_DIR / "history"

_CURRENT_SESSION_ID: Optional[str] = None
_SIGNAL_REGISTERED = False


def init_dirs() -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _safe_serialize(obj: Any) -> Any:
    """Ensure all nested values are JSON-serializable."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (list, tuple, set)):
        return [_safe_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items() if not str(k).startswith("_cb")}
    return str(obj)


def get_active_checkpoint() -> Optional[Dict[str, Any]]:
    """Return active session checkpoint if it exists and is resumable."""
    init_dirs()
    if not ACTIVE_FILE.exists():
        return None
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        if data.get("status") in ("in_progress", "interrupted"):
            return data
    except Exception as e:
        logger.warning("Failed to read active checkpoint: %s", e)
    return None


def save_checkpoint(
    task: str,
    stage: str,
    pipeline_state: Optional[Dict[str, Any]] = None,
    coder_state: Optional[Dict[str, Any]] = None,
    status: str = "in_progress",
    description: str = "",
    session_id: Optional[str] = None,
) -> str:
    """Save execution state atomically to disk."""
    global _CURRENT_SESSION_ID
    init_dirs()

    sid = session_id or _CURRENT_SESSION_ID or f"session_{int(time.time())}"
    _CURRENT_SESSION_ID = sid
    _register_signal_handlers()

    existing = {}
    if ACTIVE_FILE.exists():
        try:
            existing = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    started_at = existing.get("started_at", time.time())
    
    # Merge existing state with new updates
    merged_pipe = dict(existing.get("pipeline_state") or {})
    if pipeline_state:
        merged_pipe.update(pipeline_state)

    merged_coder = dict(existing.get("coder_state") or {})
    if coder_state:
        merged_coder.update(coder_state)

    # Sync files from coder state to pipeline if available
    files = merged_coder.get("files") or merged_pipe.get("files") or {}

    payload = {
        "session_id": sid,
        "task": task or existing.get("task", ""),
        "status": status,
        "stage": stage,
        "description": description or f"In stage: {stage}",
        "started_at": started_at,
        "updated_at": time.time(),
        "files_count": len(files),
        "file_names": sorted(list(files.keys())),
        "pipeline_state": _safe_serialize(merged_pipe),
        "coder_state": _safe_serialize(merged_coder),
    }

    tmp_file = ACTIVE_FILE.with_suffix(".tmp")
    try:
        tmp_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_file.replace(ACTIVE_FILE)
    except Exception as e:
        logger.warning("Failed to save checkpoint atomically: %s", e)
        try:
            ACTIVE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e2:
            logger.error("Fatal error writing checkpoint: %s", e2)

    return sid


def mark_completed(session_id: Optional[str] = None, final_output: Optional[str] = None) -> None:
    """Mark session as completed and archive it."""
    global _CURRENT_SESSION_ID
    init_dirs()
    sid = session_id or _CURRENT_SESSION_ID
    if not ACTIVE_FILE.exists():
        return
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        data["status"] = "completed"
        data["completed_at"] = time.time()
        if final_output:
            data["final_output"] = str(final_output)[:2000]
        
        # Archive to history
        archive_path = HISTORY_DIR / f"{data.get('session_id', sid or 'session')}.json"
        archive_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Remove active file so next run is clean
        ACTIVE_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Error finalizing checkpoint: %s", e)
    _CURRENT_SESSION_ID = None


def mark_interrupted(session_id: Optional[str] = None) -> None:
    """Mark session as interrupted."""
    init_dirs()
    if not ACTIVE_FILE.exists():
        return
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        data["status"] = "interrupted"
        data["interrupted_at"] = time.time()
        ACTIVE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("Error marking checkpoint interrupted: %s", e)


def discard_active_checkpoint() -> None:
    """Archive and delete active checkpoint to allow fresh start."""
    global _CURRENT_SESSION_ID
    init_dirs()
    if not ACTIVE_FILE.exists():
        return
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        data["status"] = "discarded"
        data["discarded_at"] = time.time()
        archive_path = HISTORY_DIR / f"{data.get('session_id', 'discarded')}_discarded.json"
        archive_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        ACTIVE_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Error discarding checkpoint: %s", e)
    _CURRENT_SESSION_ID = None


def prompt_resume_if_available(
    force_resume: bool = False,
    force_fresh: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Check for an interrupted session and prompt the user.
    Returns:
        checkpoint dict if resuming, None if starting fresh.
    """
    cp = get_active_checkpoint()
    if not cp:
        return None

    if force_fresh:
        logger.info("force_fresh requested. Discarding previous checkpoint.")
        discard_active_checkpoint()
        return None

    if force_resume:
        logger.info("force_resume requested. Resuming session %s", cp.get("session_id"))
        return cp

    task_desc = cp.get("task", "Unknown Task")
    if len(task_desc) > 80:
        task_desc = task_desc[:77] + "..."
    
    stage = cp.get("stage", "Unknown")
    desc = cp.get("description", "")
    files_count = cp.get("files_count", 0)
    file_names = ", ".join(cp.get("file_names", [])[:4])
    if files_count > 4:
        file_names += f" (+{files_count - 4} more)"
    
    t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(cp.get("updated_at", time.time())))

    print("\n" + "=" * 65)
    print(" [!] PREVIOUS INTERRUPTED TASK DETECTED (Context Saved on Disk)")
    print("=" * 65)
    print(f" - Task:        {task_desc}")
    print(f" - Last Stage:  {stage} ({desc})")
    print(f" - Saved Files: {files_count} file(s) [{file_names or 'none yet'}]")
    print(f" - Saved At:    {t_str}")
    print("=" * 65)
    print("Aap kya karna chahte hain?")
    print("  1) RESUME: Jaha se ruka tha wahi se continue karein (Pichla context reuse hoga)")
    print("  2) START FRESH: Naya kaam shuru karein (Purana task archive ho jayega)")
    print("=" * 65)

    # If running non-interactively (piped input, CI, or background service), do not block on input()
    if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        logger.info("Non-interactive terminal detected. Skipping interactive resume prompt.")
        return None

    try:
        choice = input("Option [1/2] (default: 1): ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "1"

    if choice in ("2", "fresh", "n", "new"):
        print("[Checkpoint] Starting fresh. Purana context archive kar diya gaya.\n")
        discard_active_checkpoint()
        return None
    else:
        print("[Checkpoint] Resuming from saved context...\n")
        return cp


def _register_signal_handlers() -> None:
    global _SIGNAL_REGISTERED
    if _SIGNAL_REGISTERED:
        return
    _SIGNAL_REGISTERED = True

    def _sig_handler(sig, frame):
        mark_interrupted()
        # Re-raise standard KeyboardInterrupt behavior
        sys.exit(130)

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        if hasattr(signal, "SIGBREAK"):  # Windows Ctrl+Break
            signal.signal(signal.SIGBREAK, _sig_handler)
    except Exception:
        pass

    atexit.register(lambda: None)
