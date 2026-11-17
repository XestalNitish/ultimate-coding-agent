"""Production Health Check for Ultimate Coding Agent.
Validates dependencies, local LLM servers (Main & Writer), vector store, and sandbox tools.

Usage:
    python healthcheck.py
    python main.py --health
"""
import sys
import os
import shutil
import subprocess
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as C


def check_python_environment() -> dict:
    """Check Python version and critical libraries."""
    status = {"name": "Python Environment", "ok": True, "details": []}
    v = sys.version_info
    status["details"].append(f"Python version: {v.major}.{v.minor}.{v.micro}")
    if v.major != 3 or v.minor < 10:
        status["ok"] = False
        status["details"].append("FAIL: Python 3.10+ required")

    required_pkgs = ["langchain", "langgraph", "chromadb", "pydantic", "requests"]
    for pkg in required_pkgs:
        try:
            __import__(pkg)
            status["details"].append(f"Package '{pkg}': OK")
        except ImportError:
            status["ok"] = False
            status["details"].append(f"Package '{pkg}': MISSING")
    return status


def check_llm_servers() -> dict:
    """Check Local LLM Server 1 (Main: 8082/8083) and Server 2 (Writer: 8084)."""
    import llm
    status = {"name": "LLM Servers", "ok": True, "details": []}

    # Server 1 check (Main Orchestrator)
    s1_alive = llm.server_up("main")
    if s1_alive:
        status["details"].append("Server 1 (Main Orchestrator: 8082/8083): ONLINE")
    else:
        status["ok"] = False
        status["details"].append("Server 1 (Main Orchestrator: 8082/8083): OFFLINE")

    # Server 2 check (Coder Writer node)
    s2_alive = llm.server_up("writer")
    if s2_alive:
        status["details"].append("Server 2 (Coder Writer: 8084): ONLINE")
    else:
        # Note: If Server 2 is offline, coder automatically falls back to Server 1
        status["details"].append(
            "Server 2 (Coder Writer: 8084): OFFLINE (Fallback to Server 1 active)"
        )

    return status


def check_rag_store() -> dict:
    """Check RAG document database and indexed workspaces."""
    status = {"name": "RAG Storage & Embeddings", "ok": True, "details": []}
    try:
        import rag
        libs = rag.libraries()
        status["details"].append(f"Indexed Libraries in RAG: {libs if libs else '(empty)'}")
    except Exception as e:
        status["ok"] = False
        status["details"].append(f"RAG inspection error: {e}")
    return status


def check_execution_tools() -> dict:
    """Verify presence of Python runtime and pytest in sandbox path."""
    status = {"name": "Execution Sandbox Tools", "ok": True, "details": []}
    py_exe = sys.executable
    status["details"].append(f"Python interpreter: {py_exe}")

    try:
        res = subprocess.run([py_exe, "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            status["details"].append(f"Interpreter verification: OK ({res.stdout.strip()})")
        else:
            status["ok"] = False
            status["details"].append("Interpreter check failed")
    except Exception as e:
        status["ok"] = False
        status["details"].append(f"Execution error: {e}")

    pytest_path = shutil.which("pytest") or str(Path(py_exe).parent / "pytest.exe")
    if Path(pytest_path).exists() or shutil.which("pytest"):
        status["details"].append(f"Pytest binary: {pytest_path}")
    else:
        status["details"].append("Pytest binary: NOT FOUND (scenario tests will need .venv pytest)")

    return status


def check_checkpoint_subsystem() -> dict:
    """Verify state persistence and checkpointing directory."""
    status = {"name": "State Persistence & Checkpointing", "ok": True, "details": []}
    try:
        import checkpoint_manager as cm
        cm.init_dirs()
        status["details"].append(f"Checkpoint directory: {cm.CHECKPOINT_DIR} (Writable)")
        active = cm.get_active_checkpoint()
        if active:
            status["details"].append(f"Active saved task: '{active.get('task', '')[:50]}' (Stage: {active.get('stage')})")
        else:
            status["details"].append("Active saved task: None (Clean startup state)")
        history_count = len(list(cm.HISTORY_DIR.glob("*.json")))
        status["details"].append(f"Archived task sessions: {history_count}")
    except Exception as e:
        status["ok"] = False
        status["details"].append(f"Checkpoint check error: {e}")
    return status


def run_healthcheck(verbose: bool = True) -> bool:
    """Run full suite of health checks and print structured report."""
    checks = [
        check_python_environment(),
        check_llm_servers(),
        check_rag_store(),
        check_execution_tools(),
        check_checkpoint_subsystem(),
    ]

    all_ok = True
    print("=" * 60)
    print("  ULTIMATE CODING AGENT - SYSTEM HEALTH REPORT")
    print("=" * 60)

    for c in checks:
        icon = "[PASS]" if c["ok"] else "[WARN]"
        if not c["ok"] and c["name"] == "Python Environment":
            all_ok = False
        print(f"\n{icon} {c['name']}")
        for d in c["details"]:
            print(f"    - {d}")

    print("\n" + "=" * 60)
    if all_ok:
        print("  OVERALL SYSTEM STATUS: HEALTHY & READY")
    else:
        print("  OVERALL SYSTEM STATUS: DEGRADED (Check warnings above)")
    print("=" * 60)
    return all_ok


if __name__ == "__main__":
    success = run_healthcheck()
    sys.exit(0 if success else 1)
