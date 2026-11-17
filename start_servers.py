"""3 llama-server local chalao (summarizer / main / coder), alag ports pe.

    python start_servers.py                 # teeno
    python start_servers.py --only main coder
    python start_servers.py --status        # kaun chal raha hai

Ctrl+C dabao to teeno band ho jaate hain. Logs: logs/server_<role>.log
"""
import argparse
import atexit
import shutil
import subprocess
import sys
import time

import config as C
import llm


def find_server() -> str:
    p = shutil.which(C.LLAMA_SERVER)
    if p:
        return p
    local = C.ROOT / "llama.cpp"
    if local.exists():
        for cand in local.rglob("llama-server*"):
            if cand.is_file() and cand.suffix in ("", ".exe"):
                return str(cand)
    raise SystemExit("llama-server nahi mila. `python download_llama_cpp.py` chalao "
                     "ya env LLAMA_SERVER me path do.")


def build_cmd(server: str, role: str) -> list[str]:
    cfg = C.MODELS[role]
    cmd = [server, "-m", str(C.model_path(role)),
            "--host", "127.0.0.1", "--port", str(cfg["port"]),
            "-c", str(cfg["ctx"]), "-t", str(C.THREADS), "-ngl", str(cfg["ngl"]),
            "-b", "2048", "-ub", "2048",
            "-np", "1",               # 1 slot: poori ctx ek request ko, parallel split nahi
            "--alias", role] + list(C.EXTRA_ARGS)
    if "--reasoning" not in cmd:
        cmd.extend(["--reasoning", "off"])
    return cmd


def launch(roles: list[str], wait: bool = True, timeout: int = 300) -> dict:
    """Servers start karo, health ka wait karo. -> {role: Popen}"""
    server = find_server()
    C.LOG_DIR.mkdir(parents=True, exist_ok=True)
    procs = {}
    for role in dict.fromkeys(C.real_role(r) for r in roles):     # same_as roles ek hi server
        if llm.server_up(role):
            print(f"[{role}] pehle se chal raha hai (port {C.MODELS[role]['port']})")
            continue
        if not C.model_path(role).exists():
            raise SystemExit(f"[{role}] model file nahi mili: {C.model_path(role)}\n"
                             f"Pehle: python download_models.py")
        log = open(C.LOG_DIR / f"server_{role}.log", "w", encoding="utf-8")
        procs[role] = subprocess.Popen(build_cmd(server, role), stdout=log, stderr=subprocess.STDOUT)
        print(f"[{role}] start (port {C.MODELS[role]['port']}, ctx {C.MODELS[role]['ctx']}, "
              f"ngl {C.MODELS[role]['ngl']}, threads {C.THREADS})")

    atexit.register(stop, procs)
    if wait:
        deadline = time.time() + timeout
        pending = set(procs)
        while pending and time.time() < deadline:
            for role in list(pending):
                if procs[role].poll() is not None:
                    raise SystemExit(f"[{role}] band ho gaya. logs/server_{role}.log dekho "
                                     f"(aksar: RAM/VRAM kam ya ngl zyada).")
                if llm.server_up(role):
                    print(f"[{role}] ready")
                    pending.discard(role)
            time.sleep(1.5)
        if pending:
            raise SystemExit(f"timeout: {sorted(pending)} ready nahi hue")
    return procs


def stop(procs: dict):
    for role, p in procs.items():
        if p.poll() is None:
            p.terminate()
    for p in procs.values():
        try:
            p.wait(timeout=8)
        except Exception:
            p.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(C.MODELS))
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        for r in C.MODELS:
            tag = f" (= {C.real_role(r)} ka server)" if C.real_role(r) != r else ""
            print(f"{r:11s} port {C.MODELS[C.real_role(r)]['port']}: {'UP' if llm.server_up(r) else 'down'}{tag}")
        return 0

    procs = launch(args.only or list(C.MODELS))
    print("\nSab ready. Ye terminal khula rakho. Dusre terminal me: python main.py")
    try:
        while procs and any(p.poll() is None for p in procs.values()):
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nband kar raha hoon...")
    finally:
        stop(procs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
