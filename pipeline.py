"""
pipeline.py - Unified Researcher -> RAG -> Coder pipeline (drop-in replacement for the old pipeline)

    intake -> researcher -> mediator -> (rag -> summarizer) -> planner -> (rag -> summarizer -> planner)
           -> coder -> [failed? restart(failure summary) -> planner ...] -> finalize

Agents used (all imported lazily, every stage is FAIL-SOFT: if one agent is missing/crashes,
the pipeline warns and continues with what it has - the data flow never breaks):
    research_web_agent  (research/research_web.py)   -> research report
    rag_agent           (rag/retriever.py)           -> documentation context
    run_code_dev_task   (coder/code_dev_agent.py)    -> multi-file project (has its own debug/replan loop)

Helper roles added by this pipeline (use the same local LLM as the coder agent):
    gate (research needed?) | mediator (docs needed?) | doc summarizer | planner (spec + acceptance)
    | failure summarizer (for restart)

Old API is kept:  build_graph(), run_pipeline(user_input) -> dict with
    answer, ok, out_path   (+ new: status, files, out_dir, research_path, warnings, notes)

CLI:  python pipeline.py "your task" [--research auto|on|off] [--lang python] [--install]

Env knobs (all optional; config.py values are used when present):
    PIPELINE_RESEARCH=auto|on|off   PIPELINE_WORKSPACE=general   PIPELINE_MAX_RESTARTS=1
    PIPELINE_CODER_REPLANS=1        PIPELINE_RESEARCH_DEPTH=basic|medium|advanced
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(HERE.parent) not in sys.path:
    sys.path.append(str(HERE.parent))

try:
    import config as C 
except Exception:  
    C = None

log = logging.getLogger("pipeline")


def _cfg(name: str, default: Any) -> Any:
    v = getattr(C, name, None) if C is not None else None
    return default if v is None else v


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


ROOT = Path(_cfg("ROOT", HERE))
OUT_ROOT = ROOT / "output"
LOG_DIR = Path(_cfg("LOG_DIR", ROOT / "logs"))
USE_RESEARCHER = bool(_cfg("USE_RESEARCHER", True))
RESEARCH_MODE = os.getenv("PIPELINE_RESEARCH", "auto" if USE_RESEARCHER else "off").lower()
RESEARCH_DEPTH = os.getenv("PIPELINE_RESEARCH_DEPTH", "advanced" if _cfg("USE_DEEP_RESEARCH", False) else "advanced")
DEFAULT_WS = os.getenv("PIPELINE_WORKSPACE", "general")
RAG_TOP_K = int(_cfg("RAG_TOP_K", 4))
MAX_PLANNER_RAG = int(_cfg("MAX_PLANNER_RAG_CALLS", 1))
MAX_RESTARTS = _env_int("PIPELINE_MAX_RESTARTS", int(_cfg("MAX_PLANNER_RESTARTS", 0)))
CODER_MAX_ITER = int(_cfg("MAX_RETRIES", 3))
CODER_MAX_REPLANS = _env_int("PIPELINE_CODER_REPLANS", 0)
RESEARCH_MAX_CHARS = 12000
DIGEST_CHARS = 4500
DOC_CHARS = 3500

CODER_MODULES = ("coder.code_dev", "coder.code_dev_agent", "coder", "code_dev_agent", "code_dev")
RESEARCH_MODULES = ("research.research_web", "reaserch.research_web", "research", "research_web")
RAG_MODULES = ("rag.retriever", "retriever")

_FOUND: Dict[str, Any] = {}
_FAILED_MODS: Dict[str, str] = {}
_MODS: Dict[str, Any] = {}


def _find(attr: str, modules) -> Any:
    """First module in `modules` that exposes `attr`. Failed imports are remembered (never retried)."""
    if attr in _FOUND:
        return _FOUND[attr]
    for m in modules:
        if m in _FAILED_MODS:
            continue
        mod = _MODS.get(m)
        if mod is None:
            try:
                mod = importlib.import_module(m)
                _MODS[m] = mod
            except Exception as e:  
                _FAILED_MODS[m] = f"{type(e).__name__}: {str(e)[:120]}"
                continue
        if hasattr(mod, attr):
            _FOUND[attr] = getattr(mod, attr)
            return _FOUND[attr]
    return None


def _import_hint(modules) -> str:
    errs = [f"{m} ({_FAILED_MODS[m]})" for m in modules if m in _FAILED_MODS]
    return "; ".join(errs[:3]) or "module not found"

def ui(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode(), flush=True)


try:
    from langchain_core.callbacks import BaseCallbackHandler as _CBBase
except Exception:  
    _CBBase = object


class Progress(_CBBase): 
    """Live progress for the sub-agents: prints every graph node that starts and every LLM call
    (start + how long it took), so a slow local model never looks like a frozen pipeline."""

    def __init__(self, label: str = "agent"):
        self.label, self.t0, self.calls, self._starts = label, time.time(), 0, {}

    def _p(self, msg: str) -> None:
        ui(f"    [{self.label} +{time.time() - self.t0:5.0f}s] {msg}")

    def on_chain_start(self, serialized, inputs, **kw):  # noqa: ANN001
        node = (kw.get("metadata") or {}).get("langgraph_node")
        if node and kw.get("name") == node:
            self._p(f"node: {node}")

    def on_chat_model_start(self, serialized, messages, **kw):  # noqa: ANN001
        self.calls += 1
        self._starts[kw.get("run_id")] = time.time()
        self._p(f"LLM call #{self.calls} started (waiting for model...)")

    def on_llm_start(self, serialized, prompts, **kw):  # noqa: ANN001
        if kw.get("run_id") not in self._starts:
            self.on_chat_model_start(serialized, prompts, **kw)

    def on_llm_end(self, response, **kw):  # noqa: ANN001
        t = self._starts.pop(kw.get("run_id"), None)
        self._p(f"LLM call done in {time.time() - t:.0f}s" if t else "LLM call done")

    def on_llm_error(self, error, **kw):  # noqa: ANN001
        self._starts.pop(kw.get("run_id"), None)
        self._p(f"LLM call ERROR: {type(error).__name__}: {str(error)[:120]}")


def cut(text: str, n: int) -> str:
    text = text or ""
    if len(text) <= n:
        return text
    if n < 80:
        return text[:n]
    head = (n - 20) * 2 // 3
    return text[:head] + "\n...[trimmed]...\n" + text[-(n - 20 - head):]


def parse_json(raw: str) -> dict:
    clean = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if m:
        clean = m.group(1).strip()
    cands = [clean]
    s, e = clean.find("{"), clean.rfind("}")
    if s != -1 and e > s:
        cands.append(clean[s:e + 1])
    for c in cands:
        try:
            d = json.loads(c)
            if isinstance(d, dict):
                return d
        except Exception:  # noqa: BLE001
            continue
    return {}


def to_bool(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return bool(v)


def llm_text(system: str, user: str, retries: int = 1) -> str:
    fn = _find("_llm_text", CODER_MODULES)
    if fn is None:
        raise RuntimeError("helper LLM unavailable (coder module not importable)")
    return fn(system, user, retries=retries, summarizer=True)


def compress(text: str, n: int, purpose: str = "") -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    fn = _find("summarize_text", CODER_MODULES)
    if fn is not None:
        try:
            return fn(text, n, purpose=purpose)
        except Exception:  # noqa: BLE001
            pass
    return cut(text, n)


def _add(s: dict, key: str, item: str, cap: int = 40) -> List[str]:
    return (list(s.get(key) or []) + [item[:300]])[-cap:]


def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (t or "").lower())[:30].strip("_") or "task"


_RANK = {"success": 3, "partial": 2, "failed": 1, "error": 0}


class S(TypedDict, total=False):
    user_input: str
    language: str
    research_mode: str
    workspace: str
    install_deps: bool
    out_dir: str
    started: float
    # research
    research: str
    research_digest: str
    research_path: str
    # rag
    rag_available: bool
    needs_rag: bool
    questions: list
    retrieved: list
    doc_context: str
    plan_rag_calls: int
    # plan
    plan: dict
    spec: str
    # coder / loop
    attempts: int
    restarts: int
    failure_summary: str
    code_result: dict
    best: dict
    # output
    status: str
    ok: bool
    files: dict
    out_path: str
    answer: str
    warnings: list
    notes: list

SYS_GATE = ("You decide if web research is needed before writing code. Research IS needed when the task depends on "
            "external/current/unfamiliar information (third-party APIs or services, library versions, SDK usage, data "
            "sources). It is NOT needed for self-contained logic, CRUD/CLI/UI apps or standard-library tasks. "
            'Return ONLY JSON: {"needs_research": true|false, "reason": "<short>"}')
SYS_MED = ("You are a retrieval planner. Decide if official library documentation is needed to write the requested code "
           "correctly. Simple / standard-library tasks do NOT need docs. If needed, give at most 4 short, specific "
           "documentation questions and, when possible, the best library from the given list for each. "
           'Return ONLY JSON: {"needs_rag": true|false, "questions": [{"q": "...", "library": "<name or null>"}]}')
SYS_DOC = ("Extract from the documentation only what is needed to write code for the question: exact function / class "
           "names, signatures, parameters, version notes and at most one short code example (max 6 lines). "
           "Max 120 words. No fluff. If the docs do not answer it, say 'not found'.")
SYS_PLAN = ("You are a senior software planner. Turn the task into a precise spec for a coder. Return ONLY JSON.")
SYS_FAIL = ("Summarize in max 80 words why the previous coding attempt failed: what was tried, the last error, and what "
            "to avoid or do differently next time. Plain text.")

_RESEARCH_HINT = re.compile(
    r"\b(latest|current|official|docs?|documentation|api|sdk|version|deprecated|migrate|integrat\w*|scrap\w*|webhook|"
    r"oauth|payment|gemini|openai|anthropic|groq|langgraph|langchain|fastapi|streamlit|docker|kubernetes|react|next\.?js)\b",
    re.I)
_DOC_HINT = re.compile(
    r"\b(fastapi|flask|django|streamlit|langgraph|langchain|pandas|numpy|torch|tensorflow|sqlalchemy|pydantic|"
    r"chromadb|faiss|transformers|selenium|playwright|gradio|opencv|reportlab|pymupdf)\b", re.I)

def intake(s: S) -> dict:
    task = (s.get("user_input") or "").strip()
    if not task:
        raise ValueError("user_input is empty")
    lang = s.get("language") if s.get("language") in ("python", "javascript", "bash") else "python"
    mode = (s.get("research_mode") or RESEARCH_MODE or "auto").lower()
    mode = mode if mode in ("auto", "on", "off") else "auto"
    base = s.get("out_dir") or str(OUT_ROOT / f"{_slug(task)}_{time.strftime('%Y%m%d_%H%M%S')}")
    if s.get("resumed"):
        ui(f"[intake] Resuming saved task: '{task[:60]}' (out={base})")
        return {
            "user_input": task, "language": lang, "research_mode": mode,
            "workspace": s.get("workspace") or DEFAULT_WS, "out_dir": base,
            "install_deps": bool(s.get("install_deps")), "started": s.get("started", time.time()),
            "doc_context": (s.get("doc_context") or "").strip(),
            "research": s.get("research", ""), "research_digest": s.get("research_digest", ""),
            "research_path": s.get("research_path", ""),
            "attempts": s.get("attempts", 0), "restarts": s.get("restarts", 0),
            "plan_rag_calls": s.get("plan_rag_calls", 0), "failure_summary": s.get("failure_summary", ""),
            "best": s.get("best", {}), "warnings": list(s.get("warnings") or []),
            "notes": list(s.get("notes") or []) + ["Resumed from saved checkpoint"],
            "questions": list(s.get("questions") or []), "retrieved": list(s.get("retrieved") or []),
            "plan": s.get("plan", {}), "spec": s.get("spec", ""),
            "files": s.get("files", {}),
        }
    ui(f"[intake] language={lang} research={mode} out={base}")
    return {
        "user_input": task, "language": lang, "research_mode": mode,
        "workspace": s.get("workspace") or DEFAULT_WS, "out_dir": base,
        "install_deps": bool(s.get("install_deps")), "started": time.time(),
        "doc_context": (s.get("doc_context") or "").strip(),
        "research": "", "research_digest": "", "research_path": "",
        "attempts": 0, "restarts": 0, "plan_rag_calls": 0, "failure_summary": "",
        "best": {}, "warnings": [], "notes": [], "questions": [], "retrieved": [],
    }


def _decide_research(task: str) -> tuple:
    try:
        d = parse_json(llm_text(SYS_GATE, f"Task:\n{cut(task, 1500)}", retries=1))
        if "needs_research" in d:
            return to_bool(d["needs_research"]), str(d.get("reason", "llm"))[:100]
    except Exception as e:  # noqa: BLE001
        log.info("research gate LLM failed (%s) - heuristic", e)
    return bool(_RESEARCH_HINT.search(task)), "heuristic"


def _extract_report(result: dict) -> tuple:
    """(report_text, saved_path) from the research agent's final state - tries every place the report can live."""
    saved = result.get("saved_path") or ""
    text = ""
    if saved and Path(saved).is_file():
        try:
            disk = Path(saved).read_text(encoding="utf-8").strip()
            if len(disk) > 150 and "Data Unavailable" not in disk:
                text = disk
        except Exception:  # noqa: BLE001
            pass
    if not text:
        draft = str(result.get("draft_report") or "").strip()
        if len(draft) > 150:
            text = draft
    if not text and result.get("final"):
        fin = str(result["final"]).strip()
        if "Deliverable Persistence" in fin:
            fin = fin.split("Deliverable Persistence")[0].rsplit("###", 1)[0]
        if len(fin) > 100 and not fin.startswith("• Markdown saved"):
            text = fin.strip(" -\n")
    if not text and result.get("research_notes"):
        notes = str(result["research_notes"]).strip()
        if len(notes) > 80:
            text = notes
    return text, saved


