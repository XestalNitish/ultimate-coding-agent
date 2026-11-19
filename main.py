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
import re
import tools
from llm import chat, extract_json, fit

SYS_CHAT = ("You are X-ESTAL, an advanced autonomous AI software engineering assistant created and engineered by X-ESTAL NITISH (Nitish Kumar).\n\n"
            "CRITICAL IDENTITY & LANGUAGE RULES:\n"
            "1. YOUR NAME IS STRICTLY X-ESTAL. If anyone asks 'who are you', 'kya naam hai', 'what is your name', or about your identity, you MUST explicitly state that your name is X-ESTAL, an autonomous AI software engineer and intelligence agent engineered by X-ESTAL NITISH (Nitish Kumar).\n"
            "2. LANGUAGE: You MUST communicate in clear, fluent English or natural, modern Hinglish (conversational Hindi written in English/Latin letters). NEVER respond in pure Devanagari Hindi or overly formal Hindi unless the user explicitly asks for Devanagari Hindi. Match the user's style: if they ask in English, answer in English; if they ask in Hinglish, answer in Hinglish.\n"
            "3. CONVERSATION MEMORY: Carefully remember all prior context, code, and user statements in this dialogue. When asked about something mentioned earlier (e.g. user's name, previous questions), recall and use it accurately.\n"
            "4. TECHNICAL CAPABILITIES: Provide modular, clean, working code examples and precise technical explanations. If research results or web data are provided below, synthesize them cleanly and cite source URLs.")

SYS_RAG = ("Answer ONLY from the documentation excerpts. Give a short answer with a small code example when "
           "useful. If the docs do not contain the answer, say so. Reply in fluent English or modern Hinglish.")

SYS_SEARCH = ("Decide if external web intelligence or research tools are needed (recent info, versions, prices, news, GitHub repos, URLs, live facts you may not know).\n"
              "Output JSON: {\"tool\": \"web\"|\"news\"|\"github\"|\"read\"|null, \"query\": \"<short query or url>\"}.\n"
              "Use null for general chat, identity questions ('what is your name', 'who created you'), or standard coding.")

SCHEMA_SEARCH = {
    "type": "object",
    "properties": {
        "tool": {"type": ["string", "null"], "enum": ["web", "news", "github", "read", None]},
        "query": {"type": ["string", "null"]}
    },
    "required": ["tool", "query"]
}


def _p(t):
    print(t, end="", flush=True)


def ensure_servers(roles: list[str] | None = None, progress_cb=None) -> bool:
    """Ensure required llama-servers are running, auto-starting if necessary."""
    import start_servers
    return start_servers.ensure_servers(roles=roles, progress_cb=progress_cb)


