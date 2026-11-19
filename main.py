"""Entry point. Pehle mode puchta hai:
    1) chat   - normal chatbot + web search
    2) rag    - sirf docs se jawab (sources ke saath)
    3) code   - poora coder pipeline

    python main.py
    python main.py --mode code --request "fastapi todo api banao"
    python main.py --autostart     # servers khud start kar de
    python main.py --selftest      # fake model se pipeline check (real model nahi chahiye)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

# Transparently bootstrap into .venv if executed directly from global Python lacking dependencies
_ROOT = Path(__file__).resolve().parent
_VENV_PY = _ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if __name__ == "__main__" and _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    try:
        import langgraph  # noqa: F401
    except ImportError:
        cmd = [str(_VENV_PY), str(Path(__file__).resolve())] + sys.argv[1:]
        sys.exit(subprocess.call(cmd))

import config as C
import llm
import rag
import tools
from llm import chat, extract_json, fit

SYS_CHAT = ("You are a helpful assistant. Answer clearly and briefly. Reply in the same language as the user "
            "(Hinglish is fine). Use web results only if provided; mention the source URL when you use them.")
SYS_RAG = ("Answer ONLY from the documentation excerpts. Give a short answer with a small code example when "
           "useful. If the docs do not contain the answer, say so. Reply in the same language as the user.")
SYS_SEARCH = ("Decide if a web search is needed (recent info, versions, prices, news, facts you may not know). "
              "Output JSON {\"search\": \"<query>\"} or {\"search\": null}.")
SCHEMA_SEARCH = {"type": "object", "properties": {"search": {"type": ["string", "null"]}}, "required": ["search"]}


def _p(t):
    print(t, end="", flush=True)


def ensure_servers(roles: list[str] | None = None, progress_cb=None) -> bool:
    """Ensure required llama-servers are running, auto-starting if necessary."""
    import start_servers
    return start_servers.ensure_servers(roles=roles, progress_cb=progress_cb)


def chat_turn(query: str, history: list[tuple[str, str]] | None = None,
              force_web: bool = False, on_token=None, progress_cb=None) -> dict:
    """Execute a single chat turn with optional web search and streaming LLM generation."""
    ensure_servers(["main"], progress_cb=progress_cb)
    history = history or []
    query_to_search = None
    if force_web:
        query_to_search = query
    else:
        try:
            out = extract_json(chat("main", SYS_SEARCH, query, task="search_decision", max_tokens=60,
                                    schema=SCHEMA_SEARCH), {}) or {}
            s = out.get("search")
            if isinstance(s, str) and s.strip():
                query_to_search = s.strip()
        except Exception:
            query_to_search = None

    web_content = ""
    web_err = None
    if query_to_search:
        if progress_cb:
            progress_cb(f"Web search: {query_to_search}...")
        res, web_err = tools.web_search(query_to_search, 4)
        web_content = tools.format_results(res, 3500) if res else ""

    hist_text = "\n".join(f"{r}: {t}" for r, t in history[-6:])
    prompt = (f"Conversation so far:\n{fit(hist_text, 2500)}\n\n" if hist_text else "") + \
             (f"Web results:\n{web_content}\n\n" if web_content else "") + f"User: {query}"

    ans = chat("main", SYS_CHAT, prompt, task="chat", temperature=0.5,
               stream=bool(on_token), on_token=on_token)
    return {
        "answer": ans,
        "search_query": query_to_search,
        "web_results": web_content,
        "web_error": web_err
    }


def rag_turn(query: str, library: str | None = None, k: int = 4,
             on_token=None, progress_cb=None) -> dict:
    """Execute RAG retrieval + LLM synthesis turn."""
    ensure_servers(["main"], progress_cb=progress_cb)
    libs = rag.libraries()
    clean_q = query.strip()
    if not library and clean_q.startswith("@"):
        first, _, rest = clean_q.partition(" ")
        tag = first[1:].lower()
        if tag in libs:
            library, clean_q = tag, rest.strip()

    hits = rag.search(clean_q, k=k, library=library)
    if not hits:
        return {
            "answer": f"Docs me is sawal se relevant kuch nahi mila. Aap `@<library>` tag use kar sakte hain: {', '.join(libs)}",
            "hits": [],
            "docs_context": "",
            "library_used": library
        }

    docs = "\n\n".join(f"[{i}] ({h['library']} {h['version']} p{h['page']})\n{h['text']}"
                       for i, h in enumerate(hits, 1))
    docs_prompt = f"Docs:\n{docs}\n\nQuestion: {clean_q}"
    ans = chat("main", SYS_RAG, docs_prompt, task="rag_answer", temperature=0.2,
               stream=bool(on_token), on_token=on_token)
    return {
        "answer": ans,
        "hits": hits,
        "docs_context": docs,
        "library_used": library
    }


def code_turn(request: str, resume_checkpoint: dict | None = None,
              force_resume: bool = False, force_fresh: bool = False, progress_cb=None) -> dict:
    """Execute the autonomous multi-agent code development pipeline."""
    ensure_servers(["main", "writer"], progress_cb=progress_cb)
    from pipeline import run_pipeline
    import checkpoint_manager

    cp = resume_checkpoint
    if cp is None and (force_resume or not force_fresh):
        active = checkpoint_manager.get_active_checkpoint()
        if active:
            cp = checkpoint_manager.prompt_resume_if_available(force_resume=force_resume, force_fresh=force_fresh)

    final = run_pipeline(request or (cp.get("task") if cp else ""), resume_checkpoint=cp)
    ans = (final.get("answer") if isinstance(final, dict) else str(final)) or "[done] Pipeline finished."
    return {"result": final, "summary": ans, "resumed": bool(cp)}


def research_turn(topic: str, progress_cb=None) -> dict:
    """Execute deep web research agent turn."""
    ensure_servers(["main"], progress_cb=progress_cb)
    from research.research_web import research_web_agent
    if progress_cb:
        progress_cb(f"Conducting deep web research on: {topic}...")
    result = research_web_agent.invoke(
        {
            "query": topic,
            "attached_files": [],
            "search_depth": "advanced",
            "output_type": "deep_dive",
            "export_format": "markdown",
            "generated_search_queries": None,
            "messages": [],
            "delivery_messages": [],
            "research_notes": None,
            "draft_report": None,
            "audit_feedback": None,
            "audit_passed": False,
            "iteration_count": 0,
            "delivery_iterations": 0,
            "audit_retries": 0,
            "saved_path": None,
            "final": None,
        },
        config={"recursion_limit": 60},
    )
    report = result.get("final") or result.get("draft_report") or "No research report produced."
    saved = result.get("saved_path")
    return {"report": report, "saved_path": saved, "raw_result": result}


def chat_mode():
    print("\n[chat] normal chatbot. `/web <sawal>` = zabardasti search, `/menu` = wapas, `/exit`.")
    history: list[tuple[str, str]] = []
    while True:
        q = input("\nTum> ").strip()
        if not q:
            continue
        if q in ("/menu", "/exit"):
            return q == "/exit"
        forced = q.startswith("/web ")
        if forced:
            q = q[5:].strip()
        print("AI> ", end="")
        res = chat_turn(q, history=history, force_web=forced, on_token=_p)
        print()
        if res.get("search_query"):
            print(f"(web search: {res['search_query']})")
        history += [("User", q), ("AI", res["answer"])]


def rag_mode():
    libs = rag.libraries()
    if not libs:
        print("Docs index khaali hai. docs/<library>/ me PDFs rakho aur `python ingest_docs.py` chalao.")
        return False
    print(f"\n[rag] libraries: {', '.join(libs)}\n`@fastapi sawal...` = sirf us library me dhoondho. `/menu`, `/exit`.")
    while True:
        q = input("\nSawal> ").strip()
        if not q:
            continue
        if q in ("/menu", "/exit"):
            return q == "/exit"
        print("AI> ", end="")
        res = rag_turn(q, on_token=_p)
        print("\n\nSources:")
        for i, h in enumerate(res.get("hits", []), 1):
            src = h['source'].replace('\\', '/').split('/')[-1]
            print(f"  [{i}] {h['library']} {h['version']} - {src} p{h['page']} ({h['heading'] or 'intro'})")


def research_mode(request: str | None = None):
    one_shot = request is not None
    print("\n[research] deep web research agent. Topic batao. `/menu` = wapas, `/exit`.")
    while True:
        q = request or input("\nResearch topic> ").strip()
        request = None
        if not q:
            continue
        if q in ("/menu", "/exit"):
            return q == "/exit"
        print("\n[researcher] investigating and analyzing sources...")
        res = research_turn(q)
        print("\n" + "=" * 60 + "\n" + res["report"])
        if res.get("saved_path"):
            print(f"\n[saved] Saved report to: {res['saved_path']}")
        if one_shot:
            return True


def code_mode(request: str | None = None, force_resume: bool = False, force_fresh: bool = False):
    one_shot = request is not None
    print("\n[code] coder pipeline (Researcher + RAG + Coder). Kya banana hai batao. `/menu` = wapas, `/exit`.")
    while True:
        q = request or input("\nKya banana hai> ").strip()
        request = None
        if not q:
            continue
        if q in ("/menu", "/exit"):
            return q == "/exit"
        res = code_turn(q, force_resume=force_resume, force_fresh=force_fresh)
        print("\n" + "=" * 60 + "\n" + res["summary"])
        if one_shot:
            return True


def menu(args):
    # Check for resumable session on launch if in code mode or default
    if not args.mode and not args.request:
        import checkpoint_manager
        if checkpoint_manager.get_active_checkpoint():
            cp = checkpoint_manager.prompt_resume_if_available(
                force_resume=getattr(args, "resume", False),
                force_fresh=getattr(args, "fresh", False),
            )
            if cp:
                from pipeline import run_pipeline
                print(f"[code] Resuming previous task: {cp.get('task')}")
                final = run_pipeline(cp.get("task", ""), resume_checkpoint=cp)
                ans = (final.get("answer") if isinstance(final, dict) else str(final)) or "[done] Pipeline finished."
                print("\n" + "=" * 60 + "\n" + ans)
                return

    while True:
        mode = args.mode
        if not mode:
            print("\nKya karna hai?\n  1) Normal chat (+web search)\n  2) Docs se jawab (RAG)\n  3) Code banao (full pipeline: Researcher + RAG + Coder)\n  4) Deep Web Research\n  q) Exit")
            c = input("> ").strip().lower()
            mode = {"1": "chat", "2": "rag", "3": "code", "4": "research"}.get(c)
            if c in ("q", "quit", "exit"):
                return
            if not mode:
                continue
        done = {"chat": chat_mode, "rag": rag_mode,
                "code": lambda: code_mode(args.request, force_resume=getattr(args, "resume", False), force_fresh=getattr(args, "fresh", False)),
                "research": lambda: research_mode(args.request)}[mode]()
        if args.mode or done:
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["chat", "rag", "code", "research"])
    ap.add_argument("--request", help="code/research mode: ek baar ka kaam")
    ap.add_argument("--resume", action="store_true", help="interrupted session ko bina poochhe resume karo")
    ap.add_argument("--fresh", action="store_true", help="previous checkpoint discard karke naya run karo")
    ap.add_argument("--autostart", action="store_true", help="llama servers khud start karo")
    ap.add_argument("--selftest", action="store_true", help="run mock pipeline selftests")
    ap.add_argument("--health", action="store_true", help="run system & server health check")
    args = ap.parse_args()

    if args.health:
        import healthcheck
        return 0 if healthcheck.run_healthcheck() else 1

    if args.selftest:
        import selftest
        return selftest.run()

    if not llm.mock_enabled():
        need = {"chat": ["main"], "rag": ["main"], "code": ["main", "writer"], "research": ["main"], None: ["main", "writer"]}[args.mode]
        down = [r for r in need if not llm.server_up(r)]
        if down:
            print(f"[AutoStart] Servers offline: {down}. Launching local llama-servers automatically...")
            ensure_servers(down)
            down = [r for r in need if not llm.server_up(r)]
            if "writer" in down and llm.server_up("main"):
                print("[INFO] Server 2 (writer: 8084) is offline. Using Server 1 (main) for both orchestrator and coder writer.")
                down.remove("writer")
            if down:
                print(f"[WARN] Some servers could not be started: {down}. Please check logs/ or run `python start_servers.py`.")
                return 1
    try:
        menu(args)
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
    except llm.LLMError as e:
        print(f"\nLLM error: {e}")
        return 1
    except Exception as e: 
        print(f"\n[ERROR] System error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