def researcher(s: S) -> dict:
    if s.get("research") or s.get("research_digest"):
        ui("[researcher] Resuming: Reusing saved research context from checkpoint.")
        return {"notes": _add(s, "notes", "research: reused from checkpoint")}
    task, mode = s["user_input"], s.get("research_mode", "auto")
    if mode == "off":
        return {"notes": _add(s, "notes", "research: off")}
    if mode == "auto":
        need, why = _decide_research(task)
        if not need:
            ui(f"[researcher] skipped ({why})")
            return {"notes": _add(s, "notes", f"research: not needed ({why})")}
    agent = _find("research_web_agent", RESEARCH_MODULES)
    if agent is None:
        w = f"research agent not importable ({_import_hint(RESEARCH_MODULES)}) - continuing without research"
        ui(f"[researcher] {w}")
        return {"warnings": _add(s, "warnings", w)}
    ui(f"[researcher] running research agent (depth={RESEARCH_DEPTH})...")
    query = (f"{cut(task, 400)}\n\n[Research focus: implementation details for developers - official docs, exact API "
             f"names/signatures, library versions, known pitfalls and best practices.]")
    try:
        result = agent.invoke({
            "query": query, "attached_files": [], "search_depth": RESEARCH_DEPTH, "output_type": "deep_dive",
            "export_format": "markdown", "generated_search_queries": None, "messages": [], "delivery_messages": [],
            "research_notes": None, "draft_report": None, "audit_feedback": None, "audit_passed": False,
            "iteration_count": 0, "delivery_iterations": 0, "audit_retries": 0, "saved_path": None, "final": None,
        }, config={"recursion_limit": 60, "callbacks": [Progress("research")]})
        report, saved = _extract_report(result or {})
        if not report:
            raise RuntimeError("research agent finished without a report")
        report = report[:RESEARCH_MAX_CHARS]
        digest = compress(report, DIGEST_CHARS, purpose=task)
        ui(f"  report {len(report)} chars -> digest {len(digest)} chars" + (f" | saved: {saved}" if saved else ""))
        return {"research": report, "research_digest": digest, "research_path": saved,
                "notes": _add(s, "notes", f"research: {len(report)} chars")}
    except Exception as e:  # noqa: BLE001
        w = f"research failed ({type(e).__name__}: {str(e)[:120]}) - continuing without research"
        ui(f"[researcher] {w}")
        return {"warnings": _add(s, "warnings", w)}


