"""
code_dev_agent.py  (v2.3) - precise multi-file code generation agent (LangGraph)

Flow
    analyzer -> planner -> writer -> static_fix -> security_check -> executor -> reviewer
                  ^            ^                         |                |
                  |            +-------- debugger <------+--- runtime_fix (no LLM)
                  +------------- replan (after MAX_ITERATIONS) <-----------+

What is new in v2.3 (Audited & Patched)
- analyzer  : reads user task + research report, DECIDES if official docs are needed, queries RAG
              (optional). Preserves `docs_context` across replans, reads `last_replan_error`
              properly after replanning, and guarantees fallback queries when docs are needed.
- planner   : file layout with a CONTRACT per file (exports + depends_on). Cross-checks LLM plan
              against explicit files & multiline requirements in `user_plan` so workstream files
              are never dropped. Files are written in topological dependency order.
- writer    : only writes code, ONE file per LLM call, with a token-budgeted prompt. Automatically
              retries any missing planned files alongside `failed_files`.
- static_fix / runtime_fix : deterministic repair, NO LLM (missing imports, relative imports,
              wrong module paths, missing __init__.py, missing requirements, tabs, trailing prose,
              safe `pass` replacement for self-assignments).
- debugger  : explains the bug with the LLM only when it is a real logic error. Precise errors
              (static validation, SyntaxError, NameError, ImportError) are turned into fix
              instructions without any LLM call.
- context manager : every prompt is packed to fit (ctx - FREE_TOKENS). Long research/docs are
              summarised once (LLM, with deterministic fallback), code is shrunk to outlines /
              error-focused excerpts, and a "context too long" error from the server shrinks the
              budget automatically.
- replan    : after MAX_ITERATIONS failed attempts the working context is cleared, `last_replan_error`
              and a short "lesson" are kept, and the agent goes back to analyzer/planner.
- precision : AST validation (fixed walrus/comprehension false positives in `unbound_locals`),
              stub detection, import-resolution across files, undefined-name detection,
              regression guard, CLI entry-file detection, and headless Streamlit AppTest smoke test.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, TypedDict

try:
    from .local_llm_service2 import (
        DEFAULT_PORT as DEFAULT_PORT2,
        get_local_chat_llm2,
        is_server_alive as is_server_alive2,
        start_local_server as start_local_server2,
        strip_thinking as strip_thinking2,
    )
except ImportError:
    try:
        from local_llm_service2 import (
            DEFAULT_PORT as DEFAULT_PORT2,
            get_local_chat_llm2,
            is_server_alive as is_server_alive2,
            start_local_server as start_local_server2,
            strip_thinking as strip_thinking2,
        )
    except ImportError:
        DEFAULT_PORT2 = 8084
        get_local_chat_llm2 = None  # type: ignore[assignment]
        is_server_alive2 = lambda *a, **k: False  # noqa: E731
        start_local_server2 = lambda *a, **k: None  # noqa: E731
        strip_thinking2 = lambda x: x  # noqa: E731

try:
    from .local_llm_service import (
        DEFAULT_PORT,
        get_local_chat_llm,
        is_server_alive,
        start_local_server,
        strip_thinking,
    )
except ImportError:
    try:
        from local_llm_service import (
            DEFAULT_PORT,
            get_local_chat_llm,
            is_server_alive,
            start_local_server,
            strip_thinking,
        )
    except ImportError:
        DEFAULT_PORT = 8082
        get_local_chat_llm = None  # type: ignore[assignment]
        is_server_alive = lambda *a, **k: False  # noqa: E731
        start_local_server = lambda *a, **k: None  # noqa: E731
        strip_thinking = lambda x: x  # noqa: E731

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

log = logging.getLogger("code_dev_agent")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


MAX_ITERATIONS = _env_int("CODE_DEV_MAX_ITER", 4)
MAX_REPLANS = _env_int("CODE_DEV_MAX_REPLANS", 0)
MAX_SAME_ERROR = 3
MAX_AUTOFIX_ROUNDS = 3
MAX_FILES = 25
MAX_FILE_CHARS = 60_000
RUN_TIMEOUT = _env_int("CODE_DEV_RUN_TIMEOUT", 30)
SMOKE_TIMEOUT = _env_int("CODE_DEV_SMOKE_TIMEOUT", 90)
INSTALL_TIMEOUT = _env_int("CODE_DEV_INSTALL_TIMEOUT", 900)
LOCAL_SYNTAX_RETRIES = 2
TAIL = 3000

CHARS_PER_TOKEN = 3.0
FREE_TOKENS = _env_int("CODE_DEV_FREE_TOKENS", 4000)
CTX_TOKENS_ENV = _env_int("CODE_DEV_CTX_TOKENS", 0)
FALLBACK_CTX = 32768
LLM_URL = os.getenv("CODE_DEV_LLM_URL", f"http://127.0.0.1:{DEFAULT_PORT}")

EXT = {"python": ".py", "javascript": ".js", "bash": ".sh"}
DEFAULT_ENTRY = {"python": "main.py", "javascript": "main.js", "bash": "main.sh"}
STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def _import_local_llm_service():
    if __package__:
        try:
            from .local_llm_service import get_local_chat_llm as _fn
            return _fn
        except Exception:
            pass
    from local_llm_service import get_local_chat_llm as _fn
    return _fn


_active_llm: Any = None
_active_llm2: Any = None


def set_active_llm(llm: Any) -> None:
    """Set the globally active live LLM."""
    global _active_llm
    _active_llm = llm

def set_active_llm2(llm: Any) -> None:
    """Set the globally active live LLM."""
    global _active_llm2
    _active_llm2 = llm


def get_dev_llm(
    provider: str = "local",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1,
) -> Any:
    """Factory for LLM client. Defaults to local llama-server."""
    global _active_llm
    if _active_llm is not None and provider == "current":
        return _active_llm

    if provider in ("local", "auto") and get_local_chat_llm is not None:
        return get_local_chat_llm(temperature=temperature, auto_start=True)

    if provider == "groq":
        key = api_key or os.getenv("GROQ_API_KEY")
        if key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=key,
                    model_name=model or "llama-3.3-70b-versatile",
                    temperature=temperature,
                    request_timeout=60,
                    max_retries=1,
                )
            except Exception as e:
                log.warning(f"Groq initialization notice: {e}")

    if provider == "gemini":
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if key and not key.startswith("#"):
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key=key,
                    model_name=model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    temperature=temperature,
                    request_timeout=60,
                    max_retries=1,
                )
            except Exception as e:
                log.warning(f"Gemini initialization notice: {e}")

    if provider == "openai":
        key = api_key or os.getenv("OPENAI_API_KEY")
        if key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    api_key=key,
                    model_name=model or "gpt-4o-mini",
                    temperature=temperature,
                    request_timeout=60,
                    max_retries=1,
                )
            except Exception as e:
                log.warning(f"OpenAI initialization notice: {e}")

    if get_local_chat_llm is not None:
        return get_local_chat_llm(temperature=temperature, auto_start=True)
    return None


WRITER_URL = os.getenv("CODE_DEV_WRITER_URL", "")
WRITER_CTX_ENV = _env_int("CODE_DEV_WRITER_CTX_TOKENS", 0)
DEBUGGER_ON_WRITER = os.getenv("CODE_DEV_DEBUGGER_ON_WRITER", "0") == "1"
DBG_ROLE = "writer" if DEBUGGER_ON_WRITER else "main"
_UNSET = object()
_writer_tried = False


def get_dev_llm2(
    provider: str = "local",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1,
) -> Any:
    """Factory for LLM client. Defaults to local llama-server."""
    global _active_llm2
    if _active_llm2 is not None and provider == "current":
        return _active_llm2

    if provider in ("local", "auto") and get_local_chat_llm2 is not None:
        try:
            return get_local_chat_llm2(temperature=temperature, auto_start=True)
        except Exception as e:
            log.warning("get_local_chat_llm2 initialization notice: %s", e)

    # Fallback to get_dev_llm if dedicated writer server fails or cloud provider requested
    return get_dev_llm(provider=provider, api_key=api_key, model=model, base_url=base_url, temperature=temperature)


def _load_dev_tools() -> list:
    """Same tool sets as v1 (CODE_DEV / FILE_OPS / AI_ML / SECURITY_PRIVACY). Never crashes the import."""
    if os.getenv("CODE_DEV_LOAD_TOOLS", "1") == "0":
        return []
    mod = None
    if __package__:
        try:
            from . import tools as mod  # type: ignore
        except Exception:
            mod = None
    if mod is None:
        try:
            import tools as mod  # type: ignore
        except Exception as e:
            log.info("tools module not loaded (%s)", e)
            return []
    out: list = []
    for name in ("CODE_DEV_TOOLS", "FILE_OPS_TOOLS", "AI_ML_TOOLS", "SECURITY_PRIVACY_TOOLS"):
        out += list(getattr(mod, name, []) or [])
    return out


def _bind_dev(llm: Any) -> Any:
    try:
        return llm.bind_tools(DEV_TOOLS) if (llm is not None and DEV_TOOLS) else llm
    except Exception:
        return llm


DEV_TOOLS: list = _load_dev_tools()
_LAZY = os.getenv("CODE_DEV_LAZY_LLM", "1") == "1"
llm_base = None if _LAZY else get_dev_llm(os.getenv("RAG_PROVIDER", "local"))
_active_llm = llm_base
llm_summarizer = None
llm_dev = _bind_dev(llm_base)
llm_writer: Any = None if _LAZY else get_dev_llm2(os.getenv("RAG_PROVIDER", "local"))
_doc_retriever: Optional[Callable[[str], Any]] = None
_ctx_cache: Dict[str, int] = {}
_ctx_scales: Dict[str, float] = {"main": 1.0, "writer": 1.0}


def set_llm(coder: Any, summarizer: Any = None, writer: Any = _UNSET, writer_ctx: Optional[int] = None) -> None:
    """coder = planner/analyzer/debugger model. writer = optional model used ONLY to write code."""
    global llm_base, llm_summarizer, llm_dev, llm_writer, _active_llm
    llm_base, llm_summarizer, llm_dev = coder, summarizer, _bind_dev(coder)
    _active_llm = coder
    if writer is not _UNSET:
        llm_writer = writer
    _ctx_cache.pop("writer", None)
    if writer_ctx:
        _ctx_cache["writer"] = int(writer_ctx)


def set_doc_retriever(fn: Optional[Callable[[str], Any]]) -> None:
    """fn(query) -> str | list[Document] | None. None disables RAG (agent works without docs)."""
    global _doc_retriever
    _doc_retriever = fn


def _ensure_llm():
    global llm_base, llm_dev, _active_llm
    if llm_base is None:
        llm_base = _active_llm or get_dev_llm(os.getenv("RAG_PROVIDER", "local"))
        llm_dev = _bind_dev(llm_base)
    return llm_base


def _eff_role(role: str) -> str:
    """'writer' only if a dedicated writer model exists, otherwise everything runs on 'main'."""
    global llm_writer, _writer_tried
    if role == "writer" and not _writer_tried:
        _writer_tried = True
        if llm_writer is None:
            llm_writer = get_dev_llm2(os.getenv("CODE_DEV_PROVIDER", os.getenv("RAG_PROVIDER", "local")))
    return "writer" if (role == "writer" and llm_writer is not None) else "main"


def _fetch_n_ctx(url: str) -> int:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url.rstrip("/") + "/props", timeout=1.5) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return int(((data.get("default_generation_settings") or {}).get("n_ctx")) or data.get("n_ctx") or 0)
    except Exception:
        return 0


def ctx_tokens(role: str = "main") -> int:
    role = _eff_role(role)
    if role == "writer":
        if WRITER_CTX_ENV > 0:
            return WRITER_CTX_ENV
        if "writer" not in _ctx_cache:
            n = _fetch_n_ctx(WRITER_URL) if WRITER_URL else 0
            _ctx_cache["writer"] = n if n >= 1024 else ctx_tokens("main")
        return _ctx_cache["writer"]
    if CTX_TOKENS_ENV > 0:
        return CTX_TOKENS_ENV
    if "main" not in _ctx_cache:
        n = _fetch_n_ctx(LLM_URL)
        _ctx_cache["main"] = n if n >= 1024 else FALLBACK_CTX
    return _ctx_cache["main"]


def est_tokens(text: str) -> int:
    return int(len(text or "") / CHARS_PER_TOKEN) + 1


def prompt_budget(role: str = "main") -> int:
    """Max prompt tokens so that FREE_TOKENS stay free for the answer (per model role)."""
    role = _eff_role(role)
    return max(1200, int((ctx_tokens(role) - FREE_TOKENS) * _ctx_scales.get(role, 1.0)))


def _share(frac: float, lo: int = 600, hi: int = 6000, role: str = "main") -> int:
    """A fraction of the prompt budget, in characters."""
    return max(lo, min(hi, int(prompt_budget(role) * CHARS_PER_TOKEN * frac)))


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _response_text(response) -> str:
    c = getattr(response, "content", "") or getattr(response, "text", "")
    if (not c or not str(c).strip()) and hasattr(response, "additional_kwargs"):
        c = response.additional_kwargs.get("reasoning_content", "") or ""
    if isinstance(c, list):
        c = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    c = _THINK_RE.sub("", str(c) or "")
    if "<think>" in c and "</think>" not in c:
        c = re.sub(r"<think>[\s\S]*$", "", c)
    return c.strip()


_CTX_ERR = re.compile(r"context|n_ctx|exceed|too long|too many tokens|maximum|kv cache", re.I)


def _llm_text(system: str, user: str, retries: int = 2, summarizer: bool = False, role: str = "main") -> str:
    if os.environ.get("MOCK_LLM") == "1":
        try:
            import mock_llm
            return mock_llm.mock_chat(role, "coder" if role == "writer" else "planner", system, user)
        except Exception:
            pass
    role = _eff_role(role)
    llm = (
        llm_writer
        if role == "writer"
        else (llm_summarizer if (summarizer and llm_summarizer is not None) else _ensure_llm())
    )
    if llm is None:
        raise RuntimeError("LLM backend is not available")
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        room = int((prompt_budget(role) - est_tokens(system)) * CHARS_PER_TOKEN)
        u = user if len(user) <= room else middle_cut(user, max(500, room))
        try:
            text = _response_text(llm.invoke([SystemMessage(content=system), HumanMessage(content=u)]))
            if text.strip():
                return text
            last = RuntimeError("empty response")
        except Exception as e:
            last = e
            if _CTX_ERR.search(str(e)):
                _ctx_scales[role] = max(0.35, _ctx_scales.get(role, 1.0) * 0.7)
                log.warning("context error (%s model) -> shrinking prompt budget to x%.2f", role, _ctx_scales[role])
            elif role == "writer":
                fb = _ensure_llm()
                if fb is not None and fb is not llm:
                    log.warning("writer LLM failed (%s) - falling back to the main LLM", e)
                    role, llm = "main", fb
        if attempt < retries:
            time.sleep(min(2 ** attempt, 4))
    raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last}")


def middle_cut(text: str, n: int) -> str:
    text = text or ""
    if len(text) <= n:
        return text
    if n < 60:
        return text[: max(0, n)]
    keep = n - 20
    head = keep * 2 // 3
    return text[:head] + "\n...[trimmed]...\n" + text[-(keep - head) :]


def shrink_prose(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    keep: List[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or set(s) <= set("-|: "):
            continue
        if s.startswith(("#", "-", "*", "|")) or re.match(r"\d+[.)]\s", s):
            keep.append(s[:200])
        else:
            keep.append(re.split(r"(?<=[.!?])\s", s, maxsplit=1)[0][:200])
    out = "\n".join(keep)
    if len(out) <= max_chars:
        return out
    out = "\n".join(k[:90] for k in keep)
    return out if len(out) <= max_chars else middle_cut(out, max_chars)


def _py_tree(src: str) -> Optional[ast.AST]:
    try:
        return ast.parse(src)
    except (SyntaxError, ValueError, RecursionError, TypeError):
        return None


def _fn_sig(n: ast.AST) -> str:
    kw = "async def" if isinstance(n, ast.AsyncFunctionDef) else "def"
    ret = f" -> {ast.unparse(n.returns)}" if getattr(n, "returns", None) else ""
    return f"{kw} {n.name}({ast.unparse(n.args)}){ret}"  # type: ignore[attr-defined]


def _api_lines(tree: ast.AST) -> List[str]:
    sigs: List[str] = []
    for n in tree.body:  # type: ignore[attr-defined]
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not n.name.startswith("_"):
                sigs.append(_fn_sig(n))
        elif isinstance(n, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in n.bases)
            sigs.append(f"class {n.name}({bases})" if bases else f"class {n.name}")
            count = 0
            for m in n.body:
                if count >= 15:
                    break
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not m.name.startswith("_") or m.name == "__init__"
                ):
                    sigs.append("    " + _fn_sig(m))
                    count += 1
                elif isinstance(m, ast.AnnAssign) and isinstance(m.target, ast.Name):
                    sigs.append(f"    {m.target.id}: {ast.unparse(m.annotation)}")
                    count += 1
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_"):
                    sigs.append(f"{t.id} = ...")
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and not n.target.id.startswith("_"):
            sigs.append(f"{n.target.id}: {ast.unparse(n.annotation)}")
    return sigs


def shrink_code(text: str, max_chars: int) -> str:
    """Python -> public signatures only; other languages -> head/tail cut."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    tree = _py_tree(text)
    if tree is not None:
        outline = "\n".join(_api_lines(tree)) or "(no public API)"
        return outline if len(outline) <= max_chars else middle_cut(outline, max_chars)
    return middle_cut(text, max_chars)


