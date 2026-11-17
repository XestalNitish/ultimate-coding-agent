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

# Transparently bootstrap into .venv if executed from global Python lacking dependencies
_ROOT = Path(__file__).resolve().parent
_VENV_PY = _ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
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
        query = q if forced else None
        if not forced:
            out = extract_json(chat("main", SYS_SEARCH, q, task="search_decision", max_tokens=60,
                                    schema=SCHEMA_SEARCH), {}) or {}
            s = out.get("search")
            query = s if isinstance(s, str) and s.strip() else None
        web = ""
        if query:
            print(f"(web search: {query})")
            res, err = tools.web_search(query, 4)
            web = tools.format_results(res, 3500) if res else ""
            if err:
                print(f"({err})")
        hist = "\n".join(f"{r}: {t}" for r, t in history[-6:])
        prompt = (f"Conversation so far:\n{fit(hist, 2500)}\n\n" if hist else "") + \
                 (f"Web results:\n{web}\n\n" if web else "") + f"User: {q}"
        print("AI> ", end="")
        ans = chat("main", SYS_CHAT, prompt, task="chat", temperature=0.5, stream=True, on_token=_p)
        print()
        history += [("User", q), ("AI", ans)]


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
        lib = None
        if q.startswith("@"):
            first, _, rest = q.partition(" ")
            if first[1:].lower() in libs:
                lib, q = first[1:].lower(), rest.strip()
        hits = rag.search(q, k=4, library=lib)
        if not hits:
            print("Kuch relevant nahi mila.")
            continue
        docs = "\n\n".join(f"[{i}] ({h['library']} {h['version']} p{h['page']})\n{h['text']}"
                           for i, h in enumerate(hits, 1))
        print("AI> ", end="")
        chat("main", SYS_RAG, f"Docs:\n{docs}\n\nQuestion: {q}", task="rag_answer", temperature=0.2,
             stream=True, on_token=_p)
        print("\n\nSources:")
        for i, h in enumerate(hits, 1):
            print(f"  [{i}] {h['library']} {h['version']} - {h['source'].split('/')[-1].split(chr(92))[-1]} p{h['page']} "
                  f"({h['heading'] or 'intro'})")


def research_mode(request: str | None = None):
    from research.research_web import research_web_agent
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
        result = research_web_agent.invoke(
            {
                "query": q,
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
        report = result.get("final") or result.get("draft_report") or "No report produced."
        saved = result.get("saved_path")
        print("\n" + "=" * 60 + "\n" + report)
        if saved:
            print(f"\n[saved] Saved report to: {saved}")
        if one_shot:
            return True


def code_mode(request: str | None = None, force_resume: bool = False, force_fresh: bool = False):
    from pipeline import run_pipeline
    import checkpoint_manager

    one_shot = request is not None
    # Check for active checkpoint before asking
    cp = checkpoint_manager.prompt_resume_if_available(force_resume=force_resume, force_fresh=force_fresh)
    if cp:
        print(f"[code] Resuming previous task: {cp.get('task')}")
        final = run_pipeline(cp.get("task", ""), resume_checkpoint=cp)
        ans = (final.get("answer") if isinstance(final, dict) else str(final)) or "[done] Pipeline finished."
        print("\n" + "=" * 60 + "\n" + ans)
        if one_shot:
            return True

    print("\n[code] coder pipeline (Researcher + RAG + Coder). Kya banana hai batao. `/menu` = wapas, `/exit`.")
    while True:
        q = request or input("\nKya banana hai> ").strip()
        request = None
        if not q:
            continue
        if q in ("/menu", "/exit"):
            return q == "/exit"
        final = run_pipeline(q)
        ans = (final.get("answer") if isinstance(final, dict) else str(final)) or "[done] Pipeline finished."
        print("\n" + "=" * 60 + "\n" + ans)
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

    if args.autostart and not llm.mock_enabled():
        import start_servers
        roles = {"chat": ["main"], "rag": ["main"], "code": list(C.MODELS), "research": ["main"], None: list(C.MODELS)}[args.mode]
        start_servers.launch(roles)

    if not llm.mock_enabled():
        need = {"chat": ["main"], "rag": ["main"], "code": ["main", "writer"], "research": ["main"], None: ["main"]}[args.mode]
        down = [r for r in need if not llm.server_up(r)]   # baaki roles ka error chat() khud batayega
        if "writer" in down and llm.server_up("main"):
            print("[INFO] Server 2 (writer: 8084) is offline. Using Server 1 (main) for both orchestrator and coder writer.")
            down.remove("writer")
        if down:
            print(f"Servers down: {down}. Alag terminal me `python start_servers.py` chalao "
                  f"(ya `python main.py --autostart`).")
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