def _libraries() -> List[str]:
    fn = _find("libraries", ("rag",))
    try:
        return [str(x) for x in (fn() or [])] if fn else []
    except Exception:  # noqa: BLE001
        return []


def _norm_questions(items: Any, libs: List[str], limit: int) -> List[dict]:
    libmap = {l.lower(): l for l in libs}
    out: List[dict] = []
    for it in items or []:
        if isinstance(it, str):
            it = {"q": it}
        if not isinstance(it, dict) or not str(it.get("q", "")).strip():
            continue
        lib = it.get("library")
        lib = libmap.get(lib.lower()) if isinstance(lib, str) else None
        out.append({"q": str(it["q"]).strip()[:300], "library": lib})
    return out[:limit]


def mediator(s: S) -> dict:
    if s.get("doc_context") and (s.get("resumed") or s.get("spec")):
        ui("[mediator] Resuming: Reusing saved documentation context from checkpoint.")
        return {"rag_available": True, "needs_rag": False, "questions": []}
    task = s["user_input"]
    if _find("rag_agent", RAG_MODULES) is None:
        w = f"RAG agent not importable ({_import_hint(RAG_MODULES)}) - continuing without docs"
        ui(f"[mediator] {w}")
        return {"rag_available": False, "needs_rag": False, "questions": [], "warnings": _add(s, "warnings", w)}
    libs = _libraries()
    ui("[mediator] docs needed?")
    prompt = (f"Task: {cut(task, 1200)}\n\nResearch notes: {cut(s.get('research_digest') or 'none', 1000)}\n\n"
              f"Available doc libraries: {', '.join(libs) or '(none listed - a general workspace is searched)'}")
    data: dict = {}
    try:
        data = parse_json(llm_text(SYS_MED, prompt))
    except Exception as e:  # noqa: BLE001
        log.info("mediator LLM failed (%s) - heuristic", e)
    qs = _norm_questions(data.get("questions"), libs, 4)
    needs = to_bool(data["needs_rag"]) if "needs_rag" in data else bool(_DOC_HINT.search(task))
    if needs and not qs:
        qs = [{"q": task[:300], "library": None}]
    ui(f"  needs_rag={needs}, questions={len(qs)}")
    return {"rag_available": True, "needs_rag": needs, "questions": qs if needs else []}