def focus_excerpt(src: str, error: str, path: str, max_chars: int) -> str:
    """Whole file if it fits, else outline + numbered windows around the error lines."""
    if len(src) <= max_chars:
        return src
    base = PurePosixPath(path).name
    lines_hit = [
        int(m.group(2))
        for m in re.finditer(r'File "([^"]*)", line (\d+)', error or "")
        if m.group(1).replace("\\", "/").endswith(base)
    ]
    lines_hit += [int(m) for m in re.findall(r"line (\d+)", error or "")][:3]
    src_lines = src.splitlines()
    windows: List[str] = []
    seen = set()
    for ln in lines_hit[:3]:
        if ln in seen or ln < 1 or ln > len(src_lines):
            continue
        seen.add(ln)
        a, b = max(0, ln - 26), min(len(src_lines), ln + 25)
        windows.append("\n".join(f"{i + 1}: {src_lines[i]}" for i in range(a, b)))
    outline = shrink_code(src, max_chars // 3)
    out = "OUTLINE:\n" + outline
    if windows:
        out += "\n\nCODE AROUND THE ERROR (line numbers added):\n" + "\n...\n".join(windows)
    return middle_cut(out, max_chars)


class Sec:
    """A prompt section. protect=True -> never shrunk."""
    __slots__ = ("name", "text", "prio", "kind", "floor")

    def __init__(
        self,
        name: str,
        text: str,
        prio: int = 50,
        kind: str = "prose",
        floor: int = 0,
        protect: bool = False,
    ):
        self.name, self.text, self.prio, self.kind = name, (text or "").strip(), prio, kind
        self.floor = len(self.text) if protect else floor


def _render(secs: List[Sec]) -> str:
    return "\n\n".join(f"### {s.name}\n{s.text}" for s in secs if s.text)


def pack_sections(secs: List[Sec], budget_tokens: int) -> str:
    """Fit sections into the token budget: shrink lowest priority first, never protected ones."""
    secs = [s for s in secs if s.text]
    budget_chars = int(max(300, budget_tokens) * CHARS_PER_TOKEN)
    for _ in range(80):
        total = len(_render(secs))
        if total <= budget_chars:
            break
        cands = sorted((s for s in secs if len(s.text) > s.floor), key=lambda s: s.prio)
        if not cands:
            break
        s = cands[0]
        target = max(s.floor, min(len(s.text) // 2, len(s.text) - (total - budget_chars)))
        new = shrink_code(s.text, target) if s.kind == "code" else shrink_prose(s.text, target)
        if len(new) >= len(s.text):
            new = middle_cut(s.text, max(s.floor, len(s.text) // 2))
        s.text = new
    out = _render(secs)
    return out if len(out) <= budget_chars else middle_cut(out, budget_chars)


def summarize_text(text: str, target_chars: int, purpose: str = "") -> str:
    """Map-reduce summary with the (optional) summariser LLM; deterministic fallback."""
    text = (text or "").strip()
    if len(text) <= target_chars:
        return text
    if (llm_summarizer or llm_base) is None:
        return shrink_prose(text, target_chars)
    chunk_chars = max(1500, int(prompt_budget() * CHARS_PER_TOKEN * 0.5))
    if len(text) > chunk_chars * 4:
        text = shrink_prose(text, chunk_chars * 4)
    chunks = [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]
    per = max(400, target_chars // max(1, len(chunks)))
    parts: List[str] = []
    for c in chunks:
        try:
            parts.append(
                _llm_text(
                    "You compress technical notes. Output only the compressed notes, no preface.",
                    f"Purpose: {purpose[:300]}\nCompress to at most {per} characters. Keep EXACT names "
                    f"(libraries, functions, classes, CLI flags, versions, file names, numbers) and short "
                    f"code examples. Drop prose and repetition.\n\nTEXT:\n{c}",
                    retries=1,
                    summarizer=True,
                ).strip()
            )
        except Exception:
            parts.append(shrink_prose(c, per))
    out = "\n".join(p for p in parts if p)
    return out if len(out) <= target_chars else shrink_prose(out, target_chars)


def compact_context_text(text: str, max_chars: int = 1500, label: str = "") -> str:
    """Helper for context window compaction."""
    return summarize_text(text, max_chars, purpose=label)


def _note(state: dict, line: str, cap: int = 14) -> List[str]:
    """Rolling progress log; old entries collapse into one line."""
    notes = list(state.get("progress_notes") or []) + [line[:220]]
    if len(notes) > cap:
        head = "Earlier: " + "; ".join(n[:60] for n in notes[:-8])
        notes = [head[:600]] + notes[-8:]
    return notes


class CodeDevState(TypedDict, total=False):
    task: str
    language: Literal["python", "javascript", "bash"]
    user_plan: str
    research_report: str
    docs_context: str
    research_digest: str
    needs_docs: bool
    doc_queries: List[str]
    docs_available: bool
    docs_digest: str
    analysis_reason: str
    plan_context: str
    project_name: str
    entry_point: str
    run_mode: Literal["script", "server", "library"]
    planned_files: List[Dict[str, Any]]
    dependencies: List[str]
    files: Dict[str, str]
    prev_files: Dict[str, str]
    failed_files: List[str]
    file_path: str
    code: str
    output_dir: str
    workdir: str
    install_deps: bool
    security_passed: bool
    security_feedback: Optional[str]
    execution_output: str
    test_result: str
    error: Optional[str]
    last_replan_error: Optional[str]
    fix_instructions: str
    missing_modules: List[str]
    warnings: List[str]
    review_feedback: str
    status: str
    stop_reason: Optional[str]
    iteration_count: int
    max_iterations: int
    replan_count: int
    max_replans: int
    autofix_rounds: int
    autofix_changed: bool
    autofix_log: List[str]
    error_signatures: List[str]
    fix_history: List[str]
    lessons: List[str]
    progress_notes: List[str]
    final_output: str


def safe_rel_path(p: Optional[str]) -> Optional[str]:
    p = (p or "").strip().strip("`'\"").replace("\\", "/")
    if not p or p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p):
        return None
    parts = [x for x in PurePosixPath(p).parts if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts):
        return None
    if any(re.search(r'[<>:"|?*\x00-\x1f]', x) for x in parts):
        return None
    return "/".join(parts)


def parse_json_safely(raw_text: str) -> dict:
    clean = _THINK_RE.sub("", raw_text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if m:
        clean = m.group(1).strip()
    try:
        data = json.loads(clean)
        return data if isinstance(data, dict) else {}
    except Exception:
        s, e = clean.find("{"), clean.rfind("}")
        if s != -1 and e > s:
            try:
                data = json.loads(clean[s : e + 1])
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
    return {}


def extract_code(text: str, path: str = "main.py") -> str:
    """Strip <think> blocks, markdown fences and chatter; return raw file content."""
    text = _THINK_RE.sub("", text or "").strip()
    if path.endswith((".md", ".rst", ".txt")):
        m = re.fullmatch(r"```(?:markdown|md|text|txt|plaintext)?[ \t]*\r?\n(.*)\r?\n```", text, re.DOTALL | re.I)
        return (m.group(1) if m else text).strip()
    if path.endswith(".py") and _py_tree(text) is not None:
        return text
    blocks = re.findall(r"```[\w+.-]*[ \t]*\r?\n(.*?)```", text, re.DOTALL)
    if blocks:
        code = max(blocks, key=len)
    else:
        m = re.match(r"```[\w+.-]*[ \t]*\r?\n(.*)", text, re.DOTALL)
        code = m.group(1) if m else text
    code = re.sub(r"^[ \t]*```[\w+.-]*[ \t]*$", "", code, flags=re.MULTILINE)
    return code.strip()


def extract_code_block(raw_text: str, default_lang: str = "python") -> str:
    return extract_code(raw_text, "main" + EXT.get(default_lang, ".py"))


def _tail(s: Optional[str], n: int = TAIL) -> str:
    s = s or ""
    return s if len(s) <= n else "...[truncated]...\n" + s[-n:]


def _mod_name(path: str) -> str:
    p = path[:-3] if path.endswith(".py") else path
    parts = p.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py") or path.startswith("tests/")


_PIP_NAMES = {
    "fitz": "pymupdf", "PIL": "pillow", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "yaml": "pyyaml", "dotenv": "python-dotenv", "bs4": "beautifulsoup4",
    "faster_whisper": "faster-whisper", "sentence_transformers": "sentence-transformers",
    "multipart": "python-multipart", "ffmpeg": "ffmpeg-python", "docx": "python-docx",
    "pptx": "python-pptx", "jwt": "pyjwt", "dateutil": "python-dateutil", "attr": "attrs",
    "skimage": "scikit-image", "pydantic_settings": "pydantic-settings",
    "langchain_core": "langchain-core", "langchain_openai": "langchain-openai",
    "langchain_community": "langchain-community", "langchain_chroma": "langchain-chroma",
    "langchain_huggingface": "langchain-huggingface", "langchain_classic": "langchain-classic",
    "serial": "pyserial", "magic": "python-magic", "telegram": "python-telegram-bot",
}
_KNOWN_PIP = set(_PIP_NAMES) | {
    "fastapi", "uvicorn", "flask", "django", "streamlit", "requests", "httpx", "aiohttp", "numpy",
    "pandas", "scipy", "matplotlib", "plotly", "seaborn", "torch", "tensorflow", "transformers",
    "pydantic", "sqlalchemy", "pytest", "langchain", "langgraph", "chromadb", "faiss", "openai",
    "anthropic", "lxml", "pypdf", "openpyxl", "reportlab", "tqdm", "rich", "click", "typer",
    "jinja2", "redis", "pymongo", "boto3", "gradio", "whisper", "rank_bm25", "tiktoken",
}


def _norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(deps: List[str]) -> str:
    seen, out = set(), []
    for d in deps:
        d = d.strip().strip("`'\"")
        if not d:
            continue
        base = re.split(r"[<>=!~\[ ;]", d, maxsplit=1)[0]
        if base in STDLIB:
            continue
        d = _PIP_NAMES.get(base, d)
        if _norm_pkg(d) not in seen:
            seen.add(_norm_pkg(d))
            out.append(d)
    return "\n".join(out) + ("\n" if out else "")


_IGNORED_DOC_FILENAMES = {"a.py", "b.py", "x.py", "y.py", "foo.py", "bar.py", "example.py"}


def _files_from_text(text: str) -> List[str]:
    """Extract relative filenames mentioned in backticks, parentheses, or workstream headers."""
    text = text or ""
    found = re.findall(
        r"(?:`|[\(\s]|^)((?:[A-Za-z_][\w-]*/)*[A-Za-z_][\w-]*\.(?:py|js|ts|sh|txt|md|json|toml|ya?ml|html|css|cfg|ini))(?=`|[\)\s,:;]|$)",
        text,
        re.M,
    )
    out: List[str] = []
    for f in found:
        p = safe_rel_path(f)
        if p and p.lower() not in _IGNORED_DOC_FILENAMES and p not in out:
            out.append(p)
    return out


def _deps_from_text(text: str) -> List[str]:
    """Extract dependencies from inline `requirements.txt with: ...` or multiline requirements blocks."""
    text = text or ""
    out: List[str] = []
    m = re.search(r"requirements\.txt`?\s*with:?\s*([^\n]+)", text, re.I)
    if m:
        out += [x.strip().strip("`.") for x in m.group(1).split(",") if x.strip()]
    m_block = re.search(
        r"requirements\.txt\s*:\s*(?:Plaintext\s*)?\r?\n((?:[ \t]*[A-Za-z0-9_.-]+(?:[<>=!~]=?[\d.*]+)?[ \t]*\r?\n?)+)",
        text,
        re.I,
    )
    if m_block:
        for line in m_block.group(1).splitlines():
            pkg = line.strip().strip("`")
            if pkg and pkg.lower() != "plaintext" and re.match(r"^[A-Za-z0-9_.-]+(?:[<>=!~]=?[\d.*]+)?$", pkg):
                out.append(pkg)
    return out


def _ident_list(v: Any, limit: int = 20) -> List[str]:
    if isinstance(v, str):
        v = [x for x in re.split(r"[,\s]+", v) if x]
    out: List[str] = []
    for x in v or []:
        x = str(x).strip().split("(")[0].split(":")[0].strip()
        if re.fullmatch(r"[A-Za-z_]\w*", x) and x not in out:
            out.append(x)
    return out[:limit]


_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _defs_in_body(body: list, out: set) -> None:
    for n in body:
        if isinstance(n, _DEF_NODES):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        out.add(x.id)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                if a.name != "*":
                    out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.If):
            _defs_in_body(n.body, out)
            _defs_in_body(n.orelse, out)
        elif isinstance(n, ast.Try):
            _defs_in_body(n.body, out)
            _defs_in_body(n.orelse, out)
            _defs_in_body(n.finalbody, out)
            for h in n.handlers:
                _defs_in_body(h.body, out)
        elif isinstance(n, (ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)):
            _defs_in_body(n.body, out)
            _defs_in_body(getattr(n, "orelse", []), out)


def top_level_names(tree: Optional[ast.AST]) -> set:
    out: set = set()
    if tree is not None:
        _defs_in_body(tree.body, out)  # type: ignore[attr-defined]
    return out


def _has_star_import(tree: ast.AST) -> bool:
    return any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree))


def _has_future_annotations(tree: ast.AST) -> bool:
    return any(
        isinstance(n, ast.ImportFrom)
        and n.module == "__future__"
        and any(a.name == "annotations" for a in n.names)
        for n in ast.walk(tree)
    )


def _bound_names(tree: ast.AST) -> set:
    names: set = set()
    for n in ast.walk(tree):
        tn = type(n).__name__
        if isinstance(n, _DEF_NODES):
            names.add(n.name)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = n.args
            for x in a.posonlyargs + a.args + a.kwonlyargs:
                names.add(x.arg)
            if a.vararg:
                names.add(a.vararg.arg)
            if a.kwarg:
                names.add(a.kwarg.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                names.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
        elif tn in ("MatchAs", "MatchStar") and getattr(n, "name", None):
            names.add(n.name)  # type: ignore[attr-defined]
        elif tn == "MatchMapping" and getattr(n, "rest", None):
            names.add(n.rest)  # type: ignore[attr-defined]
        elif tn in ("TypeVar", "ParamSpec", "TypeVarTuple") and getattr(n, "name", None):
            names.add(n.name)  # type: ignore[attr-defined]
    return names


def _loads(tree: ast.AST, skip_annotations: bool) -> Dict[str, int]:
    skip: set = set()
    if skip_annotations:
        for n in ast.walk(tree):
            anns: list = []
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = n.args
                allargs = a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]
                anns += [x.annotation for x in allargs if x.annotation]
                if n.returns:
                    anns.append(n.returns)
            elif isinstance(n, ast.AnnAssign):
                anns.append(n.annotation)
            for an in anns:
                for m in ast.walk(an):
                    skip.add(id(m))
    out: Dict[str, int] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and id(n) not in skip:
            out.setdefault(n.id, n.lineno)
    return out


_BUILTIN_NAMES = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__spec__", "__path__",
    "__builtins__", "__package__", "__loader__", "__debug__",
    "__class__", "__annotations__",
}


def undefined_names(tree: ast.AST) -> List[Tuple[str, int]]:
    """Names that are read but never bound anywhere in the module."""
    if _has_star_import(tree):
        return []
    bound = _bound_names(tree)
    loads = _loads(tree, skip_annotations=_has_future_annotations(tree))
    return sorted(
        ((n, ln) for n, ln in loads.items() if n not in bound and n not in _BUILTIN_NAMES),
        key=lambda x: x[1],
    )


def _stub_functions(tree: ast.AST) -> List[str]:
    bad = []
    # Collect all method names that have concrete implementations in any class
    concrete_methods = set()
    class_methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    class_methods.add(item.name)
                    real_body = [
                        s for s in item.body
                        if not (
                            isinstance(s, ast.Expr)
                            and isinstance(getattr(s, "value", None), ast.Constant)
                            and isinstance(s.value.value, str)
                        )
                    ]
                    has_code = any(
                        not (
                            isinstance(s, ast.Pass)
                            or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis)
                            or (isinstance(s, ast.Raise) and "NotImplementedError" in ast.unparse(s))
                        )
                        for s in real_body
                    )
                    if has_code:
                        concrete_methods.add(item.name)

    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if n.name.startswith("__") and n.name.endswith("__"):
            continue
        decos = " ".join(ast.unparse(d) for d in n.decorator_list).lower()
        if "abstractmethod" in decos or "overload" in decos or "property" in decos:
            continue
        body = [
            s
            for s in n.body
            if not (
                isinstance(s, ast.Expr)
                and isinstance(getattr(s, "value", None), ast.Constant)
                and isinstance(s.value.value, str)
            )
        ]

        def _is_stub(s):
            if isinstance(s, ast.Pass):
                return True
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis:
                return True
            return isinstance(s, ast.Raise) and "NotImplementedError" in ast.unparse(s)

        if not body or all(_is_stub(s) for s in body):
            # If another class implements this method concretely, or it's a class method with NotImplementedError, don't flag
            if n.name in concrete_methods:
                continue
            if n.name in class_methods and any(isinstance(s, ast.Raise) and "NotImplementedError" in ast.unparse(s) for s in body):
                continue
            bad.append(n.name)
    return bad


def validate_content(path: str, content: str, project_paths: Optional[List[str]] = None) -> Optional[str]:
    """Return an error string if the file is not acceptable, else None."""
    if path.endswith("__init__.py"):
        return None if _py_tree(content or "") is not None else "invalid __init__.py"
    if not content or not content.strip():
        return "file is empty"
    if len(content) > MAX_FILE_CHARS:
        return f"file too large ({len(content)} chars)"
    if path.endswith(".py"):
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return f"SyntaxError line {e.lineno}: {e.msg}"
        stubs = _stub_functions(tree)
        if stubs:
            return f"stub/unimplemented functions (implement fully): {', '.join(stubs[:8])}"
        if project_paths:
            valid_mods = {p.replace(".py", "").replace("/", ".").replace("\\", ".") for p in project_paths}
            valid_roots = {m.split(".")[0] for m in valid_mods}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    if top in valid_roots and node.module not in valid_mods:
                        return f"Invalid internal import: '{node.module}' not found in project paths"
    elif path.endswith(".json"):
        try:
            json.loads(content)
        except Exception as e:
            return f"invalid JSON: {e}"
    return None


def top_level_definitions(tree: Optional[ast.AST]) -> set:
    if tree is None:
        return set()
    return {
        n.name
        for n in getattr(tree, "body", [])
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def _check_written(path: str, content: str, exports: List[str], previous: Optional[str]) -> Optional[str]:
    """Checks applied to every freshly written file (drives the writer's local retries)."""
    prob = validate_content(path, content)
    if prob or not path.endswith(".py"):
        return prob
    names = top_level_names(_py_tree(content))
    missing = [e for e in exports if e not in names]
    if missing:
        return f"missing required top-level definitions: {', '.join(missing)}"
    if previous and exports:
        # Only verify that required public exports were not accidentally dropped during rewrite
        prev_defs = top_level_definitions(_py_tree(previous))
        curr_defs = top_level_definitions(_py_tree(content))
        lost = sorted(n for n in (prev_defs - curr_defs) if n in exports)
        if lost:
            return f"you removed required export definitions that must be kept: {', '.join(lost[:8])}"
    return None


def _module_file(mod: str, files: Dict[str, str]) -> Optional[str]:
    base = mod.replace(".", "/")
    for cand in (base + ".py", base + "/__init__.py"):
        if cand in files:
            return cand
    return None


def _submodules(pkg_dir: str, files: Dict[str, str]) -> set:
    out = set()
    prefix = pkg_dir.rstrip("/") + "/"
    for p in files:
        if p.startswith(prefix):
            rest = p[len(prefix) :].split("/")
            out.add(rest[0].removesuffix(".py"))
    return out


def _fmt_from(mod: str, aliases: List[ast.alias]) -> str:
    names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in aliases)
    return f"from {mod} import {names}"


def _apply_line_edits(src: str, edits: List[Tuple[int, int, List[str]]]) -> str:
    """edits: (lineno, end_lineno, new statements) 1-based; applied bottom-up keeping indentation."""
    lines = src.split("\n")
    for ln, end, stmts in sorted(edits, key=lambda e: -e[0]):
        indent = re.match(r"\s*", lines[ln - 1]).group(0)
        lines[ln - 1 : end] = [indent + s for s in stmts]
    return "\n".join(lines)


def resolve_local_imports(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str], List[Tuple[str, str]]]:
    """Check/repair `from <project module> import name`. Returns (files, changes, unresolved)."""
    out = dict(files)
    changes: List[str] = []
    unresolved: List[Tuple[str, str]] = []
    py = [p for p in out if p.endswith(".py")]
    trees = {p: _py_tree(out[p]) for p in py}
    defs = {p: top_level_names(t) for p, t in trees.items()}
    stars = {p: (t is not None and _has_star_import(t)) for p, t in trees.items()}
    local_tops = {p.split("/")[0].removesuffix(".py") for p in out}
    stems: Dict[str, List[str]] = {}
    for p in py:
        stems.setdefault(PurePosixPath(p).stem, []).append(p)

    for path in py:
        tree = trees[path]
        if tree is None:
            continue
        edits: List[Tuple[int, int, List[str]]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            mod = node.module
            top = mod.split(".")[0]
            target = _module_file(mod, out)
            if target is None:
                pkg_dir = mod.replace(".", "/")
                is_dir = any(p.startswith(pkg_dir + "/") for p in out)
                if is_dir:
                    subs = _submodules(pkg_dir, out)
                    bad = [a.name for a in node.names if a.name != "*" and a.name not in subs]
                    for b in bad:
                        unresolved.append(
                            (
                                path,
                                f"line {node.lineno}: `from {mod} import {b}` - '{b}' not found "
                                f"in package '{mod}' (has: {', '.join(sorted(subs)) or 'nothing'})",
                            )
                        )
                elif top in local_tops:
                    near = sorted(m for m in (_mod_name(p) for p in py) if m.split(".")[0] == top)
                    unresolved.append(
                        (
                            path,
                            f"line {node.lineno}: module '{mod}' does not exist in the project "
                            f"(project modules: {', '.join(near[:10]) or '-'})",
                        )
                    )
                elif "." not in mod and top not in STDLIB and len(stems.get(mod, [])) == 1:
                    new_mod = _mod_name(stems[mod][0])
                    edits.append((node.lineno, node.end_lineno or node.lineno, [_fmt_from(new_mod, node.names)]))
                    changes.append(f"{path}: `from {mod} import ...` -> `from {new_mod} import ...`")
                continue
            if stars.get(target):
                continue
            known = set(defs.get(target, set()))
            if target.endswith("__init__.py"):
                known |= _submodules(PurePosixPath(target).parent.as_posix(), out)
            missing = [a for a in node.names if a.name != "*" and a.name not in known]
            if not missing:
                continue
            kept = [a for a in node.names if a not in missing]
            moved: Dict[str, List[ast.alias]] = {}
            for a in missing:
                cands = [p for p in py if p not in (target, path) and a.name in defs.get(p, set())]
                if len(cands) == 1:
                    moved.setdefault(_mod_name(cands[0]), []).append(a)
                else:
                    unresolved.append(
                        (
                            path,
                            f"line {node.lineno}: `from {mod} import {a.name}` - '{a.name}' is not "
                            f"defined in {target} (defined there: "
                            f"{', '.join(sorted(n for n in known if not n.startswith('_'))[:12]) or '-'})",
                        )
                    )
            if moved:
                stmts = ([_fmt_from(mod, kept)] if kept else []) + [_fmt_from(m, al) for m, al in moved.items()]
                still_bad = [a for a in missing if not any(a in al for al in moved.values())]
                if still_bad:
                    stmts.insert(0, _fmt_from(mod, still_bad))
                edits.append((node.lineno, node.end_lineno or node.lineno, stmts))
                changes.append(
                    f"{path}: moved import of {', '.join(a.name for al in moved.values() for a in al)} "
                    f"to {', '.join(moved)}"
                )
        if edits:
            new = _apply_line_edits(out[path], edits)
            if _py_tree(new) is not None:
                out[path] = new
    return out, changes, unresolved


def validate_project(files: Dict[str, str], planned: List[str], entry: str = "") -> List[Tuple[str, str]]:
    problems: List[Tuple[str, str]] = []
    for path in dict.fromkeys(list(planned) + list(files)):
        if path not in files:
            problems.append((path, "planned file was never written"))
            continue
        err = validate_content(path, files[path])
        if err:
            problems.append((path, err))
    py = {p: _py_tree(c) for p, c in files.items() if p.endswith(".py")}
    _, _, unresolved = resolve_local_imports({p: c for p, c in files.items()})
    seen = set()
    for p, m in unresolved:
        if (p, m) not in seen:
            seen.add((p, m))
            problems.append((p, m))
    for p, tree in py.items():
        if tree is None:
            continue
        und = undefined_names(tree)
        if und:
            problems.append((p, "undefined names: " + ", ".join(f"'{n}' (line {ln})" for n, ln in und[:6])))
        ub = unbound_locals(tree)
        if ub:
            problems.append(
                (
                    p,
                    "name used before assignment (UnboundLocalError): "
                    + ", ".join(f"'{n}' in {fn}() line {ln}" for n, ln, fn in ub[:5]),
                )
            )
        ms = missing_self_methods(tree)
        if ms:
            problems.append(
                (
                    p,
                    "calls methods that the class never defines: "
                    + ", ".join(f"self.{n}() in class {c} line {ln}" for n, ln, c in ms[:5]),
                )
            )
    if all(t is not None for t in py.values()):
        problems += project_conflicts(files, entry)
    return problems


_TYPING_NAMES = {
    "List", "Dict", "Optional", "Any", "Tuple", "Set", "Union", "Callable", "Iterable",
    "Iterator", "Sequence", "Mapping", "Literal", "TypedDict", "Generator", "Awaitable",
    "Type", "ClassVar", "Protocol", "Final", "TypeVar", "Generic", "NamedTuple",
    "AsyncIterator", "cast", "TYPE_CHECKING", "FrozenSet", "Deque",
}
_FROM_AUTO = {
    "Path": "pathlib", "dataclass": "dataclasses", "field": "dataclasses", "Enum": "enum", "ABC": "abc",
    "abstractmethod": "abc", "defaultdict": "collections", "Counter": "collections",
    "deque": "collections", "OrderedDict": "collections", "namedtuple": "collections",
    "partial": "functools", "lru_cache": "functools", "wraps": "functools",
    "contextmanager": "contextlib", "timedelta": "datetime", "timezone": "datetime", "Decimal": "decimal",
    "StringIO": "io", "BytesIO": "io",
}
_IMPORT_AUTO = {
    "os", "sys", "re", "json", "time", "math", "random", "logging", "hashlib", "subprocess",
    "shutil", "tempfile", "uuid", "pickle", "itertools", "functools", "collections", "argparse",
    "asyncio", "threading", "traceback", "textwrap", "csv", "glob", "io", "string", "copy",
    "base64", "sqlite3", "inspect", "operator", "signal", "socket", "statistics", "secrets",
    "platform", "zipfile", "warnings", "contextlib", "dataclasses", "typing", "enum", "abc",
    "pathlib", "queue", "heapq", "bisect", "decimal", "struct", "zlib", "gzip", "getpass",
    "pprint", "difflib", "fnmatch", "configparser", "unicodedata",
}


def _insert_imports(src: str, tree: ast.AST, stmts: List[str]) -> str:
    lines = src.split("\n")
    body = tree.body  # type: ignore[attr-defined]
    idx, i = 0, 0
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        idx, i = body[0].end_lineno or 0, 1
    while i < len(body) and isinstance(body[i], ast.ImportFrom) and body[i].module == "__future__":
        idx, i = body[i].end_lineno or idx, i + 1
    lines[idx:idx] = stmts
    return "\n".join(lines)


def _auto_import_stmts(need: List[str], tree: ast.AST) -> List[str]:
    stmts: List[str] = []
    typing_names = sorted(n for n in need if n in _TYPING_NAMES)
    if typing_names:
        stmts.append("from typing import " + ", ".join(typing_names))
    for n in sorted(need):
        if n in _TYPING_NAMES:
            continue
        if n == "datetime":
            attrs = {
                a.attr
                for a in ast.walk(tree)
                if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "datetime"
            }
            stmts.append(
                "import datetime"
                if attrs & {"datetime", "timedelta", "date", "timezone", "time"}
                else "from datetime import datetime"
            )
        elif n in _FROM_AUTO:
            stmts.append(f"from {_FROM_AUTO[n]} import {n}")
        else:
            stmts.append(f"import {n}")
    return stmts


def fix_missing_imports(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    out, changes = dict(files), []
    for path, src in files.items():
        if not path.endswith(".py"):
            continue
        tree = _py_tree(src)
        if tree is None or _has_star_import(tree):
            continue
        bound = _bound_names(tree)
        auto = _TYPING_NAMES | set(_FROM_AUTO) | _IMPORT_AUTO | {"datetime"}
        need = [n for n in _loads(tree, skip_annotations=False) if n not in bound and n in auto]
        if not need:
            continue
        new = _insert_imports(src, tree, _auto_import_stmts(need, tree))
        if _py_tree(new) is not None:
            out[path] = new
            changes.append(f"{path}: added missing imports for {', '.join(sorted(need))}")
    return out, changes


def fix_relative_imports(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    out, changes = dict(files), []
    for path, src in files.items():
        if not path.endswith(".py"):
            continue
        tree = _py_tree(src)
        if tree is None:
            continue
        pkg = list(PurePosixPath(path).parent.parts)
        edits: List[Tuple[int, int, List[str]]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            up = node.level - 1
            if up > len(pkg):
                continue
            base = pkg[: len(pkg) - up]
            if node.module:
                base += node.module.split(".")
                stmts = [_fmt_from(".".join(base), node.names)]
            elif base:
                stmts = [_fmt_from(".".join(base), node.names)]
            else:
                stmts = [f"import {a.name}" + (f" as {a.asname}" if a.asname else "") for a in node.names]
            edits.append((node.lineno, node.end_lineno or node.lineno, stmts))
        if edits:
            new = _apply_line_edits(src, edits)
            if _py_tree(new) is not None:
                out[path] = new
                changes.append(f"{path}: relative imports -> absolute imports")
    return out, changes


def ensure_init_files(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    out, changes = dict(files), []
    dirs = set()
    for p in files:
        if p.endswith(".py"):
            parts = PurePosixPath(p).parent.parts
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
    for d in sorted(dirs):
        init = f"{d}/__init__.py"
        if init not in out:
            out[init] = ""
            changes.append(f"{init}: created (empty package marker)")
    return out, changes


def fix_requirements(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    py = [p for p in files if p.endswith(".py")]
    if not py:
        return files, []
    local_tops = {p.split("/")[0].removesuffix(".py") for p in files}
    needed: Dict[str, str] = {}
    for p in py:
        tree = _py_tree(files[p])
        if tree is None:
            continue
        for n in ast.walk(tree):
            mods: List[str] = []
            if isinstance(n, ast.Import):
                mods = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                mods = [n.module.split(".")[0]]
            for m in mods:
                if m in STDLIB or m in local_tops or m not in _KNOWN_PIP:
                    continue
                needed[_norm_pkg(_PIP_NAMES.get(m, m))] = _PIP_NAMES.get(m, m)
    req = files.get("requirements.txt", "")
    have = {
        _norm_pkg(re.split(r"[<>=!~\[ ;#]", l.strip(), maxsplit=1)[0])
        for l in req.splitlines()
        if l.strip() and not l.strip().startswith("#")
    }
    add = [v for k, v in sorted(needed.items()) if k not in have]
    if not add:
        return files, []
    out = dict(files)
    out["requirements.txt"] = (req.rstrip("\n") + "\n" if req.strip() else "") + "\n".join(add) + "\n"
    return out, [f"requirements.txt: added {', '.join(add)}"]


def _looks_like_prose(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.startswith(("Here", "Note", "This ", "Explanation", "The ", "In ", "You ", "I ", "Let me", "Output")):
        return not re.search(r"[=(){}\[\]]", s)
    return len(s.split()) >= 4 and not re.search(r"[=(){}\[\]:#@]", s)


def repair_syntax_text(src: str) -> Tuple[str, Optional[str]]:
    """Cheap fixes for broken python: tabs, chatter before/after the code."""
    if _py_tree(src) is not None:
        return src, None
    if "\t" in src:
        t = src.expandtabs(4)
        if _py_tree(t) is not None:
            return t, "tabs expanded"
    lines = src.split("\n")
    for k in range(1, 13):
        if k >= len(lines):
            break
        if all(_looks_like_prose(l) for l in lines[-k:]):
            new = "\n".join(lines[:-k]).rstrip() + "\n"
            if _py_tree(new) is not None:
                return new, f"removed {k} trailing prose line(s)"
    for k in range(1, 6):
        if k >= len(lines):
            break
        if all(_looks_like_prose(l) for l in lines[:k]):
            new = "\n".join(lines[k:])
            if _py_tree(new) is not None:
                return new, f"removed {k} leading prose line(s)"
    return src, None


def fix_syntax(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    out, changes = dict(files), []
    for p, c in files.items():
        if p.endswith(".py") and c.strip():
            new, how = repair_syntax_text(c)
            if how:
                out[p] = new
                changes.append(f"{p}: {how}")
    return out, changes


def _files_in_trace(err: str, files: Dict[str, str]) -> List[str]:
    found: List[str] = []
    for m in re.finditer(r'File "([^"]+)", line \d+', err or ""):
        norm = m.group(1).replace("\\", "/")
        best = max((r for r in files if norm.endswith("/" + r) or norm == r), key=len, default=None)
        if best and best not in found:
            found.append(best)
    return list(reversed(found))


def fix_from_error(files: Dict[str, str], err: str) -> Tuple[Dict[str, str], List[str]]:
    """Runtime-error specific repairs (NameError from project module or standard library/typing)."""
    m = re.search(r"NameError: name '(\w+)' is not defined", err or "")
    if not m:
        return files, []
    name = m.group(1)
    traced = _files_in_trace(err, files)
    if not traced:
        traced = [p for p in files if p.endswith(".py")]
    if not traced:
        return files, []
    path = traced[0]
    tree = _py_tree(files[path])
    if tree is None:
        return files, []

    # Check 1: Standard library or typing auto-imports
    stmt = None
    if name in _IMPORT_AUTO:
        stmt = f"import {name}"
    elif name in _FROM_AUTO:
        stmt = f"from {_FROM_AUTO[name]} import {name}"
    elif name in _TYPING_NAMES:
        stmt = f"from typing import {name}"
    elif name == "datetime":
        stmt = "from datetime import datetime, timedelta"
    elif name == "timedelta":
        stmt = "from datetime import timedelta"
    elif name in ("ABC", "abstractmethod"):
        stmt = "from abc import ABC, abstractmethod"

    if stmt:
        new = _insert_imports(files[path], tree, [stmt])
        if _py_tree(new) is not None:
            out = dict(files)
            out[path] = new
            return out, [f"{path}: auto-added `{stmt}` (NameError: {name})"]

    # Check 2: Name defined in another project module
    cands = [
        p
        for p, c in files.items()
        if p.endswith(".py") and p != path and name in top_level_names(_py_tree(c))
    ]
    if len(cands) == 1:
        new = _insert_imports(files[path], tree, [f"from {_mod_name(cands[0])} import {name}"])
        if _py_tree(new) is not None:
            out = dict(files)
            out[path] = new
            return out, [f"{path}: added `from {_mod_name(cands[0])} import {name}` (NameError)"]
    return files, []


_NESTED_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _scope_walk(body: list):
    """Walk statements/expressions of ONE function scope (does not enter nested scopes)."""
    stack = list(reversed(body))
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, _NESTED_SCOPES):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(n))))


def _end(n: ast.AST) -> Tuple[int, int]:
    return (
        getattr(n, "end_lineno", None) or n.lineno,  # type: ignore[attr-defined]
        getattr(n, "end_col_offset", None) or 0,  # type: ignore[attr-defined]
    )


def unbound_locals(tree: ast.AST) -> List[Tuple[str, int, str]]:
    """(name, line, function) for names read before they are assigned in the same function
    (e.g. `storage = storage` -> UnboundLocalError). Fixed to handle walrus `:=` properly."""
    out: List[Tuple[str, int, str]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = fn.args
        params = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
        if a.vararg:
            params.add(a.vararg.arg)
        if a.kwarg:
            params.add(a.kwarg.arg)
        declared: set = set()
        stores: Dict[str, Tuple[int, int]] = {}
        loads: Dict[str, List[Tuple[int, int]]] = {}
        loops: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []

        def store(name: str, pos: Tuple[int, int]) -> None:
            if name not in stores or pos < stores[name]:
                stores[name] = pos

        for n in _scope_walk(fn.body):
            if isinstance(n, (ast.Global, ast.Nonlocal)):
                declared.update(n.names)
            elif isinstance(n, ast.Assign):
                # Store happens AFTER the RHS value is evaluated
                rhs_end = _end(n.value)
                for t in n.targets:
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                            store(x.id, rhs_end)
            elif isinstance(n, ast.AnnAssign) and n.value is not None and isinstance(n.target, ast.Name):
                store(n.target.id, _end(n.value))
            elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                loads.setdefault(n.target.id, []).append((n.target.lineno, n.target.col_offset))
                store(n.target.id, _end(n))
            elif isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
                # Walrus operator binds immediately after its value expression completes
                store(n.target.id, _end(n.value))
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                for x in ast.walk(n.target):
                    if isinstance(x, ast.Name):
                        store(x.id, (n.lineno, n.col_offset))
                loops.append(((n.lineno, n.col_offset), _end(n)))
            elif isinstance(n, ast.While):
                loops.append(((n.lineno, n.col_offset), _end(n)))
            elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                for x in ast.walk(n.optional_vars):
                    if isinstance(x, ast.Name):
                        store(x.id, (x.lineno, x.col_offset))
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for al in n.names:
                    store((al.asname or al.name).split(".")[0], (n.lineno, n.col_offset))
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                store(n.name, (n.lineno, n.col_offset))
            elif isinstance(n, ast.ExceptHandler) and n.name:
                store(n.name, (n.lineno, n.col_offset))
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                loads.setdefault(n.id, []).append((n.lineno, n.col_offset))
        for name, spos in stores.items():
            if name in params or name in declared:
                continue
            bad = [
                p
                for p in loads.get(name, [])
                if p < spos and not any(s <= p <= e and s <= spos <= e for s, e in loops)
            ]
            if bad:
                out.append((name, min(bad)[0], fn.name))
    return out


class _Pos:
    """(lineno, utf-8 col offset) -> absolute character index (bounds-safe)."""
    def __init__(self, src: str):
        self.lines = src.split("\n")
        self.starts = [0]
        for l in self.lines:
            self.starts.append(self.starts[-1] + len(l) + 1)

    def idx(self, lineno: int, col: int) -> int:
        if not self.lines:
            return 0
        ln = max(1, min(lineno, len(self.lines)))
        line = self.lines[ln - 1]
        return self.starts[ln - 1] + len(line.encode("utf-8")[: max(0, col)].decode("utf-8", "ignore"))


def _apply_span_edits(src: str, edits: List[Tuple[int, int, str]]) -> str:
    for s, e, r in sorted(edits, key=lambda x: -x[0]):
        src = src[:s] + r + src[e:]
    return src


def fix_argparse_required(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """add_argument("title", required=True) -> TypeError at parser construction. Drop `required=`."""
    out, changes = dict(files), []
    for path, src in files.items():
        if not path.endswith(".py") or "add_argument" not in src:
            continue
        tree = _py_tree(src)
        if tree is None:
            continue
        pos = _Pos(src)
        edits: List[Tuple[int, int, str]] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and not node.args[0].value.startswith("-")
            ):
                for kw in node.keywords:
                    if kw.arg == "required":
                        s = pos.idx(kw.lineno, kw.col_offset)
                        e = pos.idx(kw.end_lineno or kw.lineno, kw.end_col_offset or 0)
                        m = re.match(r"\s*,\s*", src[e:])
                        if m:
                            e += m.end()
                        else:
                            m2 = re.search(r",\s*$", src[:s])
                            if m2:
                                s = m2.start()
                        edits.append((s, e, ""))
        if edits:
            new = _apply_span_edits(src, edits)
            if _py_tree(new) is not None:
                out[path] = new
                changes.append(f"{path}: removed invalid `required=` from {len(edits)} positional argparse argument(s)")
    return out, changes


def fix_rich_console_class_call(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """`Console.print(...)` on the class (instead of an instance) -> `Console().print(...)`."""
    out, changes = dict(files), []
    for path, src in files.items():
        if not path.endswith(".py") or "Console" not in src:
            continue
        tree = _py_tree(src)
        if tree is None:
            continue
        if not any(
            isinstance(n, ast.ImportFrom)
            and (n.module or "").startswith("rich")
            and any(a.name == "Console" for a in n.names)
            for n in ast.walk(tree)
        ):
            continue
        pos = _Pos(src)
        edits = []
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Attribute)
                and n.attr == "print"
                and isinstance(n.value, ast.Name)
                and n.value.id == "Console"
            ):
                edits.append(
                    (
                        pos.idx(n.value.lineno, n.value.col_offset),
                        pos.idx(n.value.end_lineno or n.value.lineno, n.value.end_col_offset or 0),
                        "Console()",
                    )
                )
        if edits:
            new = _apply_span_edits(src, edits)
            if _py_tree(new) is not None:
                out[path] = new
                changes.append(f"{path}: `Console.print` -> `Console().print` ({len(edits)}x)")
    return out, changes


def fix_self_assignment(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """`storage = storage` inside a function makes it a local -> UnboundLocalError.
    Replace the line with `pass` (preserving block structure) and import the name if needed."""
    out, changes = dict(files), []
    py = [p for p in files if p.endswith(".py")]
    stems = {PurePosixPath(p).stem: p for p in py}
    defs = {p: top_level_names(_py_tree(files[p])) for p in py}
    for path in py:
        src = files[path]
        tree = _py_tree(src)
        if tree is None:
            continue
        victims: List[Tuple[ast.Assign, str]] = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = fn.args
            params = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
            for n in _scope_walk(fn.body):
                if (
                    isinstance(n, ast.Assign)
                    and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)
                    and isinstance(n.value, ast.Name)
                    and n.targets[0].id == n.value.id
                    and n.value.id not in params
                ):
                    victims.append((n, n.value.id))
        if not victims:
            continue
        mod_names = top_level_names(tree)
        imports: List[str] = []
        todo: List[Tuple[ast.Assign, str]] = []
        for n, name in victims:
            if name in mod_names:
                todo.append((n, name))
            elif name in stems and stems[name] != path:
                modname = _mod_name(stems[name])
                imports.append(
                    f"import {name}" if "." not in modname else f"from {modname.rsplit('.', 1)[0]} import {name}"
                )
                todo.append((n, name))
            else:
                cands = [p for p in py if p != path and name in defs.get(p, set())]
                if len(cands) == 1:
                    imports.append(f"from {_mod_name(cands[0])} import {name}")
                    todo.append((n, name))
        if not todo:
            continue
        lines = src.split("\n")
        ls = list(lines)
        for n, _ in sorted(todo, key=lambda t: -t[0].lineno):
            indent = re.match(r"\s*", ls[n.lineno - 1]).group(0)
            ls[n.lineno - 1 : (n.end_lineno or n.lineno)] = [indent + "pass"]
        new = "\n".join(ls)
        if _py_tree(new) is None:
            continue
        new_tree = _py_tree(new)
        need = [i for i in dict.fromkeys(imports) if i.split()[-1] not in top_level_names(new_tree)]
        if need and new_tree is not None:
            new = _insert_imports(new, new_tree, need)
        if _py_tree(new) is not None:
            out[path] = new
            changes.append(
                f"{path}: replaced `{todo[0][1]} = {todo[0][1]}` with `pass` (UnboundLocalError)"
                + (f" and added `{need[0]}`" if need else "")
            )
    return out, changes


def missing_self_methods(tree: ast.AST) -> List[Tuple[str, int, str]]:
    """self.foo(...) where the class (no base classes) defines no `foo` -> AttributeError at runtime."""
    out: List[Tuple[str, int, str]] = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.bases or cls.keywords or cls.decorator_list:
            continue
        have = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for n in cls.body:
            if isinstance(n, ast.Assign):
                have |= {t.id for t in n.targets if isinstance(t, ast.Name)}
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                have.add(n.target.id)
        if {"__getattr__", "__getattribute__", "__slots__"} & have:
            continue
        for x in ast.walk(cls):
            if (
                isinstance(x, ast.Attribute)
                and isinstance(x.value, ast.Name)
                and x.value.id == "self"
                and isinstance(x.ctx, ast.Store)
            ):
                have.add(x.attr)
        for x in ast.walk(cls):
            if (
                isinstance(x, ast.Call)
                and isinstance(x.func, ast.Attribute)
                and isinstance(x.func.value, ast.Name)
                and x.func.value.id == "self"
                and x.func.attr not in have
                and not x.func.attr.startswith("__")
            ):
                out.append((x.func.attr, x.lineno, cls.name))
    return out


def _remove_toplevel_class(src: str, name: str) -> Optional[str]:
    tree = _py_tree(src)
    if tree is None:
        return None
    for n in tree.body:  # type: ignore[attr-defined]
        if isinstance(n, ast.ClassDef) and n.name == name:
            start = min([n.lineno] + [d.lineno for d in n.decorator_list])
            lines = src.split("\n")
            del lines[start - 1 : (n.end_lineno or n.lineno)]
            if 0 < start - 1 < len(lines) and not lines[start - 1].strip() and not lines[start - 2].strip():
                del lines[start - 1]
            return "\n".join(lines)
    return None


def _imports_module(tree: ast.AST, modname: str) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == modname and not n.level:
            return True
        if isinstance(n, ast.Import) and any(a.name == modname for a in n.names):
            return True
    return False


def _safe_class_fingerprint(n: ast.ClassDef) -> str:
    """Safe, non-recursive string fingerprint of a class body to prevent RecursionError."""
    try:
        return ast.unparse(n)
    except Exception:
        pass
    try:
        members = sorted(getattr(m, "name", "") for m in getattr(n, "body", []))
        return f"{n.name}:{':'.join(m for m in members if m)}:{len(getattr(n, 'body', []))}"
    except Exception:
        return f"{getattr(n, 'name', 'cls')}:{id(n)}"


def dedupe_identical_classes(
    files: Dict[str, str], order: Optional[List[str]] = None
) -> Tuple[Dict[str, str], List[str]]:
    """The same class copy-pasted into two modules -> keep the first one, import it in the other."""
    out, changes = dict(files), []
    rank = {p: i for i, p in enumerate(order or [])}
    py = [p for p in files if p.endswith(".py") and not _is_test(p) and not p.endswith("__init__.py")]
    if len(py) < 2:
        return out, changes
    seen: Dict[Tuple[str, str], List[str]] = {}
    for p in py:
        tree = _py_tree(files[p])
        if tree is None:
            continue
        for n in getattr(tree, "body", []):
            if isinstance(n, ast.ClassDef):
                seen.setdefault((n.name, _safe_class_fingerprint(n)), []).append(p)
    for (name, _), paths in seen.items():
        if len(paths) < 2:
            continue
        paths = sorted(paths, key=lambda p: (rank.get(p, 10 ** 6), p))
        canon = paths[0]
        canon_tree = _py_tree(out[canon])
        for p in paths[1:]:
            if canon_tree is None or _imports_module(canon_tree, _mod_name(p)):
                continue
            new = _remove_toplevel_class(out[p], name)
            if new is None:
                continue
            tree = _py_tree(new)
            if tree is None:
                continue
            if name not in top_level_names(tree):
                new = _insert_imports(new, tree, [f"from {_mod_name(canon)} import {name}"])
            if _py_tree(new) is not None:
                out[p] = new
                changes.append(f"{p}: duplicate `class {name}` removed, imported from {canon}")
    return out, changes


_GENERIC_CLASS_NAMES = {"Config", "Meta", "Settings", "Base", "Error", "Test", "Item", "Node", "State", "App"}


def project_conflicts(files: Dict[str, str], entry: str = "") -> List[Tuple[str, str]]:
    """Cross-file design problems: duplicated classes, entry point re-implementing other modules."""
    probs: List[Tuple[str, str]] = []
    py = {
        p: _py_tree(c)
        for p, c in files.items()
        if p.endswith(".py") and not _is_test(p) and not p.endswith("__init__.py")
    }
    classes: Dict[str, List[Tuple[str, str]]] = {}
    funcs: Dict[str, set] = {}
    for p, t in py.items():
        if t is None:
            continue
        for n in getattr(t, "body", []):
            if isinstance(n, ast.ClassDef) and n.name not in _GENERIC_CLASS_NAMES:
                classes.setdefault(n.name, []).append((p, _safe_class_fingerprint(n)))
            elif (
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not n.name.startswith("_")
                and n.name not in ("main", "run", "app", "create_app")
            ):
                funcs.setdefault(p, set()).add(n.name)
    for name, items in classes.items():
        first = items[0]
        for p, d in items[1:]:
            kind = "identical" if d == first[1] else "different"
            probs.append(
                (
                    p,
                    f"class {name} is also defined in {first[0]} ({kind} body) - keep ONE definition "
                    f"and import it from there",
                )
            )
    if entry in funcs:
        for p, names in funcs.items():
            shared = sorted(funcs[entry] & names) if p != entry else []
            if len(shared) >= 3:
                probs.append(
                    (
                        entry,
                        f"re-implements {len(shared)} functions that already exist in {p} "
                        f"({', '.join(shared[:8])}) - delete them and import/call the originals "
                        f"from {_mod_name(p)}",
                    )
                )
    return probs


_PITFALLS = [
    (
        r"argparse|argumentparser|add_argument|subparsers",
        "argparse: positional arguments NEVER take required=; with type=int the value is already an int (no .isdigit()); "
        "give every subparser set_defaults(func=...).",
    ),
    (
        r"streamlit|\bst\.",
        "Streamlit: the file given to `streamlit run` must CALL the UI function at module level (e.g. `run_ui()`), not only "
        "define it; st.form needs st.form_submit_button; a button only acts inside `if st.button(...):`; "
        "`with st.container(border=True):`; st.tabs() returns containers (use `with tab:`, never compare a tab to a string); "
        "apply unique `key=` on every button/input inside a loop; convert date objects to str before saving JSON; "
        "call st.rerun() after changing data.",
    ),
    (r"\brich\b", "rich: create `console = Console()` and call console.print(...) on the INSTANCE (never `Console.print`)."),
    (r"pydantic|basemodel", "pydantic v2: use model_dump()/model_validate(); define each model ONCE and import it elsewhere."),
    (r"json\.dump|\bjson\b", "json: convert date/datetime/Path objects to str before json.dump; new ids = max(existing ids)+1."),
    (r"fastapi", "FastAPI: `app = FastAPI()` at module level; Pydantic models for request bodies; never start uvicorn at import time."),
    (r"flask", "Flask: `app = Flask(__name__)` at module level; `app.run()` only under `if __name__ == '__main__':`."),
]


def _pitfalls(blob: str) -> str:
    return "\n".join(f"- {t}" for pat, t in _PITFALLS if re.search(pat, blob))


def _infer_dependencies(planned: List[Dict[str, Any]], entry: str) -> None:
    """Make sure a file sees the real interfaces of the modules it is about to use."""
    py = [p for p in planned if p["path"].endswith(".py") and not p["path"].endswith("__init__.py")]
    by_path = {p["path"]: p for p in py}

    def reach(path: str) -> set:
        seen: set = set()
        stack = list(by_path.get(path, {}).get("depends_on", []))
        while stack:
            d = stack.pop()
            if d not in seen:
                seen.add(d)
                stack.extend(by_path.get(d, {}).get("depends_on", []))
        return seen

    def add(p: Dict[str, Any], q: Dict[str, Any]) -> None:
        if q["path"] != p["path"] and q["path"] not in p["depends_on"] and p["path"] not in reach(q["path"]):
            p["depends_on"].append(q["path"])

    for p in py:
        txt = f"{p.get('purpose', '')} {' '.join(p.get('exports') or [])}".lower()
        for q in py:
            if q is p or _is_test(q["path"]):
                continue
            stem = PurePosixPath(q["path"]).stem.lower()
            if len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", txt):
                add(p, q)
    ent = by_path.get(entry)
    if ent:
        for q in py:
            if q is not ent and not _is_test(q["path"]):
                add(ent, q)
    for t in py:
        if _is_test(t["path"]):
            for q in py:
                if not _is_test(q["path"]):
                    add(t, q)


def _cli_info(files: Dict[str, str], entry: str) -> Tuple[bool, str, List[str]]:
    """Determine if the project has an argparse CLI, which file runs it (`entry` or `cli.py`),
    and which sub-commands exist."""
    cli_files = {p for p, c in files.items() if p.endswith(".py") and "ArgumentParser(" in c}
    if not cli_files:
        return False, entry, []
    uses_entry = entry in cli_files
    if not uses_entry:
        tree = _py_tree(files.get(entry, ""))
        if tree is not None:
            for n in ast.walk(tree):
                mods: List[str] = []
                if isinstance(n, ast.ImportFrom) and n.module and not n.level:
                    mods = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
                elif isinstance(n, ast.Import):
                    mods = [a.name for a in n.names]
                if any(_module_file(m, files) in cli_files for m in mods):
                    uses_entry = True
    cli_runner = entry if uses_entry else sorted(cli_files)[0]
    subs: List[str] = []
    for p in sorted(cli_files, key=lambda x: (x != cli_runner, x)):
        for m in re.finditer(r"""\.add_parser\(\s*["']([\w-]+)["']""", files[p]):
            if m.group(1) not in subs:
                subs.append(m.group(1))
    return uses_entry, cli_runner, subs[:6]


_ST_SMOKE = r'''
import sys, os, json
sys.path.insert(0, os.getcwd())
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=45).run()
def _txt(e):
    v = getattr(e, "value", None) or getattr(e, "message", None) or ""
    st = getattr(e, "stack_trace", None) or []
    return (str(v) + "\n" + "\n".join(str(x) for x in st)).strip()
res = {"exceptions": [_txt(e) for e in at.exception],
       "errors": [str(getattr(e, "value", "")) for e in at.error],
       "elements": len(at.main) + len(at.sidebar)}
print("__ST__" + json.dumps(res))
'''
_ST_ERR_RE = re.compile(
    r"NameError|UnboundLocal|not defined|referenced before|where it is not associated|has no attribute|"
    r"ModuleNotFound|No module named|ImportError|TypeError|KeyError|AttributeError|JSON serializable|DuplicateWidgetID",
    re.I,
)


def _deep_checks(
    py: str,
    root: Path,
    files: Dict[str, str],
    env: Dict[str, str],
    entry: str,
    run_mode: str,
    cli_entry: bool,
    cli_runner: str,
    cli_subs: List[str],
    classify,
    missing: List[str],
    base_out: dict,
) -> Tuple[Optional[dict], List[str]]:
    """Checks that go beyond `import works`: CLI parsers are built, Streamlit apps really render."""
    logs: List[str] = []
    if cli_entry or cli_subs:
        cmds = [[py, cli_runner, s, "--help"] for s in cli_subs]
        if run_mode != "script" or cli_runner != entry:
            cmds.insert(0, [py, cli_runner, "--help"])
        ok = 0
        for cmd in cmds:
            rc, out, err, to = _run(cmd, root, 30, env)
            if to:
                continue
            if rc != 0:
                mod = classify(err)
                if mod:
                    missing.append(mod)
                    break
                return (
                    _fail(
                        f"CLI check failed: `{' '.join(cmd[1:])}` exited with code {rc}\n{_tail(err or out, 1800)}",
                        _failed_files_from_trace(err, root, files) or [cli_runner],
                        out,
                        "CLI check failed",
                        **base_out,
                    ),
                    logs,
                )
            ok += 1
        if ok:
            logs.append(f"CLI check ({cli_runner}): {ok} command(s) answered --help")
    st_files = [
        p for p, c in files.items() if p.endswith(".py") and re.search(r"^\s*(import streamlit|from streamlit)", c, re.M)
    ]
    if st_files:
        rc, _, _, _ = _run([py, "-c", "import streamlit"], root, 60, env, limits=False)
        if rc == 0:
            target = (
                entry
                if entry in st_files
                else next((p for p in ("ui.py", "app.py", "streamlit_app.py", "main.py") if p in st_files), st_files[0])
            )
            rc, out, err, to = _run([py, "-c", _ST_SMOKE, target], root, SMOKE_TIMEOUT, env)
            m = re.search(r"__ST__(.*)$", out or "", re.M)
            if m:
                data = json.loads(m.group(1))
                if data["exceptions"]:
                    txt = "\n\n".join(data["exceptions"])
                    return (
                        _fail(
                            f"Streamlit app `{target}` raised an exception when run headlessly (AppTest):\n"
                            f"{_tail(txt, 1800)}",
                            _failed_files_from_trace(txt, root, files) or [target],
                            "",
                            "Streamlit app crashed",
                            **base_out,
                        ),
                        logs,
                    )
                bad = [e for e in data["errors"] if _ST_ERR_RE.search(e)]
                if bad:
                    return (
                        _fail(
                            f"Streamlit app `{target}` shows an error on first load (a caught exception?): "
                            f"{bad[0][:500]}",
                            [target],
                            "",
                            "Streamlit app shows an error",
                            **base_out,
                        ),
                        logs,
                    )
                if data["elements"] == 0:
                    return (
                        _fail(
                            f"`{target}` renders nothing. The file passed to `streamlit run` must CALL the UI "
                            f"function at module level (e.g. `run_ui()`), not only define it.",
                            [target],
                            "",
                            "Streamlit app renders nothing",
                            **base_out,
                        ),
                        logs,
                    )
                logs.append(f"Streamlit AppTest: `{target}` rendered {data['elements']} element(s) without exceptions")
    return None, logs


def autofix_files(
    files: Dict[str, str], language: str = "python"
) -> Tuple[Dict[str, str], List[str], List[Tuple[str, str]]]:
    """Run every deterministic fixer until nothing changes (max 3 passes)."""
    if language != "python":
        return files, [], []
    cur, log_lines = dict(files), []
    unresolved: List[Tuple[str, str]] = []
    for _ in range(3):
        before = dict(cur)
        for fixer in (
            fix_syntax,
            fix_argparse_required,
            fix_rich_console_class_call,
            fix_relative_imports,
            fix_self_assignment,
            dedupe_identical_classes,
            fix_missing_imports,
        ):
            try:
                cur, ch = fixer(cur)
                log_lines += ch
            except Exception as e:
                log.warning("fixer %s failed: %s", getattr(fixer, "__name__", str(fixer)), e)
        try:
            cur, ch, unresolved = resolve_local_imports(cur)
            log_lines += ch
        except Exception as e:
            log.warning("resolve_local_imports failed: %s", e)
        for fixer in (fix_requirements, ensure_init_files):
            try:
                cur, ch = fixer(cur)
                log_lines += ch
            except Exception as e:
                log.warning("fixer %s failed: %s", getattr(fixer, "__name__", str(fixer)), e)
        if cur == before:
            break
    return cur, list(dict.fromkeys(log_lines)), unresolved


_KNOWN_LIBS = [
    "fastapi", "flask", "django", "streamlit", "langgraph", "langchain", "pandas", "numpy",
    "torch", "tensorflow", "sklearn", "requests", "httpx", "aiohttp", "sqlalchemy", "pydantic",
    "docker", "react", "express", "pytest", "opencv", "matplotlib", "plotly", "gradio", "chromadb",
    "faiss", "transformers", "whisper", "pymupdf", "reportlab", "selenium", "playwright", "uvicorn",
    "celery", "redis", "kafka", "spring", "tkinter", "pygame", "typer", "rich", "beautifulsoup4",
    "bs4", "lxml", "supabase", "boto3",
]
_DOC_WORDS = re.compile(
    r"\b(latest|official|documentation|docs?|api|sdk|version|deprecated|migrate|"
    r"integrat\w*|framework|library|endpoint)\b",
    re.I,
)


def _heuristic_docs_decision(text: str) -> Tuple[bool, List[str]]:
    low = (text or "").lower()
    libs = [l for l in _KNOWN_LIBS if re.search(rf"\b{re.escape(l)}\b", low)]
    need = bool(libs) or bool(_DOC_WORDS.search(text or ""))
    short_task = (text or "").splitlines()[0][:80].strip()
    queries = [f"{l} {short_task}".strip() for l in libs[:4]] or ([short_task[:150]] if need and short_task else [])
    return need, queries


def _call_retriever(q: str, warnings: List[str]) -> str:
    if _doc_retriever is None:
        return ""
    try:
        res = _doc_retriever(q)
    except Exception as e:
        warnings.append(f"RAG query failed ({type(e).__name__}: {str(e)[:120]}) - continuing without those docs")
        return ""
    if res is None:
        return ""
    if isinstance(res, str):
        return res.strip()
    try:
        return "\n\n".join(getattr(d, "page_content", str(d)) for d in res).strip()
    except TypeError:
        return str(res).strip()


def analyzer_node(state: CodeDevState) -> dict:
    task = state.get("task", "")
    language = state.get("language", "python")
    user_plan = state.get("user_plan") or ""
    lessons = state.get("lessons") or []
    warnings = list(state.get("warnings") or [])
    research = (state.get("research_report") or "").strip()
    digest = state.get("research_digest") or ""
    if research and not digest:
        digest = summarize_text(research, _share(0.18, 800, 5000), purpose=task)

    blob = f"{task}\n{user_plan[:2000]}\n{digest[:2000]}"
    need, queries = _heuristic_docs_decision(blob)
    reason = "heuristic"

    if _doc_retriever is not None or state.get("docs_context"):
        try:
            data = parse_json_safely(
                _llm_text(
                    "You decide whether a coder needs reference documentation. Output JSON only.",
                    f"Task: {task[:800]}\nLanguage: {language}\nResearch notes: {digest[:1200] or '(none)'}\n\n"
                    "Official docs (Python, JavaScript, FastAPI, Streamlit, Docker, ...) can be searched. "
                    "Docs are needed when the code uses a framework/library API, exact flags or version-specific "
                    "behaviour. Plain logic / standard-library tasks do NOT need docs.\n"
                    'Return ONLY JSON: {"needs_docs": true|false, "queries": ["<=4 short search queries"], '
                    '"reason": "<short>"}',
                    retries=1,
                )
            )
            if "needs_docs" in data:
                need = bool(data.get("needs_docs"))
                qs = [str(q).strip()[:150] for q in (data.get("queries") or []) if str(q).strip()]
                queries = qs[:4] or queries
                reason = str(data.get("reason", "llm"))[:160]
        except Exception as e:
            log.info("analyzer LLM failed (%s) - using heuristic", e)

    # Fixed Bug #1: Read `last_replan_error` (preserved across replan) as well as `error`
    replan_err = state.get("error") or state.get("last_replan_error") or ""
    if lessons and replan_err:
        need = True
        err_q = f"{task[:60]} {_error_signature(replan_err)}".strip()
        if err_q not in queries:
            queries = (queries + [err_q])[:5]

    # Fixed Bug #3: Ensure `queries` is never empty when `need` is True
    if need and not queries:
        queries = [f"{language} {task[:120]}".strip()]

    docs = (state.get("docs_context") or "").strip()
    available = len(docs) >= 40
    if need and _doc_retriever is not None:
        chunks = []
        seen = {c.strip()[:200] for c in docs.split("\n\n") if len(c.strip()) >= 40}
        for q in queries[:5]:
            txt = _call_retriever(q, warnings)
            key = txt[:200]
            if len(txt) >= 40 and key not in seen:
                seen.add(key)
                chunks.append(txt)
        if chunks:
            docs = (docs + "\n\n" if docs else "") + "\n\n".join(chunks)
        available = len(docs) >= 40
        if not available:
            warnings.append("RAG returned no usable docs - continuing without reference docs")
    elif need and _doc_retriever is None and not docs:
        reason += " | docs wanted but no RAG configured"

    docs_digest = summarize_text(docs, _share(0.22, 800, 5000), purpose=task) if available else ""

    # Fixed Bug #2: Persist `docs_context` in state so replans don't lose retrieved docs
    return {
        "research_digest": digest,
        "docs_context": docs,
        "needs_docs": need,
        "doc_queries": queries,
        "docs_available": available,
        "docs_digest": docs_digest,
        "analysis_reason": reason,
        "warnings": list(dict.fromkeys(warnings)),
        "progress_notes": _note(state, f"analysis: docs {'used' if available else 'not used'} ({reason[:60]})"),
    }


def _toposort(planned: List[Dict[str, Any]], entry: str) -> List[Dict[str, Any]]:
    by_path = {p["path"]: p for p in planned}
    order, state = [], {}

    def visit(path: str) -> None:
        if state.get(path) == 2:
            return
        if state.get(path) == 1:
            return
        state[path] = 1
        for d in by_path[path].get("depends_on") or []:
            if d in by_path and d != path:
                visit(d)
        state[path] = 2
        order.append(by_path[path])

    for p in planned:
        if p["path"].lower() in ("requirements.txt", "package.json", "pyproject.toml") and p["path"] != entry:
            visit(p["path"])
    for p in planned:
        if p["path"] != entry:
            visit(p["path"])
    if entry in by_path:
        visit(entry)
    return order


_topological_sort_files = _toposort


def planner_node(state: CodeDevState) -> dict:
    task = state.get("task", "")
    language = state.get("language", "python")
    user_plan = state.get("user_plan") or ""
    lessons = state.get("lessons") or []
    ext = EXT[language]

    if state.get("planned_files") and bool(state.get("files")):
        log.info("planner_node: Reusing %d planned files from checkpoint", len(state["planned_files"]))
        return {
            "planned_files": state["planned_files"],
            "entry_point": state.get("entry_point") or state.get("file_path") or DEFAULT_ENTRY[language],
            "dependencies": state.get("dependencies") or [],
            "project_name": state.get("project_name") or "project",
            "run_mode": state.get("run_mode") or "script",
            "files": state.get("files") or {},
            "plan_context": state.get("plan_context") or "",
            "progress_notes": _note(state, f"planner: reused {len(state['planned_files'])} planned files from checkpoint"),
        }

    schema = f"""Design the project file layout. Return ONLY valid JSON:
{{
  "project_name": "<short_snake_case>",
  "entry_point": "<relative path of main file>",
  "run_mode": "script" | "server" | "library",
  "files": [{{"path": "<relative/path{ext}>", "purpose": "<one line>",
             "exports": ["<public function/class names other files import>"],
             "depends_on": ["<paths of project files this file imports>"]}}],
  "dependencies": ["<third-party pip packages only>"],
  "notes": "<constraints>"
}}
Rules:
- Relative paths only. Folders allowed (e.g. "parsers/pdf_parser.py"). Max {MAX_FILES} files.
- A small task is ONE file. Split only when it helps: keep every file under ~150 lines.
- If USER SPEC names specific files (e.g. models.py, storage.py, cli.py, ui.py, main.py, tests/test_*.py), include ALL of them.
- Imports between project modules are absolute from the project root (`from parsers.pdf_parser import parse_pdf`).
- "exports" must list exactly the names that other files will import. "depends_on" must be acyclic.
- run_mode "script" = runs and exits; "server" = web app/UI that never exits; "library" = importable modules.
- Prefer the standard library. Only use third-party packages the task really needs."""

    docs_note = (
        state.get("docs_digest")
        if state.get("docs_available")
        else "NO reference docs are available. Use only the standard library and APIs you are certain exist."
    )
    secs = [
        Sec("TASK", f"{task}\nLanguage: {language}", 100, protect=True),
        Sec("LESSONS FROM FAILED ATTEMPTS (avoid repeating)", "\n".join(f"- {l}" for l in lessons), 90, floor=200),
        Sec("USER SPEC (follow exactly)", user_plan, 80, floor=300),
        Sec("REFERENCE DOCS", docs_note, 50),
        Sec("RESEARCH NOTES", state.get("research_digest", ""), 45),
    ]
    system = "You are a Principal Software Architect. Output JSON only."
    prompt = pack_sections(secs, prompt_budget() - est_tokens(schema + system)) + "\n\n" + schema

    data: dict = {}
    try:
        data = parse_json_safely(_llm_text(system, prompt))
    except Exception as e:
        log.warning("planner failed, using fallback plan: %s", e)

    planned: List[Dict[str, Any]] = []
    seen = set()
    for item in data.get("files") or []:
        if isinstance(item, str):
            item = {"path": item}
        if not isinstance(item, dict):
            continue
        p = safe_rel_path(str(item.get("path", "")))
        if p and p not in seen:
            seen.add(p)
            planned.append(
                {
                    "path": p,
                    "purpose": str(item.get("purpose", ""))[:200],
                    "exports": _ident_list(item.get("exports")),
                    "depends_on": [
                        d for d in (safe_rel_path(str(x)) for x in (item.get("depends_on") or [])) if d
                    ],
                }
            )

    # Fixed Bug #5: Ensure explicit workstream files in `user_plan` are never dropped
    spec_files = _files_from_text(user_plan)
    for p in spec_files:
        if p not in seen and p != "requirements.txt":
            seen.add(p)
            planned.append({"path": p, "purpose": "required by user spec", "exports": [], "depends_on": []})

    if not planned:
        planned = [
            {
                "path": safe_rel_path(state.get("file_path")) or DEFAULT_ENTRY[language],
                "purpose": task[:200],
                "exports": [],
                "depends_on": [],
            }
        ]
    planned = planned[:MAX_FILES]
    paths = {p["path"] for p in planned}
    for p in planned:
        p["depends_on"] = [d for d in p["depends_on"] if d in paths and d != p["path"]]

    given = safe_rel_path(state.get("file_path"))
    if given and len(planned) == 1:
        planned[0]["path"] = given
        paths = {given}

    plist = [p["path"] for p in planned]
    entry = safe_rel_path(data.get("entry_point"))
    if entry not in plist:
        entry = (
            next((c for c in ("main" + ext, "app" + ext, "index" + ext) if c in plist), None)
            or next((p for p in plist if p.endswith(ext) and not _is_test(p)), plist[-1])
        )

    deps = [d for d in (data.get("dependencies") or []) if isinstance(d, str)] + _deps_from_text(user_plan)
    files: Dict[str, str] = dict(state.get("files") or {})
    if language == "python":
        req = _requirements(deps)
        if req:
            files["requirements.txt"] = req
            if "requirements.txt" not in plist:
                planned.insert(
                    0,
                    {"path": "requirements.txt", "purpose": "dependency list", "exports": [], "depends_on": []},
                )

    run_mode = data.get("run_mode")
    if run_mode not in ("script", "server", "library"):
        blob = (" ".join(deps) + " " + user_plan).lower()
        run_mode = "server" if re.search(r"fastapi|flask|streamlit|uvicorn|django", blob) else "script"

    if language == "python":
        _infer_dependencies(planned, entry)
    ordered = _toposort([p for p in planned if p["path"] != "requirements.txt"], entry)
    planned = [p for p in planned if p["path"] == "requirements.txt"] + ordered

    project = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(data.get("project_name") or "project")).strip("_")[:40] or "project"
    tree = "\n".join(
        f"- {p['path']}: {p['purpose']}" + (f"  [exports: {', '.join(p['exports'])}]" if p["exports"] else "")
        for p in planned
    )
    plan_context = f"Entry point: {entry}\nRun mode: {run_mode}\nFiles (write order):\n{tree}\nNotes: {data.get('notes', '')}"

    return {
        "project_name": project,
        "entry_point": entry,
        "file_path": entry,
        "run_mode": run_mode,
        "planned_files": planned,
        "dependencies": deps,
        "files": files,
        "plan_context": plan_context,
        "user_plan": user_plan,
        "iteration_count": 0,
        "error_signatures": [],
        "failed_files": [],
        "stop_reason": None,
        "autofix_rounds": 0,
        "autofix_changed": False,
        "progress_notes": _note(state, f"plan: {len(planned)} file(s), entry {entry}, mode {run_mode}"),
    }


WRITER_SYSTEM = (
    "You are a Senior Staff Software Engineer acting ONLY as the code writer. "
    "Output ONLY raw, executable code for the requested file. "
    "Do NOT output explanations, introductory text, conversational chatter, or boilerplate. "
    "Start directly with the first line of code."
)
WRITER_RULES = """CRITICAL RULES:
1. PURE CODE ONLY: Return only the complete raw file content. No conversational preface, no markdown commentary, no boilerplate explanations.
2. ZERO FRAMEWORK HALLUCINATION: Do NOT import or use unrequested frameworks such as LangGraph (e.g. AgentState, StateGraph, END), FastAPI (e.g. BackgroundTasks, APIRouter), Streamlit, or Flask unless explicitly demanded in the task.
3. STANDARD LIBRARY FOCUS: Strictly adhere to Python standard library. Any optional third-party modules MUST be lazy-imported inside functions inside try/except ImportError blocks.
4. COMPLETE WORKING CODE: No stubs, TODOs, or `pass`-only placeholders. If defining base classes/interfaces, use `@abstractmethod` or raise NotImplementedError.
5. NO CIRCULAR ASSIGNMENTS: Never assign a name to itself (`x = x`) and never use a name before it is defined or imported.
6. REFERENCE DOCS ARE INFORMATIONAL ONLY: Do NOT copy unrelated framework classes from reference docs.
7. SELFTEST & ENTRY POINT: Ensure non-interactive tests or CLI entry points run deterministically and fast (<5s).
8. BE CONCISE AND MODULAR: Keep code clean, compact, and free of redundant boilerplate or bloated multi-paragraph comments so generation completes quickly within token limits."""


def _api_summary(files: Dict[str, str], exclude: str = "", only: Optional[List[str]] = None, limit: int = 3500) -> str:
    out = []
    for path, src in files.items():
        if path == exclude or not path.endswith(".py") or path.endswith("__init__.py"):
            continue
        if only is not None and path not in only:
            continue
        tree = _py_tree(src)
        if tree is None:
            continue
        sigs = _api_lines(tree)
        if sigs:
            out.append(f"# {path}  (import as: {_mod_name(path)})\n" + "\n".join(sigs))
    return "\n\n".join(out)[:limit]


def _write_one(state: CodeDevState, path: str, files: Dict[str, str], fix: bool) -> str:
    language = state.get("language", "python")
    planned = state.get("planned_files") or []
    meta = next((p for p in planned if p["path"] == path), {})
    purpose, exports = meta.get("purpose", ""), list(meta.get("exports") or [])
    deps = list(meta.get("depends_on") or [])
    unwritten = [d for d in deps if d not in files]
    tree = "\n".join(f"- {p['path']}: {p['purpose']}" for p in planned)
    pkgs = ", ".join(state.get("dependencies") or []) or "standard library only"
    previous = files.get(path) if fix else None

    fix_block = ""
    if fix:
        err = state.get("error") or ""
        cur = focus_excerpt(files.get(path, ""), err, path, _share(0.35, 1500, 9000, "writer"))
        fix_block = f"CURRENT CONTENT OF {path} (edit it, keep everything that works):\n{cur}\n"
        if err:
            fix_block += f"\nERROR TO FIX:\n{_tail(err, 1800)}\n"
        if state.get("fix_instructions"):
            fix_block += f"\nFIX INSTRUCTIONS:\n{state['fix_instructions']}\n"
        if state.get("security_feedback"):
            fix_block += f"\nSECURITY PROBLEM TO FIX:\n{state['security_feedback']}\n"

    header = (
        f"path: {path}\npurpose: {purpose or 'see spec'}\nlanguage: {language}\n"
        f"run mode: {state.get('run_mode', 'script')}\nthird-party packages allowed: {pkgs}\n"
        f"must define (exact names): {', '.join(exports) or '(free)'}"
    )
    api_files = [p for p in files if p != path] if fix else deps
    docs = (
        state.get("docs_digest")
        if state.get("docs_available")
        else "No reference docs available: rely on the standard library and APIs you are certain about."
    )
    secs = [
        Sec("FILE TO WRITE", header, 100, protect=True),
        Sec("FIX CONTEXT", fix_block, 95, kind="code", floor=500),
        Sec(
            "INTERFACES OF PROJECT FILES YOU IMPORT (use these exact names/signatures)",
            _api_summary(files, exclude=path, only=api_files),
            90,
            kind="code",
            floor=200,
        ),
        Sec(
            "PLANNED FILES NOT WRITTEN YET (contract)",
            "\n".join(
                f"{d}: exports {', '.join(next((p.get('exports') or [] for p in planned if p['path'] == d), [])) or '?'}"
                for d in unwritten
            ),
            85,
            floor=0,
        ),
        Sec("LESSONS FROM EARLIER FAILED ATTEMPTS", "\n".join(f"- {l}" for l in (state.get("lessons") or [])), 70),
        Sec("SPEC FROM USER", state.get("user_plan") or "", 60, floor=200),
        Sec("PROJECT FILES", tree, 40),
        Sec("REFERENCE DOCS", docs, 35),
        Sec("RESEARCH NOTES", state.get("research_digest", ""), 30),
    ]
    pit = (
        _pitfalls(
            f"{purpose} {state.get('user_plan') or ''} {state.get('task', '')} {pkgs} "
            f"{_api_summary(files, exclude=path, only=api_files)}".lower()
        )
        if language == "python"
        else ""
    )
    secs.insert(3, Sec("LIBRARY PITFALLS (follow strictly)", pit, 88, floor=0))
    overhead = est_tokens(WRITER_SYSTEM + WRITER_RULES) + 120
    base = (
        f"Project task: {state.get('task', '')[:600]}\n\n"
        + pack_sections(secs, prompt_budget("writer") - overhead - est_tokens(state.get("task", "")[:600]))
        + "\n\n"
        + WRITER_RULES
    )

    problem, content = None, ""
    for attempt in range(LOCAL_SYNTAX_RETRIES + 1):
        user = (
            base
            if not problem
            else base + f"\n\nYour previous output was rejected: {problem}\nReturn the complete corrected file."
        )
        content = extract_code(_llm_text(WRITER_SYSTEM, user, role="writer"), path)
        if path.endswith(".py"):
            content, _ = repair_syntax_text(content)
        problem = _check_written(path, content, exports, previous)
        if not problem:
            return content
        log.info("writer: %s attempt %d rejected: %s", path, attempt + 1, problem)
    return content


def code_writer_node(state: CodeDevState) -> dict:
    files: Dict[str, str] = dict(state.get("files") or {})
    planned = list(state.get("planned_files") or [])
    known = {p["path"] for p in planned}
    entry = state.get("entry_point") or state.get("file_path") or DEFAULT_ENTRY[state.get("language", "python")]
    warnings = list(state.get("warnings") or [])
    notes = list(state.get("progress_notes") or [])

    fix_mode = bool(state.get("error") or state.get("security_feedback")) and bool(files)
    if fix_mode:
        # Fixed Bug #10: Also include any planned files that are still unwritten
        unwritten_planned = [p["path"] for p in planned if p["path"] not in files]
        failed_targets = [p for p in (state.get("failed_files") or []) if safe_rel_path(p)]
        targets = list(dict.fromkeys(unwritten_planned + (failed_targets or [entry])))
        for p in targets:
            if p not in known:
                planned.append({"path": p, "purpose": "added during fix", "exports": [], "depends_on": []})
                known.add(p)
    else:
        targets = [p["path"] for p in planned if p["path"] not in files]

    for path in targets:
        try:
            files[path] = _write_one({**state, "planned_files": planned}, path, files, fix_mode and path in files)
            notes = _note({"progress_notes": notes}, f"{'fixed' if (fix_mode and path in files) else 'wrote'} {path}")
            try:
                import checkpoint_manager
                checkpoint_manager.save_checkpoint(
                    task=state.get("task", ""),
                    stage=f"coder:writer:{path}",
                    coder_state={**state, "files": files, "planned_files": planned},
                    description=f"Wrote {path} ({len(files)} files)",
                )
            except Exception:
                pass
        except Exception as e:
            warnings.append(f"writer failed for {path}: {e}")
            log.warning("writer failed for %s: %s", path, e)

    return {
        "files": files,
        "planned_files": planned,
        "code": files.get(entry, ""),
        "error": None,
        "security_feedback": None,
        "failed_files": [],
        "warnings": warnings,
        "progress_notes": notes,
        "autofix_rounds": 0,
        "autofix_changed": False,
    }


def static_fix_node(state: CodeDevState) -> dict:
    files = state.get("files") or {}
    try:
        new, changes, _unresolved = autofix_files(files, state.get("language", "python"))
    except Exception as e:
        log.warning("static_fix_node failed: %s", e)
        new, changes = files, []
    entry = state.get("entry_point") or state.get("file_path") or ""
    out: dict = {"files": new, "code": new.get(entry, state.get("code", ""))}
    if changes:
        out["autofix_log"] = list(dict.fromkeys((state.get("autofix_log") or []) + changes))
        out["progress_notes"] = _note(state, f"auto-fix (no LLM): {len(changes)} change(s)")
    return out


def runtime_fix_node(state: CodeDevState) -> dict:
    rounds = state.get("autofix_rounds", 0)
    if rounds >= MAX_AUTOFIX_ROUNDS or state.get("language", "python") != "python":
        return {"autofix_changed": False}
    files = state.get("files") or {}
    try:
        new, changes, _ = autofix_files(files, "python")
        new, ch2 = fix_from_error(new, state.get("error") or "")
        changes += ch2
    except Exception as e:
        log.warning("runtime_fix_node failed: %s", e)
        new, changes = files, []
    changed = new != files
    entry = state.get("entry_point") or state.get("file_path") or ""
    out: dict = {"autofix_changed": changed, "autofix_rounds": rounds + (1 if changed else 0)}
    if changed:
        out.update(
            {
                "files": new,
                "code": new.get(entry, state.get("code", "")),
                "autofix_log": list(dict.fromkeys((state.get("autofix_log") or []) + changes)),
                "progress_notes": _note(state, f"runtime auto-fix (no LLM): {len(changes)} change(s)"),
            }
        )
    return out


_DANGEROUS = [
    (r"rm\s+-rf?\s+(/|~|\$HOME|\*)(\s|\"|'|$)", "destructive rm -rf on root/home"),
    (r"shutil\.rmtree\s*\(\s*['\"](/|~)", "rmtree on root/home"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r"\bmkfs\.\w+", "filesystem formatting"),
    (r"\bdd\s+if=.*\bof=/dev/", "raw device write"),
    (r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b", "pipe remote script to shell"),
    (r"__import__\s*\(\s*['\"]pty['\"]\s*\)\s*\.spawn", "pty spawn"),
    (r"\bos\.system\s*\(\s*['\"]\s*(sudo|chmod\s+777\s+/)", "privileged os.system"),
    (
        r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)\s*=\s*['\"](?!your|example|change|xxx|placeholder|test|dummy|mock|default|none|null)[A-Za-z0-9_\-/+=]{28,}['\"]",
        "hard-coded secret (use environment variables)",
    ),
]


def security_audit_node(state: CodeDevState) -> dict:
    files = state.get("files") or {}
    violations: List[tuple] = []
    for path, src in files.items():
        for pattern, reason in _DANGEROUS:
            if _is_test(path) and "hard-coded secret" in reason:
                continue
            if re.search(pattern, src):
                violations.append((path, reason))
    if not violations:
        return {"security_passed": True, "security_feedback": None}

    it = state.get("iteration_count", 0) + 1
    limit = state.get("max_iterations", MAX_ITERATIONS)
    out = {
        "security_passed": False,
        "security_feedback": "Security violations:\n" + "\n".join(f"- {p}: {r}" for p, r in violations),
        "failed_files": sorted({p for p, _ in violations}),
        "status": "security_violation",
        "iteration_count": it,
    }
    if it >= limit:
        out["stop_reason"] = f"Security violations remain after {it} attempts."
    return out


_SMOKE_CODE = r'''
import sys, os, json, importlib, traceback
sys.path.insert(0, os.getcwd())
failures = []
for mod in json.loads(sys.argv[1]):
    try:
        importlib.import_module(mod)
    except BaseException:
        failures.append({"module": mod, "tb": traceback.format_exc()})
print("__SMOKE__" + json.dumps(failures))
'''


def _clean_env() -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not re.search(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", k, re.I)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["CI"] = "true"
    return env


def _dec(x) -> str:
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else x


def _posix_limits(timeout: int):
    def apply():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (timeout + 5, timeout + 5))
            resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 * 1024, 200 * 1024 * 1024))
        except Exception:
            pass
    return apply


def _run(cmd: List[str], cwd, timeout: int, env: Dict[str, str], limits: bool = True):
    kw: Dict[str, Any] = {}
    if limits and os.name == "posix":
        kw["preexec_fn"] = _posix_limits(timeout)
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **kw,
        )
        return p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as e:
        return -1, _dec(e.stdout), _dec(e.stderr), True
    except FileNotFoundError as e:
        return 127, "", f"Command not found: {cmd[0]} ({e})", False


def _materialize(files: Dict[str, str], root: Path) -> None:
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    base = root.resolve()
    for rel, content in files.items():
        p = (root / rel).resolve()
        if base not in p.parents:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _failed_files_from_trace(text: str, root: Path, files: Dict[str, str]) -> List[str]:
    out: List[str] = []
    base = root.resolve()
    for m in re.finditer(r'File "([^"]+)", line \d+', text or ""):
        try:
            rel = Path(m.group(1)).resolve().relative_to(base).as_posix()
        except Exception:
            continue
        if rel in files and rel not in out:
            out.append(rel)
    return list(reversed(out))[:3]


def _missing_module(text: str) -> Optional[str]:
    m = re.search(r"No module named ['\"]([\w.\-]+)['\"]", text or "")
    return m.group(1).split(".")[0] if m else None


def _ensure_venv(workdir: Path, files: Dict[str, str], env: Dict[str, str]):
    venv = workdir / "venv"
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    req = files.get("requirements.txt", "")
    h = hashlib.sha1(req.encode()).hexdigest()
    marker = venv / ".req_hash"
    if py.exists() and marker.exists() and marker.read_text() == h:
        return str(py), None
    if not py.exists():
        rc, _, err, to = _run([sys.executable, "-m", "venv", str(venv)], workdir, 300, env, limits=False)
        if rc != 0 or to:
            return None, f"venv creation failed: {_tail(err, 500)}"
    if req.strip():
        rf = workdir / "requirements.txt"
        rf.write_text(req, encoding="utf-8")
        rc, out, err, to = _run(
            [str(py), "-m", "pip", "install", "-q", "-r", str(rf)], workdir, INSTALL_TIMEOUT, env, limits=False
        )
        if to:
            return None, f"pip install timed out after {INSTALL_TIMEOUT}s"
        if rc != 0:
            return None, f"pip install failed (check requirements.txt):\n{_tail(err or out, 1500)}"
    marker.write_text(h)
    return str(py), None


def _fail(error: str, failed: List[str], out: str = "", result: str = "Execution failed", **extra) -> dict:
    return {
        "status": "needs_debugging",
        "error": error,
        "failed_files": failed,
        "execution_output": out,
        "test_result": result,
        **extra,
    }


def real_executor_node(state: CodeDevState) -> dict:
    files = state.get("files") or {}
    language = state.get("language", "python")
    entry = state.get("entry_point") or state.get("file_path") or DEFAULT_ENTRY[language]
    run_mode = state.get("run_mode", "script")
    install = bool(state.get("install_deps"))
    planned = [p["path"] for p in state.get("planned_files") or []]

    if language == "python":
        problems = validate_project(files, planned, entry)
    else:
        problems = [
            (p, e)
            for p in dict.fromkeys(planned + list(files))
            for e in [("planned file was never written" if p not in files else validate_content(p, files[p]))]
            if e
        ]
    if entry not in files:
        problems.append((entry, "entry point missing"))
    if problems:
        return _fail(
            "Static validation failed:\n" + "\n".join(f"- {p}: {m}" for p, m in problems),
            list(dict.fromkeys(p for p, _ in problems)),
            result="Static validation failed",
        )

    workdir = Path(state.get("workdir") or tempfile.mkdtemp(prefix="agent_run_"))
    root = workdir / "project"
    _materialize(files, root)
    env = _clean_env()
    base_out = {"workdir": str(workdir)}

    if language != "python":
        exe = ["node", entry] if language == "javascript" else ["bash", entry]
        rc, out, err, to = _run(exe, root, RUN_TIMEOUT, env)
        if to:
            return _fail(f"Timed out after {RUN_TIMEOUT}s", [entry], out, "Timeout", **base_out)
        if rc != 0:
            return _fail(_tail(err) or f"exit code {rc}", [entry], out, **base_out)
        return {
            "status": "success",
            "error": None,
            "execution_output": _tail(out) or "exit code 0",
            "test_result": "Run OK",
            **base_out,
        }

    py = sys.executable
    if install:
        py, venv_err = _ensure_venv(workdir, files, env)
        if venv_err:
            return _fail(venv_err, ["requirements.txt"], result="Dependency install failed", **base_out)

    local_tops = {p.split("/")[0].removesuffix(".py") for p in files}
    missing: List[str] = []
    log_parts: List[str] = []

    def classify(text: str) -> Optional[str]:
        mod = _missing_module(text)
        return mod if mod and mod not in local_tops else None

    cli_entry, cli_runner, cli_subs = _cli_info(files, entry)
    if run_mode == "script":
        rc, out, err, to = _run([py, entry] + (["--help"] if cli_entry else []), root, RUN_TIMEOUT, env)
        log_parts.append(out)
        if to:
            return _fail(
                f"Timed out after {RUN_TIMEOUT}s. A script must terminate (servers/UIs must be started "
                f"only under `if __name__ == '__main__'` and the project run_mode should be 'server').",
                [entry],
                out,
                "Timeout",
                **base_out,
            )
        if rc != 0:
            mod = classify(err)
            if mod:
                missing.append(mod)
            else:
                return _fail(
                    _tail(err) or f"exit code {rc}",
                    _failed_files_from_trace(err, root, files) or [entry],
                    out,
                    **base_out,
                )
    else:
        mods = [_mod_name(p) for p in files if p.endswith(".py") and not _is_test(p) and _mod_name(p)]
        rc, out, err, to = _run([py, "-c", _SMOKE_CODE, json.dumps(mods)], root, SMOKE_TIMEOUT, env)
        m = re.search(r"__SMOKE__(.*)$", out or "", re.M)
        if to or not m:
            return _fail(
                ("Import smoke test timed out" if to else "Import smoke test crashed")
                + ":\n"
                + _tail(err or out, 1500),
                _failed_files_from_trace(err, root, files) or [entry],
                "",
                "Smoke test failed",
                **base_out,
            )
        failures = json.loads(m.group(1))
        real = []
        for f in failures:
            mod = classify(f["tb"])
            if mod:
                missing.append(mod)
            else:
                real.append(f)
        log_parts.append(f"Import smoke test: {len(mods) - len(failures)}/{len(mods)} modules imported OK")
        if real:
            tb = "\n\n".join(f"[{f['module']}]\n{_tail(f['tb'], 1200)}" for f in real[:2])
            ff: List[str] = []
            for f in real:
                for p in _failed_files_from_trace(f["tb"], root, files)[:1]:
                    if p not in ff:
                        ff.append(p)
            return _fail(tb, ff[:3] or [entry], "\n".join(log_parts), "Import errors", **base_out)

    if not missing:
        bad, dlogs = _deep_checks(
            py, root, files, env, entry, run_mode, cli_entry, cli_runner, cli_subs, classify, missing, base_out
        )
        log_parts += dlogs
        if bad:
            return bad
    missing = sorted(set(missing))
    if missing and install:
        return _fail(
            f"Packages still missing after install: {', '.join(missing)}. Fix requirements.txt (pip package names).",
            ["requirements.txt"],
            "\n".join(log_parts),
            "Dependency mismatch",
            **base_out,
        )
    if missing:
        return {
            "status": "deps_missing",
            "error": None,
            "missing_modules": missing,
            "execution_output": "\n".join(log_parts),
            "test_result": f"Static + partial checks passed; not fully run (missing packages: {', '.join(missing)})",
            **base_out,
        }

    tests = [p for p in files if p.endswith(".py") and _is_test(p)]
    result = "Run OK" if run_mode == "script" else "All modules import OK"
    if tests:
        rc, out, err, to = _run(
            [py, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider"] + tests,
            root,
            SMOKE_TIMEOUT,
            env,
        )
        blob = (out or "") + (err or "")
        if "No module named pytest" in blob:
            log_parts.append("pytest not installed: tests skipped")
        elif to:
            return _fail("Tests timed out", tests[:2], "\n".join(log_parts), "Tests timeout", **base_out)
        elif rc not in (0, 5):
            return _fail(
                _tail(blob),
                (_failed_files_from_trace(blob, root, files) or tests)[:3],
                "\n".join(log_parts),
                "Tests failed",
                **base_out,
            )
        else:
            log_parts.append(_tail(out, 800))
            result = "Tests passed"

    return {
        "status": "success",
        "error": None,
        "missing_modules": [],
        "execution_output": _tail("\n".join(x for x in log_parts if x) or "exit code 0"),
        "test_result": result,
        **base_out,
    }


def _error_signature(err: str) -> str:
    lines = [l.strip() for l in (err or "").splitlines() if l.strip()]
    last = lines[-1] if lines else "unknown"
    return re.sub(r"\d+", "N", last)[:200]


def _deterministic_fix_text(err: str) -> Optional[str]:
    """Self-explanatory errors -> fix instructions without asking the LLM."""
    if err.startswith("Static validation failed"):
        return (
            "Fix every item below exactly, change nothing else:\n"
            + err.split("\n", 1)[1][:1800]
            + "\nKeep all existing public functions/classes."
        )
    m = re.search(r"(Syntax|Indentation|Tab)Error: (.+)", err)
    if m and "Traceback" in err:
        return f"Fix the {m.group(1)}Error: {m.group(2)[:200]}. Keep everything else unchanged."
    m = re.search(r"NameError: name '(\w+)' is not defined", err)
    if m:
        return f"Define or import `{m.group(1)}` where it is used (import it from the project module that defines it)."
    m = re.search(r"ImportError: cannot import name '(\w+)' from '([\w.]+)'", err)
    if m:
        return (
            f"`{m.group(1)}` does not exist in `{m.group(2)}`. Either define it there or import the real name "
            f"from the correct project module (see the interfaces list)."
        )
    m = re.search(r"ModuleNotFoundError: No module named '([\w.]+)'", err)
    if m:
        return (
            f"Module `{m.group(1)}` does not exist in the project. Import from an existing project module "
            f"(absolute path from project root) or create the missing file."
        )
    return None


def _deterministic_diagnose(err: str, files: dict, targets: list) -> tuple:
    fix = _deterministic_fix_text(err) or ""
    m = re.search(r"ImportError: cannot import name '(\w+)' from '([\w.]+)'", err)
    if m:
        sym, mod = m.group(1), m.group(2)
        for fpath, code in files.items():
            if mod in fpath.replace("/", ".").replace("\\", "."):
                try:
                    import difflib
                    tree = ast.parse(code)
                    tree_exports = [
                        n.name
                        for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
                    ]
                    close = difflib.get_close_matches(sym, tree_exports, n=1)
                    if close:
                        fix += f" Did you mean `{close[0]}`? Use `{close[0]}` instead."
                except Exception:
                    pass
    line_m = re.search(r"File [^,]+, line (\d+)", err)
    line_info = f"Line {line_m.group(1)}: " if line_m else ""
    return line_info + fix, targets


def debugger_node(state: CodeDevState) -> dict:
    err = state.get("error") or "Unknown failure"
    files = state.get("files") or {}
    entry = state.get("entry_point") or state.get("file_path") or ""
    it = state.get("iteration_count", 0) + 1
    limit = state.get("max_iterations", MAX_ITERATIONS)
    failed = [p for p in (state.get("failed_files") or []) if p in files or safe_rel_path(p)] or [entry]

    sig = _error_signature(err)
    sigs = list(state.get("error_signatures") or []) + [sig]
    repeats = sigs.count(sig)
    if repeats == 1 and "Traceback" in err and state.get("test_result") != "Import errors":
        failed = failed[:1]

    stop = None
    if repeats >= MAX_SAME_ERROR:
        stop = f"Same error repeated {repeats} times - automatic fixing is not converging: {sig}"
    elif it >= limit:
        stop = f"Reached max attempts ({limit})."

    fix = ""
    if not stop:
        fix = _deterministic_fix_text(err) or ""
        used_llm = False
        if not fix:
            hist = "\n".join(f"- {h}" for h in (state.get("fix_history") or [])[-4:])
            secs = [
                Sec("ERROR", _tail(err, 2500), 100, floor=600),
                Sec(
                    "FAILING FILE(S)",
                    "\n\n".join(
                        f"## {p}\n{focus_excerpt(files[p], err, p, _share(0.3, 1200, 7000, DBG_ROLE))}"
                        for p in failed[:3]
                        if p in files
                    ),
                    80,
                    kind="code",
                    floor=400,
                ),
                Sec("ALREADY TRIED (do not repeat)", hist, 60, floor=0),
                Sec(
                    "INTERFACES OF OTHER FILES",
                    _api_summary(files, exclude=failed[0] if failed else ""),
                    40,
                    kind="code",
                ),
            ]
            instr = (
                "The project failed. Explain the bug and tell the file writer exactly what to change.\n"
                'Return ONLY JSON: {"root_cause": "<why>", "fix_instructions": "<precise instructions>"}'
            )
            system = "You are a Systems Debugger. Output JSON only."
            prompt = pack_sections(secs, prompt_budget(DBG_ROLE) - est_tokens(system + instr)) + "\n\n" + instr
            try:
                data = parse_json_safely(_llm_text(system, prompt, retries=1, role=DBG_ROLE))
                fix = f"Cause: {data.get('root_cause', '')}\nDo: {data.get('fix_instructions', '')}".strip()
                used_llm = True
            except Exception as e:
                log.warning("debugger LLM failed: %s", e)
            if not fix or fix == "Cause: \nDo:":
                fix = f"Fix exactly this error: {sig}"
        if repeats > 1:
            fix += f"\nThis same error already occurred {repeats - 1} time(s) after earlier fixes. Use a DIFFERENT approach."
        log.info("debugger: %s fix instructions", "LLM" if used_llm else "deterministic")

    hist_list = list(state.get("fix_history") or [])
    if fix:
        hist_list.append(f"attempt {it}: {sig[:80]} -> {fix.splitlines()[0][:100] if fix else ''}")
    return {
        "error": err,
        "failed_files": failed,
        "fix_instructions": fix,
        "iteration_count": it,
        "error_signatures": sigs,
        "stop_reason": stop,
        "fix_history": hist_list[-6:],
        "progress_notes": _note(state, f"debug #{it}: {sig[:80]}"),
    }


def replan_node(state: CodeDevState) -> dict:
    n = state.get("replan_count", 0) + 1
    last_err = state.get("error") or ""
    why = state.get("stop_reason") or _error_signature(last_err)
    lesson = (
        f"Plan #{n} failed: {why[:200]} | last error: {_tail(last_err, 280).strip()[:280]} | "
        f"tried: {(state.get('fix_instructions') or '')[:160]}"
    )
    lessons = (state.get("lessons") or []) + [lesson]
    return {
        "lessons": lessons[-3:],
        "replan_count": n,
        "prev_files": state.get("files") or state.get("prev_files") or {},
        "files": state.get("files") or state.get("prev_files") or {},
        "planned_files": state.get("planned_files") or [],
        "failed_files": [],
        "error": None,
        "last_replan_error": last_err,  # Fixed Bug #1: Preserved for analyzer_node
        "fix_instructions": "",
        "security_feedback": None,
        "security_passed": True,
        "iteration_count": state.get("iteration_count", 0),  # Preserve cumulative count to prevent infinite loop
        "error_signatures": list(state.get("error_signatures") or []),
        "stop_reason": None,
        "autofix_rounds": 0,
        "autofix_changed": False,
        "fix_history": [],
        "status": "needs_debugging",
        "code": "",
        "execution_output": "",
        "test_result": "",
        "progress_notes": [f"replan #{n}: context cleared, restarting from analysis"],
        "warnings": list(state.get("warnings") or []) + [f"replanned {n}x: {why[:120]}"],
    }


def _resolve_output_dir(project: str, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir)
    try:
        from tools._common import safe_output_path
        return Path(str(safe_output_path("code", project)))
    except Exception:
        return Path("generated_code") / project


def _run_hints(state: CodeDevState) -> List[str]:
    files = state.get("files") or {}
    entry = state.get("entry_point", "")
    hints = []
    if "requirements.txt" in files:
        hints.append("pip install -r requirements.txt")
    for p, src in files.items():
        if not p.endswith(".py"):
            continue
        if re.search(r"\bFastAPI\s*\(", src):
            hints.append(f"uvicorn {_mod_name(p)}:app --reload")
        elif re.search(r"^\s*(import|from)\s+streamlit", src, re.M):
            hints.append(f"streamlit run {p}")
    if state.get("language") == "python" and state.get("run_mode") == "script" and entry:
        hints.append(f"python {entry}")
    return hints


def reviewer_node(state: CodeDevState) -> dict:
    files = state.get("files") or state.get("prev_files") or {}
    status = state.get("status", "needs_debugging")
    final_status = {"success": "success", "deps_missing": "partial"}.get(status, "failed")

    out_dir = _resolve_output_dir(state.get("project_name", "project"), state.get("output_dir"))
    saved: List[str] = []
    if files:
        out_dir.mkdir(parents=True, exist_ok=True)
        base = out_dir.resolve()
        for rel, content in files.items():
            dest = (out_dir / rel).resolve()
            if base not in dest.parents:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            saved.append(rel)

    icon = {"success": "OK", "partial": "PARTIAL", "failed": "FAILED"}[final_status]
    docs = (
        "used"
        if state.get("docs_available")
        else ("wanted but unavailable" if state.get("needs_docs") else "not needed")
    )
    lines = [
        f"## Overview & Files Saved [{icon}]",
        f"- Task: {state.get('task', '')[:300]}",
        f"- Location: `{out_dir}`",
        f"- Entry point: `{state.get('entry_point', '')}` (run mode: {state.get('run_mode', 'script')})",
        f"- LLM fix attempts: {state.get('iteration_count', 0)}/{state.get('max_iterations', MAX_ITERATIONS)}"
        f" | replans: {state.get('replan_count', 0)} | reference docs: {docs}",
        "",
        "## Files",
    ]
    lines += [f"- `{p}` ({len(files[p].splitlines())} lines)" for p in sorted(saved)] or ["- (no files produced)"]
    lines += ["", "## Execution & Test Results", f"- Result: {state.get('test_result') or 'not executed'}"]
    if state.get("execution_output"):
        lines += ["```", _tail(state["execution_output"], 1500), "```"]
    if final_status == "partial":
        lines.append(
            f"- Not fully run because these packages are not installed: "
            f"{', '.join(state.get('missing_modules') or [])}. Install them (or call with install_deps=True) and re-run."
        )
    if final_status == "failed":
        lines.append(f"- Stopped: {state.get('stop_reason') or 'unresolved error'}")
        if state.get("error"):
            lines += ["- Last error:", "```", _tail(state["error"], 1500), "```"]
        lines.append("- Files above are the best attempt, NOT verified.")
    if state.get("autofix_log"):
        lines += ["", "## Auto-fixes applied without LLM"] + [f"- {a}" for a in (state["autofix_log"])[:15]]
    hints = _run_hints({**state, "files": files})
    if hints:
        lines += ["", "## How to run"] + [f"- `{h}`" for h in dict.fromkeys(hints)]
    if state.get("warnings"):
        lines += ["", "## Warnings"] + [f"- {w}" for w in state["warnings"]]

    workdir = state.get("workdir")
    if workdir:
        shutil.rmtree(workdir, ignore_errors=True)
    return {
        "status": final_status,
        "output_dir": str(out_dir),
        "final_output": "\n".join(lines),
        "review_feedback": f"{final_status}: {len(saved)} file(s) written to {out_dir}",
        "workdir": "",
        "files": files,
    }


def _stop_target(state: CodeDevState) -> str:
    # Always route to reviewer when stopped to preserve best-attempt files and prevent endless replan loops
    return "reviewer"


def route_after_security(state: CodeDevState) -> str:
    if state.get("security_passed", True):
        return "executor"
    return _stop_target(state) if state.get("stop_reason") else "writer"


def route_after_execution(state: CodeDevState) -> str:
    return "runtime_fix" if state.get("status") == "needs_debugging" else "reviewer"


def route_after_runtime_fix(state: CodeDevState) -> str:
    return "security_check" if state.get("autofix_changed") else "debugger"


def route_after_debugger(state: CodeDevState) -> str:
    return _stop_target(state) if state.get("stop_reason") else "writer"


workflow = StateGraph(CodeDevState)
workflow.add_node("analyzer", analyzer_node)
workflow.add_node("planner", planner_node)
workflow.add_node("writer", code_writer_node)
workflow.add_node("static_fix", static_fix_node)
workflow.add_node("security_check", security_audit_node)
workflow.add_node("executor", real_executor_node)
workflow.add_node("runtime_fix", runtime_fix_node)
workflow.add_node("debugger", debugger_node)
workflow.add_node("replan", replan_node)
workflow.add_node("reviewer", reviewer_node)

workflow.add_edge(START, "analyzer")
workflow.add_edge("analyzer", "planner")
workflow.add_edge("planner", "writer")
workflow.add_edge("writer", "static_fix")
workflow.add_edge("static_fix", "security_check")
workflow.add_conditional_edges(
    "security_check",
    route_after_security,
    {"executor": "executor", "writer": "writer", "replan": "replan", "reviewer": "reviewer"},
)
workflow.add_conditional_edges(
    "executor",
    route_after_execution,
    {"runtime_fix": "runtime_fix", "reviewer": "reviewer"},
)
workflow.add_conditional_edges(
    "runtime_fix",
    route_after_runtime_fix,
    {"security_check": "security_check", "debugger": "debugger"},
)
workflow.add_conditional_edges(
    "debugger",
    route_after_debugger,
    {"writer": "writer", "replan": "replan", "reviewer": "reviewer"},
)
workflow.add_edge("replan", "analyzer")
workflow.add_edge("reviewer", END)
code_dev_agent = workflow.compile()

GRAPH_CONFIG = {"recursion_limit": 250}


def _initial_state(
    task: str,
    language: str = "python",
    file_path: Optional[str] = None,
    plan: Optional[str] = None,
    output_dir: Optional[str] = None,
    install_deps: bool = False,
    max_iterations: int = MAX_ITERATIONS,
    research_report: Optional[str] = None,
    docs_context: Optional[str] = None,
    max_replans: Optional[int] = None,
    existing_files: Optional[Dict[str, str]] = None,
    resume_state: Optional[Dict[str, Any]] = None,
) -> CodeDevState:
    rs = resume_state or {}
    files = dict(existing_files or rs.get("files") or {})
    planned_files = list(rs.get("planned_files") or [])
    prev_files = dict(rs.get("prev_files") or {})
    it = rs.get("iteration_count", 0)
    replans = rs.get("replan_count", 0)
    notes = list(rs.get("progress_notes") or [])
    if files:
        notes.append(f"resumed: {len(files)} file(s) loaded from saved checkpoint")

    return {
        "task": task,
        "language": language,
        "user_plan": plan or rs.get("user_plan") or "",
        "plan_context": rs.get("plan_context", ""),
        "research_report": research_report or rs.get("research_report", ""),
        "docs_context": docs_context or rs.get("docs_context", ""),
        "files": files,
        "file_path": safe_rel_path(file_path) or rs.get("file_path", "") or rs.get("entry_point", ""),
        "output_dir": output_dir or rs.get("output_dir", ""),
        "install_deps": install_deps or bool(rs.get("install_deps")),
        "security_passed": rs.get("security_passed", True),
        "security_feedback": rs.get("security_feedback"),
        "execution_output": rs.get("execution_output", ""),
        "test_result": rs.get("test_result", ""),
        "error": rs.get("error"),
        "last_replan_error": rs.get("last_replan_error"),
        "status": rs.get("status", "needs_debugging"),
        "iteration_count": it,
        "max_iterations": max_iterations,
        "replan_count": replans,
        "max_replans": MAX_REPLANS if max_replans is None else max_replans,
        "autofix_rounds": rs.get("autofix_rounds", 0),
        "autofix_changed": rs.get("autofix_changed", False),
        "autofix_log": list(rs.get("autofix_log") or []),
        "error_signatures": list(rs.get("error_signatures") or []),
        "fix_history": list(rs.get("fix_history") or []),
        "lessons": list(rs.get("lessons") or []),
        "progress_notes": notes,
        "failed_files": list(rs.get("failed_files") or []),
        "warnings": list(rs.get("warnings") or []),
        "stop_reason": rs.get("stop_reason"),
        "final_output": rs.get("final_output", ""),
        "prev_files": prev_files,
        "planned_files": planned_files,
    }


def run_code_dev_task(
    task: str,
    language: str = "python",
    file_path: Optional[str] = None,
    plan: Optional[str] = None,
    output_dir: Optional[str] = None,
    install_deps: bool = False,
    max_iterations: int = MAX_ITERATIONS,
    research_report: Optional[str] = None,
    docs: Optional[str] = None,
    retriever: Optional[Callable[[str], Any]] = None,
    llm: Any = None,
    summarizer_llm: Any = None,
    writer_llm: Any = None,
    writer_ctx: Optional[int] = None,
    max_replans: Optional[int] = None,
    research_context: Optional[str] = None,
    rag_docs: Optional[str] = None,
    step_callback: Optional[Callable[[str, dict], None]] = None,
    use_llm_debugger: Optional[bool] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run an end-to-end (multi-file) coding task."""
    agent = "Code & Dev Engineer"
    research_report = research_report or research_context
    docs = docs or rag_docs
    for _k in _ctx_scales:
        _ctx_scales[_k] = 1.0
    if llm is not None or summarizer_llm is not None or writer_llm is not None:
        set_llm(
            llm if llm is not None else _ensure_llm(),
            summarizer_llm if summarizer_llm is not None else llm_summarizer,
            writer_llm if writer_llm is not None else _UNSET,
            writer_ctx,
        )
    if _ensure_llm() is None:
        return {
            "status": "error",
            "agent": agent,
            "error": "llm_unavailable",
            "reply": "No LLM backend is available. Start the local model server and retry.",
        }
    if retriever is not None:
        set_doc_retriever(retriever)
    log.info(
        "LLM roles: planner/debugger=main, writer=%s, ctx main=%d writer=%d",
        "separate model" if _eff_role("writer") == "writer" else "same as main",
        ctx_tokens("main"),
        ctx_tokens("writer"),
    )
    try:
        init_st = _initial_state(
            task,
            language,
            file_path,
            plan,
            output_dir,
            install_deps,
            max_iterations,
            research_report,
            docs,
            max_replans,
            existing_files=kwargs.get("existing_files"),
            resume_state=kwargs.get("resume_state"),
        )
        final_state: Dict[str, Any] = dict(init_st)
        for step in code_dev_agent.stream(init_st, config=GRAPH_CONFIG, stream_mode="updates"):
            for node, update in step.items():
                final_state.update(update or {})
                if step_callback:
                    try:
                        step_callback(node, final_state)
                    except Exception:
                        pass
                try:
                    import checkpoint_manager
                    checkpoint_manager.save_checkpoint(
                        task=task,
                        stage=f"coder:{node}",
                        coder_state=final_state,
                        description=f"Coder node '{node}' ({len(final_state.get('files') or {})} file(s))",
                    )
                except Exception:
                    pass
        final = final_state
    except Exception as e:
        log.exception("code dev agent crashed")
        return {"status": "error", "agent": agent, "error": str(e), "reply": f"Code Dev agent crashed: {e}"}

    return {
        "status": final.get("status", "failed"),
        "agent": agent,
        "reply": final.get("final_output", ""),
        "files": final.get("files", {}),
        "code": final.get("code", ""),
        "file_path": final.get("entry_point", ""),
        "output_dir": final.get("output_dir", ""),
        "execution_output": final.get("execution_output", ""),
        "error": final.get("error"),
        "stop_reason": final.get("stop_reason"),
        "docs_used": bool(final.get("docs_available")),
        "doc_status": "used" if bool(final.get("docs_available")) else "fallback_no_rag",
        "replans": final.get("replan_count", 0),
        "autofix_log": final.get("autofix_log", []),
        "warnings": final.get("warnings", []),
    }


def pipeline_coder_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for the big pipeline."""
    res = run_code_dev_task(
        task=state.get("task") or state.get("user_query", ""),
        plan=state.get("coder_plan") or state.get("user_plan"),
        research_report=state.get("research_report") or state.get("research_notes"),
        docs=state.get("rag_context"),
        output_dir=state.get("output_dir"),
    )
    return {
        "code_status": res.get("status"),
        "code_files": res.get("files", {}),
        "code_reply": res.get("reply", ""),
        "code_dir": res.get("output_dir", ""),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    state = _initial_state(
        "create a CLI todo app with add/list/done commands saved in a json file and add streamlit glassmorphism ui on it with a nice design",
        language="python",
        plan="- Create a command-line interface (CLI) todo application with the following commands:\n  - `add`: Add a new todo item.\n  - `list`: List all todo items.\n  - `done`: Mark a todo item as completed.\n- Store the todo items in a JSON file for persistence.\n- Implement a Streamlit web interface with a glassmorphism design to interact with the todo app visually.",
    )
    final_state: Dict[str, Any] = dict(state)
    print("\nRunning Code Dev Agent v2.3...\n")
    for step in code_dev_agent.stream(state, config=GRAPH_CONFIG, stream_mode="updates"):
        for node, update in step.items():
            final_state.update(update or {})
            print(f"[{node.upper()}] done", end="")
            if update and update.get("status"):
                print(f" | status={update['status']}", end="")
            if update and update.get("error"):
                print(f" | error={str(update['error'])[:120]!r}", end="")
            print()
    print("\n" + "=" * 60)
    print(final_state.get("final_output", ""))
    print("=" * 60)