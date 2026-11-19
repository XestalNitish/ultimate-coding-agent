"""
local_llm_service.py - 100% offline X-Estal-4B (Spark-X2.5-4B GGUF) inference service via llama-server
========================================================================================================
Manages the local llama-server process. No external API calls.

What is different from the first version (all fixes for "server does not start / context full"):
- Server crashes are no longer silent: llama-server output goes to logs/llama_server.log.
- Unknown optional flags (--reasoning, --reasoning-budget, --no-reasoning-preserve, -ngl) are
  detected from the crash log and dropped automatically, then the server is restarted.
- Start-up wait is 120 s (a 4B model needs more than the old 5 s to load).
- Context window defaults to an auto-tuned 8192..16384 (was 4096) with -np 1 (one slot = full window).
- Threads = physical cores. GPU offload (-ngl 99) is tried, and dropped if the build/GPU can't do it.
- Output tokens are capped (was 1,000,000) -> XESTAL_MAX_TOKENS (default 4096).
- HTTP timeouts are realistic for local generation (was 15 s / 120 s) -> XESTAL_REQUEST_TIMEOUT (900 s).
- Health check no longer flips to "dead" under load (0.25 s -> 1.5 s), which could spawn a 2nd server.
- The server we started is stopped again at exit (set XESTAL_KEEP_SERVER=1 to keep it running).

Env knobs: XESTAL_MODEL_PATH, LLAMA_SERVER_BIN, XESTAL_PORT, XESTAL_CTX, XESTAL_THREADS,
           XESTAL_GPU_LAYERS (0 = CPU only), XESTAL_MAX_TOKENS, XESTAL_REQUEST_TIMEOUT, XESTAL_KEEP_SERVER
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional

import requests

logger = logging.getLogger("x_estal_llm_service")

_ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = int(os.getenv("XESTAL_PORT", "8082"))
DEFAULT_HOST = "127.0.0.1"
MAX_OUTPUT_TOKENS = int(os.getenv("XESTAL_MAX_TOKENS", "14000"))
REQUEST_TIMEOUT = int(os.getenv("XESTAL_REQUEST_TIMEOUT", "9000"))
LOG_FILE = _ROOT / "logs" / "llama_server.log"

_server_process: Optional[subprocess.Popen] = None

def strip_thinking(text: str) -> str:
    """Remove any thinking tags or internal monologue from output."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[THINKING\][\s\S]*?\[/THINKING\]", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _clamp_tokens(n: Any) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = MAX_OUTPUT_TOKENS
    return max(16, min(n, MAX_OUTPUT_TOKENS))


def get_model_path() -> Path:
    """Return path to downloaded GGUF weights."""
    env = os.getenv("XESTAL_MODEL_PATH")
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        _ROOT.parent / "models" / "XHToken__Spark-X2.5-4B-GGUF" / "Spark-X2.5-4B-Q4_K_M.gguf",
        _ROOT / "models" / "Spark-X2.5-4B-GGUF" / "Spark-X2.5-4B-Q4_K_M.gguf",
        Path("D:/ultimate coding agent/models/XHToken__Spark-X2.5-4B-GGUF/Spark-X2.5-4B-Q4_K_M.gguf"),
        Path("D:/ultimate coding agent/models/XHToken__Spark-X2.6-4B-GGUF/Spark-X2.6-4B-Q4_K_M.gguf"),
    ]
    for c in candidates:
        if c.exists():
            return c
    model_dir = _ROOT / "models" / "Spark-X2.5-4B-GGUF"
    if model_dir.exists():
        for f in model_dir.glob("*.gguf"):
            return f
    for search_dir in [_ROOT / "models", Path("D:/project2/models"), Path("d:/local llm/models")]:
        if search_dir.exists():
            for f in search_dir.rglob("*.gguf"):
                return f
    return candidates[0]


def get_server_binary() -> Optional[Path]:
    """Find local llama-server executable binary."""
    env = os.getenv("LLAMA_SERVER_BIN")
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        _ROOT / "llama_bin" / "llama-server.exe",
        _ROOT / "llama_bin" / "llama-server",
        _ROOT.parent / "local llm" / "llama_bin" / "llama-server.exe",
        Path("d:/local llm/llama_bin/llama-server.exe"),
        Path("D:/project2/llama_bin/llama-server.exe"),
    ]
    for c in candidates:
        if c.exists():
            return c
    for name in ["llama-server", "llama-server.exe"]:
        in_path = shutil.which(name)
        if in_path:
            return Path(in_path)
    return None


def is_local_capable() -> bool:
    """True if the server is up, or a binary + model exist so we can start it."""
    return is_server_alive() or (get_server_binary() is not None and get_model_path().exists())