def rag_node(s: S) -> dict:
    agent = _find("rag_agent", RAG_MODULES)
    qs = s.get("questions") or []
    warnings = list(s.get("warnings") or [])
    retrieved, seen = [], set()
    if agent is None:
        return {"retrieved": [], "questions": []}
    ui(f"[rag] {len(qs)} question(s)...")
    for q in qs:
        ws = q.get("library") or s.get("workspace") or DEFAULT_WS
        hits: List[dict] = []
        try:
            for d in agent.search(q["q"], ws, top_n=RAG_TOP_K):
                meta = getattr(d, "metadata", None) or {}
                txt = getattr(d, "page_content", str(d))
                key = (meta.get("source", ""), meta.get("page", 1), txt[:60])
                if key not in seen:
                    seen.add(key)
                    hits.append({"library": meta.get("library") or ws, "page": meta.get("page", 1),
                                 "source": meta.get("source", ""), "text": txt})
        except Exception as e:  # noqa: BLE001
            warnings.append(f"RAG search failed for '{q['q'][:50]}' ({type(e).__name__}: {str(e)[:100]})")
        retrieved.append({"q": q["q"], "hits": hits})
    return {"retrieved": retrieved, "questions": [], "warnings": warnings[-40:]}


def summarizer(s: S) -> dict:
    parts = []
    for item in s.get("retrieved") or []:
        if not item.get("hits"):
            continue
        docs = "\n\n".join(f"[{h['library']} p{h['page']}]\n{h['text']}" for h in item["hits"])
        ui(f"[summarizer] {item['q'][:60]}")
        try:
            summ = llm_text(SYS_DOC, f"Question: {item['q']}\n\nDocs:\n{cut(docs, 6000)}").strip()
        except Exception:  # noqa: BLE001
            summ = cut(docs, 700)
        if summ and "not found" not in summ.lower()[:20]:
            parts.append(f"Q: {item['q']}\n{summ}")
    doc_ctx = s.get("doc_context", "")
    if parts:
        doc_ctx = (doc_ctx + "\n\n" + "\n\n".join(parts)).strip()
    doc_ctx = compress(doc_ctx, DOC_CHARS, purpose=s["user_input"])
    return {"doc_context": doc_ctx, "retrieved": [], "questions": [],
            "notes": _add(s, "notes", f"docs: {len(doc_ctx)} chars")}