def chat_turn(query: str, history: list[tuple[str, str]] | None = None,
              force_web: bool = False, tool_override: str | None = None,
              on_token=None, progress_cb=None) -> dict:
    """Execute a single chat turn with true multi-turn memory, multi-tool research intelligence, and streaming LLM generation."""
    ensure_servers(["main"], progress_cb=progress_cb)
    history = history or []

    # 1) Detect URLs in query
    url_match = re.search(r'https?://[^\s<>"\'\)]+', query)
    detected_url = url_match.group(0) if url_match else None

    chosen_tool = tool_override
    tool_query = None

    if query.startswith("/web "):
        chosen_tool, tool_query = "web", query[5:].strip()
    elif query.startswith("/news "):
        chosen_tool, tool_query = "news", query[6:].strip()
    elif query.startswith("/github "):
        chosen_tool, tool_query = "github", query[8:].strip()
    elif query.startswith("/read "):
        chosen_tool, tool_query = "read", query[6:].strip()
    elif force_web:
        chosen_tool, tool_query = "web", query
    elif detected_url and not chosen_tool:
        chosen_tool, tool_query = "read", detected_url

    # If not manually specified, consult smart intent router
    if not chosen_tool:
        try:
            out = extract_json(chat("main", SYS_SEARCH, query, task="search_decision", max_tokens=60,
                                    schema=SCHEMA_SEARCH), {}) or {}
            t = out.get("tool")
            q = out.get("query")
            if t in ("web", "news", "github", "read") and isinstance(q, str) and q.strip():
                chosen_tool = t
                tool_query = q.strip()
        except Exception:
            chosen_tool = None

    tool_output = ""
    tool_err = None

    if chosen_tool and tool_query:
        if progress_cb:
            progress_cb(f"Executing research tool '{chosen_tool}' on: {tool_query}...")
        try:
            if chosen_tool == "news":
                from research.tools.research_web import news_search
                tool_output = news_search.invoke({"topic": tool_query, "max_results": 4})
            elif chosen_tool == "github":
                from research.tools.research_web import github_search
                tool_output = github_search.invoke({"query": tool_query, "max_results": 4})
            elif chosen_tool == "read":
                from research.tools.research_web import web_reader
                raw_read = web_reader.invoke({"url": tool_query, "max_chars": 3500})
                tool_output = fit(str(raw_read), 3500)
            else:  # 'web'
                res, tool_err = tools.web_search(tool_query, 4)
                tool_output = tools.format_results(res, 3500) if res else ""
        except Exception as e:
            tool_err = str(e)

    # 2) Assemble True Multi-Turn Dialogue Memory (Sliding Window: last 6 turns)
    recent_history = history[-6:] if history else []
    messages = [{"role": "system", "content": SYS_CHAT}]
    for speaker, text in recent_history:
        role_tag = "user" if speaker in ("User", "user", "Human") else "assistant"
        messages.append({"role": role_tag, "content": fit(str(text), 1200)})

    current_turn_prompt = query
    if tool_output:
        current_turn_prompt = f"Live Research Tool Evidence ({chosen_tool.upper()}):\n{fit(tool_output, 3000)}\n\nUser Question: {query}"
    messages.append({"role": "user", "content": current_turn_prompt})

    try:
        ans = chat("main", SYS_CHAT, messages=messages, task="chat", temperature=0.4,
                   stream=bool(on_token), on_token=on_token)
    except Exception as e:
        # Fallback to single turn if anything fails
        if "exceed" in str(e).lower():
            fallback_prompt = f"User Question: {fit(query, 2000)}"
            ans = chat("main", SYS_CHAT, fallback_prompt, task="chat_fallback", temperature=0.4,
                       stream=bool(on_token), on_token=on_token)
        else:
            raise e
    return {
        "answer": ans,
        "search_query": tool_query,
        "tool_used": chosen_tool,
        "web_results": tool_output,
        "web_error": tool_err
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
              force_resume: bool = False, force_fresh: bool = False,
              research: str = "auto", progress_cb=None) -> dict:
    """Execute the autonomous multi-agent code development pipeline."""
    ensure_servers(["main", "writer"], progress_cb=progress_cb)
    from pipeline import run_pipeline
    import checkpoint_manager

    cp = resume_checkpoint
    if cp is None and (force_resume or not force_fresh):
        active = checkpoint_manager.get_active_checkpoint()
        if active:
            cp = checkpoint_manager.prompt_resume_if_available(force_resume=force_resume, force_fresh=force_fresh)

    final = run_pipeline(
        request or (cp.get("task") if cp else ""),
        research=research,
        resume_checkpoint=cp,
        step_callback=progress_cb,
    )
    ans = (final.get("answer") if isinstance(final, dict) else str(final)) or "[done] Pipeline finished."
    return {
        "result": final,
        "summary": ans,
        "resumed": bool(cp),
        "research": final.get("research", ""),
        "research_path": final.get("research_path", ""),
        "notes": final.get("notes", []),
        "warnings": final.get("warnings", []),
    }


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


def code_mode(request: str | None = None, force_resume: bool = False, force_fresh: bool = False, research: str = "auto"):
    one_shot = request is not None
    print("\n[code] coder pipeline (Researcher + RAG + Coder). Kya banana hai batao.")
    print("Tip: `/research <task>` = zabardasti Deep Web Research pehle chalao. `/menu` = wapas, `/exit`.")
    while True:
        q = request or input("\nKya banana hai> ").strip()
        request = None
        if not q:
            continue
        if q in ("/menu", "/exit"):
            return q == "/exit"
        mode_r = research
        if q.startswith("/research "):
            q = q[len("/research "):].strip()
            mode_r = "on"
        res = code_turn(q, force_resume=force_resume, force_fresh=force_fresh, research=mode_r)
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
                "code": lambda: code_mode(args.request, force_resume=getattr(args, "resume", False),
                                          force_fresh=getattr(args, "fresh", False),
                                          research=getattr(args, "research", "auto")),
                "research": lambda: research_mode(args.request)}[mode]()
        if args.mode or done:
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["chat", "rag", "code", "research"])
    ap.add_argument("--request", help="code/research mode: ek baar ka kaam")
    ap.add_argument("--research", choices=["auto", "on", "off"], default="auto", help="research mode (auto | on | off)")
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