def is_server_alive(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """True when the inference server is up and ready (503 while the model loads = not ready)."""
    for path in ("/health", "/v1/models"):
        try:
            if requests.get(f"http://{host}:{port}{path}", timeout=1.5).status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def get_context_size(port: int = DEFAULT_PORT) -> Optional[int]:
    """n_ctx the running server was started with (per slot), or None."""
    try:
        r = requests.get(f"http://{DEFAULT_HOST}:{port}/props", timeout=2)
        n = (r.json().get("default_generation_settings") or {}).get("n_ctx")
        return int(n) if n else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Auto-tuning for this computer
# --------------------------------------------------------------------------- #
def _auto_ctx(model: Optional[Path]) -> int:
    """Context window: env override, else sized to free RAM, clamped to 8192..16384."""
    env = os.getenv("XESTAL_CTX", "")
    if env.isdigit() and int(env) >= 1024:
        return int(env)
    try:
        import psutil
        avail = psutil.virtual_memory().available
        model_bytes = model.stat().st_size if model and model.exists() else 3 * 1024 ** 3
        ctx = int((avail * 0.70 - model_bytes) / (160 * 1024))   # ~0.15 MB of KV cache per token (4B, fp16)
    except Exception:  # noqa: BLE001
        return 12288
    return max(8192, min(ctx, 16384)) // 1024 * 1024


def _auto_threads() -> int:
    env = os.getenv("XESTAL_THREADS", "")
    if env.isdigit() and int(env) > 0:
        return int(env)
    n = None
    try:
        import psutil
        n = psutil.cpu_count(logical=False)
    except Exception:  # noqa: BLE001
        pass
    return max(1, n or (os.cpu_count() or 4) // 2)


# --------------------------------------------------------------------------- #
# Server lifecycle
# --------------------------------------------------------------------------- #
_BAD_ARG = re.compile(r"(?:invalid argument|unknown argument|unrecognized (?:option|argument)|unknown option)"
                      r"[:\s]+(\S+)", re.I)


def _tail_log(start_pos: int, n: int = 1500) -> str:
    try:
        with open(LOG_FILE, "rb") as f:
            f.seek(start_pos)
            return f.read().decode("utf-8", "replace")[-n:]
    except Exception:  # noqa: BLE001
        return ""


def start_local_server(
    port: int = DEFAULT_PORT,
    n_ctx: Optional[int] = None,
    n_threads: Optional[int] = None,
    wait_timeout: int = 120,
) -> bool:
    """
    Start llama-server in the background if it is not already running.
    Returns True once /health is OK. Output is written to logs/llama_server.log.
    """
    global _server_process

    if is_server_alive(DEFAULT_HOST, port):
        logger.info("Local X-Estal server already active on http://%s:%s", DEFAULT_HOST, port)
        return True

    exe = get_server_binary()
    model = get_model_path()
    if not exe or not exe.exists():
        logger.error("llama-server binary not found (put it in llama_bin/ or set LLAMA_SERVER_BIN).")
        return False
    if not model or not model.exists():
        logger.error("GGUF model not found (put it in models/ or set XESTAL_MODEL_PATH): %s", model)
        return False

    ctx = n_ctx or _auto_ctx(model)
    threads = n_threads or _auto_threads()
    gpu = os.getenv("XESTAL_GPU_LAYERS", "99")

    base = [str(exe), "-m", str(model), "--host", DEFAULT_HOST, "--port", str(port),
            "-c", str(ctx), "-np", "1",                 # one slot = the whole window belongs to one request
            "-t", str(threads), "-tb", str(threads)]
    # optional flags: dropped automatically when this llama-server build rejects them
    optional: List[List[str]] = [
        ["--reasoning", "off"],
        ["--reasoning-budget", "0"],
        ["--no-reasoning-preserve"],
    ]
    if gpu.isdigit() and int(gpu) > 0:
        optional.append(["-ngl", gpu])                  # last = first to be dropped on unexplained failures

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2_000_000:
        LOG_FILE.write_text("", encoding="utf-8")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW

    while True:
        cmd = base + [a for group in optional for a in group]
        start_pos = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
        logger.info("Starting llama-server (ctx=%s, threads=%s): %s", ctx, threads, " ".join(cmd[5:]))
        try:
            with open(LOG_FILE, "ab") as lf:
                lf.write(("\n=== start %s ===\n%s\n" % (time.strftime("%F %T"), " ".join(cmd))).encode())
                lf.flush()
                proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, creationflags=creationflags)
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to launch llama-server: %s", e)
            return False

        t0 = time.monotonic()
        died = False
        while time.monotonic() - t0 < wait_timeout:
            if proc.poll() is not None:
                died = True
                break
            if is_server_alive(DEFAULT_HOST, port):
                _server_process = proc
                logger.info("Local X-Estal server ready on http://%s:%s (ctx=%s)", DEFAULT_HOST, port, ctx)
                return True
            time.sleep(0.5)

        if not died:   # still loading after wait_timeout: leave it running, caller may keep polling
            _server_process = proc
            logger.warning("Server still loading after %ss (see %s).", wait_timeout, LOG_FILE)
            return False

        tail = _tail_log(start_pos)
        if is_server_alive(DEFAULT_HOST, port):        # port taken by another healthy server
            return True
        logger.warning("llama-server exited (code %s). Log tail:\n%s", proc.returncode, tail)
        if not optional:
            logger.error("llama-server cannot start. Full log: %s", LOG_FILE)
            return False
        bad = _BAD_ARG.search(tail)
        drop = next((g for g in optional if bad and g[0] == bad.group(1).strip("'\"`")), optional[-1])
        logger.warning("Retrying without %s", " ".join(drop))
        optional.remove(drop)


def stop_local_server() -> None:
    """Stop the server process that this module started (no-op for servers started elsewhere)."""
    global _server_process
    p, _server_process = _server_process, None
    if p is not None and p.poll() is None:
        try:
            p.terminate()
            p.wait(timeout=10)
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass


if os.getenv("XESTAL_KEEP_SERVER", "0") != "1":
    atexit.register(stop_local_server)


def _ensure_server(port: int) -> None:
    if is_server_alive(DEFAULT_HOST, port):
        return
    if not start_local_server(port=port):
        raise RuntimeError(
            "Local X-Estal server is offline and could not be started automatically. "
            f"Check the model in models/ and the log: {LOG_FILE}"
        )


# --------------------------------------------------------------------------- #
# Chat helpers
# --------------------------------------------------------------------------- #
def query_local_model(
    messages: List[Dict[str, str]],
    max_tokens: int = MAX_OUTPUT_TOKENS,
    temperature: float = 0.2,
    port: int = DEFAULT_PORT,
) -> Dict[str, Any]:
    """Synchronous completion. Thinking tags are stripped; returns only the clean answer."""
    _ensure_server(port)
    payload = {"messages": messages, "max_tokens": _clamp_tokens(max_tokens),
               "temperature": temperature, "stream": False}
    resp = requests.post(f"http://{DEFAULT_HOST}:{port}/v1/chat/completions",
                         json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Local server returned HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    content = strip_thinking(msg.get("content", ""))
    if not content:   # everything was inside think tags
        content = strip_thinking(msg.get("reasoning_content", "")) or "Done."
    return {"content": content, "display": content, "usage": data.get("usage", {}),
            "finish_reason": choice.get("finish_reason")}


def _partial_tag_len(low: str, tag: str) -> int:
    """Length of the longest suffix of `low` that is a proper prefix of `tag`."""
    for k in range(min(len(tag) - 1, len(low)), 0, -1):
        if low.endswith(tag[:k]):
            return k
    return 0


def filter_think_stream(tokens: Iterable[str]) -> Generator[str, None, None]:
    """Drop <think>...</think> blocks from a token stream (tags may be split across chunks)."""
    pending, in_think = "", False
    for tok in tokens:
        pending += tok
        while True:
            low = pending.lower()
            if in_think:
                i = low.find("</think>")
                if i == -1:
                    pending = pending[-7:]
                    break
                pending, in_think = pending[i + 8:], False
                continue
            i = low.find("<think>")
            if i == -1:
                keep = _partial_tag_len(low, "<think>")
                emit, pending = pending[:len(pending) - keep], pending[len(pending) - keep:]
                if emit:
                    yield emit
                break
            if i > 0:
                yield pending[:i]
            pending, in_think = pending[i + 7:], True
    if pending and not in_think:
        yield pending


def stream_local_model(
    messages: List[Dict[str, str]],
    max_tokens: int = MAX_OUTPUT_TOKENS,
    temperature: float = 0.2,
    port: int = DEFAULT_PORT,
) -> Generator[str, None, None]:
    """Stream clean response tokens; <think> blocks are filtered out live."""
    _ensure_server(port)
    payload = {"messages": messages, "max_tokens": _clamp_tokens(max_tokens),
               "temperature": temperature, "stream": True}

    def raw() -> Generator[str, None, None]:
        with requests.post(f"http://{DEFAULT_HOST}:{port}/v1/chat/completions", json=payload,
                           stream=True, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Local server returned HTTP {resp.status_code}: {resp.text[:300]}")
            for line in resp.iter_lines():
                if not line:
                    continue
                s = line.decode("utf-8", "replace")
                if not s.startswith("data: "):
                    continue
                part = s[6:].strip()
                if part == "[DONE]":
                    break
                try:
                    delta = (json.loads(part).get("choices") or [{}])[0].get("delta", {})
                except Exception:  # noqa: BLE001
                    continue
                tok = delta.get("content") or ""
                if tok:
                    yield tok

    yield from filter_think_stream(raw())


def get_local_chat_llm(
    temperature: float = 0.7,
    port: int = DEFAULT_PORT,
    auto_start: bool = False,
    max_tokens: Optional[int] = None,
):
    """LangChain ChatOpenAI connected to the local model (long timeout, capped output)."""
    if auto_start and not is_server_alive(DEFAULT_HOST, port):
        try:
            start_local_server(port=port)
        except Exception as e:  # noqa: BLE001
            logger.warning("auto_start failed: %s", e)

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        base_url=f"http://{DEFAULT_HOST}:{port}/v1",
        api_key="x-estal-local",
        model_name="X-Estal-4B",
        temperature=temperature,
        max_tokens=_clamp_tokens(max_tokens or MAX_OUTPUT_TOKENS),
        request_timeout=REQUEST_TIMEOUT,
        max_retries=1,
    )