def _spec_text(p: dict) -> str:
    def block(title: str, items: Any) -> str:
        items = [str(x) for x in (items or []) if str(x).strip()]
        return f"{title}:\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1)) if items else ""

    parts = [f"GOAL: {p.get('summary', '')}" if p.get("summary") else "",
             block("REQUIREMENTS", p.get("requirements")),
             block("ACCEPTANCE CHECKS", p.get("acceptance")),
             block("CONSTRAINTS", p.get("constraints"))]
    return "\n\n".join(x for x in parts if x)


def planner(s: S) -> dict:
    if s.get("resumed") and s.get("spec") and s.get("plan"):
        ui("[planner] Resuming: Reusing saved plan & spec from checkpoint.")
        return {"plan": s["plan"], "spec": s["spec"], "questions": [], "notes": _add(s, "notes", "plan: reused from checkpoint")}
    ui("[planner] making spec...")
    calls = s.get("plan_rag_calls", 0)
    can_ask = bool(s.get("rag_available")) and calls < MAX_PLANNER_RAG
    libs = _libraries() if can_ask else []
    prompt = (f"TASK:\n{cut(s['user_input'], 3000)}\n\nRESEARCH NOTES:\n{cut(s.get('research_digest') or 'none', 2500)}\n\n"
              f"DOC NOTES:\n{cut(s.get('doc_context') or 'none', 2500)}")
    if s.get("failure_summary"):
        prompt += f"\n\nPREVIOUS ATTEMPTS FAILED - plan so this is avoided:\n{s['failure_summary']}"
    prompt += ('\n\nReturn ONLY JSON: {"summary": "<one line>", "requirements": ["<=10 concrete, checkable items"], '
               '"acceptance": ["<=6 checks"], "constraints": ["<=5: libraries/versions/forbidden things"], '
               '"needs_docs": false, "doc_questions": [{"q": "...", "library": null}]}\n'
               "Rules: keep the user's names, filenames, endpoints and schema EXACTLY; do not invent requirements; "
               + ("set needs_docs=true only if essential API details are clearly missing from the notes."
                  if can_ask else "needs_docs must be false."))
    data: dict = {}
    try:
        data = parse_json(llm_text(SYS_PLAN, prompt))
    except Exception as e:  # noqa: BLE001
        log.warning("planner failed: %s", e)
    plan = {k: data.get(k) for k in ("summary", "requirements", "acceptance", "constraints")} if data else {}
    spec = _spec_text(plan) if plan else ""
    qs = _norm_questions(data.get("doc_questions"), libs, 3) if (can_ask and to_bool(data.get("needs_docs"))) else []
    out: dict = {"plan": plan, "spec": spec, "notes": _add(s, "notes", f"plan: {'ok' if spec else 'empty (task used as-is)'}")}
    if qs:
        ui(f"  planner needs docs ({len(qs)} question(s))")
        out.update({"questions": qs, "plan_rag_calls": calls + 1})
    else:
        out["questions"] = []
    return out


def _make_retriever(s: S) -> Optional[Callable[[str], Any]]:
    agent = _find("rag_agent", RAG_MODULES)
    if agent is None:
        return None
    ws = s.get("workspace") or DEFAULT_WS
    return lambda q: agent.get_context(q, ws)


def coder_node(s: S) -> dict:
    attempt = s.get("attempts", 0)
    out_dir = s["out_dir"] + ("" if attempt == 0 else f"_retry{attempt}")
    run = _find("run_code_dev_task", CODER_MODULES)
    warnings = list(s.get("warnings") or [])
    ui(f"[coder] attempt {attempt + 1} -> {out_dir}")
    if run is None:
        res: dict = {"status": "error", "error": f"coder agent not importable ({_import_hint(CODER_MODULES)})"}
    else:
        task = s["user_input"]
        if s.get("failure_summary"):
            task += "\n\nPREVIOUS ATTEMPTS FAILED - avoid this:\n" + s["failure_summary"]
        retr = _make_retriever(s)
        setter = _find("set_doc_retriever", CODER_MODULES)
        if setter is not None:
            setter(retr)  
        kw: Dict[str, Any] = dict(
            task=task, language=s.get("language", "python"), plan=s.get("spec") or None, output_dir=out_dir,
            install_deps=bool(s.get("install_deps")), max_iterations=CODER_MAX_ITER,
            research_report=s.get("research_digest") or s.get("research") or None,
            docs=s.get("doc_context") or None, max_replans=CODER_MAX_REPLANS,
            existing_files=s.get("files") or None,
            resume_state=s.get("code_result") or None)
        if retr is not None:
            kw["retriever"] = retr
        gcfg = _find("GRAPH_CONFIG", CODER_MODULES)  
        if isinstance(gcfg, dict):
            gcfg["callbacks"] = [Progress("coder")]
        try:
            res = run(**kw) or {}
        except Exception as e:  # noqa: BLE001
            log.exception("coder crashed")
            res = {"status": "error", "error": f"{type(e).__name__}: {e}"}
    status = res.get("status") if res.get("status") in _RANK else "error"
    files = res.get("files") or {}
    ui(f"  coder status={status}, files={len(files)}, replans={res.get('replans', 0)}")
    for w in res.get("warnings") or []:
        warnings.append(f"coder: {w}")
    cur = {"status": status, "files": files, "output_dir": res.get("output_dir") or out_dir,
           "file_path": res.get("file_path", ""), "reply": res.get("reply", ""), "error": res.get("error"),
           "stop_reason": res.get("stop_reason"), "execution_output": res.get("execution_output", ""),
           "docs_used": bool(res.get("docs_used"))}
    best = s.get("best") or {}
    if not best or _RANK[status] >= _RANK.get(best.get("status", "error"), 0) and (files or not best.get("files")):
        best = cur
    return {"code_result": cur, "best": best, "attempts": attempt + 1, "status": status,
            "warnings": warnings[-40:], "notes": _add(s, "notes", f"coder attempt {attempt + 1}: {status}")}


def route_after_coder(s: S) -> str:
    if s.get("status") in ("success", "partial"):
        return "finalize"
    if s.get("restarts", 0) >= 1:
        return "finalize"
    return "restart" if s.get("restarts", 0) < MAX_RESTARTS else "finalize"


def restart(s: S) -> dict:
    n = s.get("restarts", 0) + 1
    res = s.get("code_result") or {}
    ui(f"[restart] coder failed -> failure summary, back to planner ({n}/{MAX_RESTARTS})")
    raw = (f"Task: {cut(s['user_input'], 800)}\nStatus: {res.get('status')}\nStop reason: {res.get('stop_reason')}\n"
           f"Last error:\n{cut(str(res.get('error') or ''), 1200)}\nOutput:\n{cut(res.get('execution_output') or '', 500)}")
    try:
        summ = llm_text(SYS_FAIL, raw).strip()
    except Exception:  # noqa: BLE001
        summ = f"{res.get('status')}: {res.get('stop_reason') or ''} | {cut(str(res.get('error') or ''), 300)}"
    prev = s.get("failure_summary", "")
    return {"failure_summary": cut((prev + "\n" + summ).strip(), 1200), "restarts": n, "plan": {}, "spec": "",
            "questions": [], "plan_rag_calls": 0, "status": "",
            "notes": _add(s, "notes", f"restart {n}: {summ[:120]}")}


def finalize(s: S) -> dict:
    best = s.get("best") or {}
    status = best.get("status") or "error"
    files = best.get("files") or {}
    out_dir = Path(best.get("output_dir") or s.get("out_dir") or OUT_ROOT / "unknown")
    warnings = list(s.get("warnings") or [])

    if files: 
        try:
            base = out_dir.resolve()
            for rel, content in files.items():
                dest = (out_dir / rel).resolve()
                if base in dest.parents and not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(content, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"could not save files: {e}")
    try:  
        nd = out_dir / "_pipeline_notes"
        for fname, txt in (("research.md", s.get("research")), ("docs_notes.md", s.get("doc_context")),
                           ("spec.md", s.get("spec"))):
            if txt and txt.strip():
                nd.mkdir(parents=True, exist_ok=True)
                (nd / fname).write_text(txt, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    entry = best.get("file_path") or ""
    out_path = str(out_dir / entry) if entry and (out_dir / entry).exists() else str(out_dir)
    icon = {"success": "OK", "partial": "PARTIAL", "failed": "FAILED", "error": "ERROR"}[status]
    docs = "used" if (s.get("doc_context") or best.get("docs_used")) else ("not found" if s.get("needs_rag") else "not needed")
    research = (f"used ({len(s.get('research') or '')} chars" + (f", saved: {s['research_path']}" if s.get("research_path") else "") + ")"
                ) if s.get("research") else "skipped / unavailable"
    lines = [f"## Pipeline result [{icon}]",
             f"- Task: {s.get('user_input', '')[:300]}",
             f"- Location: `{out_dir}`",
             f"- Entry: `{entry or '-'}` | attempts: {s.get('attempts', 0)} | restarts: {s.get('restarts', 0)}",
             f"- Research: {research} | Docs (RAG): {docs}",
             f"- Time: {time.time() - s.get('started', time.time()):.0f}s", "", "## Files"]
    lines += [f"- `{p}` ({len(c.splitlines())} lines)" for p, c in sorted(files.items())] or ["- (no files produced)"]
    if best.get("reply"):
        lines += ["", "## Coder report", best["reply"]]
    elif best.get("error"):
        lines += ["", "## Error", "```", cut(str(best["error"]), 1500), "```"]
    if status in ("failed", "error"):
        lines += ["", "Code poora verify nahi hua - files best-effort hain, run karne se pehle check kar lena."]
    if warnings:
        lines += ["", "## Pipeline warnings"] + [f"- {w}" for w in warnings[-15:]]
    return {"status": status, "ok": status == "success", "files": files, "out_path": out_path,
            "out_dir": str(out_dir), "answer": "\n".join(lines), "warnings": warnings}

def build_graph():
    g = StateGraph(S)
    for name, fn in [("intake", intake), ("researcher", researcher), ("mediator", mediator), ("rag", rag_node),
                     ("summarizer", summarizer), ("planner", planner), ("coder", coder_node),
                     ("restart", restart), ("finalize", finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "researcher")
    g.add_edge("researcher", "mediator")
    g.add_conditional_edges("mediator", lambda s: "rag" if s.get("needs_rag") and s.get("questions") else "summarizer",
                            {"rag": "rag", "summarizer": "summarizer"})
    g.add_edge("rag", "summarizer")
    g.add_edge("summarizer", "planner")
    g.add_conditional_edges("planner", lambda s: "rag" if s.get("questions") else "coder",
                            {"rag": "rag", "coder": "coder"})
    g.add_conditional_edges("coder", route_after_coder, {"restart": "restart", "finalize": "finalize"})
    g.add_edge("restart", "planner")
    g.add_edge("finalize", END)
    return g.compile()


def run_pipeline(user_input: str, language: str = "python", research: Optional[str] = None,
                 workspace: Optional[str] = None, install_deps: bool = False,
                 output_dir: Optional[str] = None, docs: Optional[str] = None,
                 resume_checkpoint: Optional[Dict[str, Any]] = None) -> S:
    """research: 'auto' | 'on' | 'off' (None = env/config). docs: already-retrieved docs text (optional)."""
    resumed_pipe = (resume_checkpoint.get("pipeline_state") or {}) if resume_checkpoint else {}
    resumed_coder = (resume_checkpoint.get("coder_state") or {}) if resume_checkpoint else {}

    init: S = {
        "user_input": user_input or (resume_checkpoint.get("task", "") if resume_checkpoint else ""),
        "language": language or resumed_pipe.get("language", "python"),
        "research_mode": research or resumed_pipe.get("research_mode", ""),
        "workspace": workspace or resumed_pipe.get("workspace", ""),
        "install_deps": install_deps or bool(resumed_pipe.get("install_deps")),
        "out_dir": output_dir or resumed_pipe.get("out_dir", ""),
        "doc_context": docs or resumed_pipe.get("doc_context", ""),
        "research": resumed_pipe.get("research", ""),
        "research_digest": resumed_pipe.get("research_digest", ""),
        "research_path": resumed_pipe.get("research_path", ""),
        "plan": resumed_pipe.get("plan", {}),
        "spec": resumed_pipe.get("spec", ""),
        "files": resumed_coder.get("files") or resumed_pipe.get("files", {}),
        "attempts": resumed_pipe.get("attempts", 0),
        "restarts": resumed_pipe.get("restarts", 0),
        "resumed": bool(resume_checkpoint),
        "code_result": resumed_coder,
    }
    final: Dict[str, Any] = dict(init)
    t0 = time.time()
    session_id = resume_checkpoint.get("session_id") if resume_checkpoint else None
    try:
        app = build_graph()
        for step in app.stream(init, config={"recursion_limit": 120}, stream_mode="updates"):
            for _node, upd in step.items():
                final.update(upd or {})
                try:
                    import checkpoint_manager
                    session_id = checkpoint_manager.save_checkpoint(
                        task=final.get("user_input") or user_input,
                        stage=_node,
                        pipeline_state=final,
                        coder_state=final.get("code_result") or {},
                        description=f"Completed pipeline node '{_node}'",
                        session_id=session_id,
                    )
                except Exception as ce:
                    log.debug("Checkpoint save failed: %s", ce)
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline crashed")
        best = final.get("best") or {}
        final.update({"status": "error", "ok": False, "files": best.get("files", {}),
                      "answer": f"Pipeline crashed: {type(e).__name__}: {e}\n"
                                f"Last notes: {'; '.join(final.get('notes') or [])[-400:]}"})
    try:
        if final.get("status") in ("success", "partial"):
            import checkpoint_manager
            checkpoint_manager.mark_completed(session_id=session_id, final_output=final.get("answer"))
    except Exception:
        pass
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        slim = {k: v for k, v in final.items() if k not in ("answer", "best", "code_result", "files", "research")}
        slim["files"] = sorted((final.get("files") or {}).keys())
        (LOG_DIR / f"run_{int(t0)}.json").write_text(json.dumps(slim, indent=1, ensure_ascii=False, default=str),
                                                      encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ui(f"\n[done] {time.time() - t0:.0f}s | status={final.get('status')}")
    return final  # type: ignore[return-value]


if __name__ == "__main__":
    import argparse
    import checkpoint_manager

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Researcher + RAG + Coder pipeline")
    ap.add_argument("task", nargs="*", help="what to build")
    ap.add_argument("--research", choices=["auto", "on", "off"], default=None)
    ap.add_argument("--lang", default="python", choices=["python", "javascript", "bash"])
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--install", action="store_true", help="install requirements in a venv before running")
    ap.add_argument("--resume", action="store_true", help="resume from last saved checkpoint")
    ap.add_argument("--fresh", action="store_true", help="start fresh and discard any saved checkpoint")
    a = ap.parse_args()

    cp = None
    if a.resume or (not a.task and not a.fresh):
        cp = checkpoint_manager.prompt_resume_if_available(force_resume=a.resume, force_fresh=a.fresh)

    if cp:
        task_text = cp.get("task", "")
        res = run_pipeline(task_text, language=a.lang, research=a.research, workspace=a.workspace, install_deps=a.install, resume_checkpoint=cp)
    else:
        task_text = " ".join(a.task).strip() or input("Task: ").strip()
        res = run_pipeline(task_text, language=a.lang, research=a.research, workspace=a.workspace, install_deps=a.install)
    print("\n" + "=" * 60 + "\n" + res.get("answer", "") + "\n" + "=" * 60)