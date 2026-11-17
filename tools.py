"""Web search + REAL tester (LLM se nahi, asli tools se code check hota hai)."""
import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import config as C

# ----------------------------------------------------------------------------
# Web search
# ----------------------------------------------------------------------------

def web_search(query: str, n: int = 4):
    """-> (results, error). results = [{title, url, body}]"""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as d:
            raw = list(d.text(query, max_results=n))
    except Exception as e:  # internet nahi / package missing
        return [], f"web search fail: {e}"
    return [{"title": r.get("title", ""), "url": r.get("href", ""), "body": r.get("body", "")}
            for r in raw], ""


def format_results(results, max_chars: int = 5000) -> str:
    out = []
    for i, r in enumerate(results, 1):
        out.append(f"[{i}] {r['title']}\n{r['body']}\n{r['url']}")
    text = "\n\n".join(out)
    return text[:max_chars]


# ----------------------------------------------------------------------------
# Tester
# ----------------------------------------------------------------------------
WEB_LIBS = {"streamlit", "fastapi", "flask", "uvicorn", "gradio", "django"}

_STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def _top_imports(tree: ast.AST) -> set:
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def _tail(text: str, lines: int = 30, chars: int = 2500) -> str:
    text = (text or "").strip()
    t = "\n".join(text.splitlines()[-lines:])
    return t[-chars:]


def _result(ok: bool, stage: str, report: str, notes=None) -> dict:
    return {"ok": ok, "stage": stage, "report": report, "notes": notes or []}


def _limit_memory():  # sirf Linux/Mac: runaway code RAM na kha jaye
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
    except Exception:
        pass


def test_code(code: str, filename: str = "main.py", timeout: int | None = None) -> dict:
    timeout = timeout or C.TEST_TIMEOUT
    notes = []

    # 1) syntax
    try:
        tree = ast.parse(code)
        compile(code, filename, "exec")
    except SyntaxError as e:
        return _result(False, "syntax", f"SyntaxError: {e.msg} (line {e.lineno}): {(e.text or '').strip()}")
    except Exception as e:
        return _result(False, "syntax", f"{type(e).__name__}: {e}")

    run_dir = Path(tempfile.mkdtemp(prefix="run_", dir=_ensure_work_dir()))
    try:
        path = run_dir / "main.py"
        path.write_text(code, encoding="utf-8")

        # 2) ruff (optional): undefined names / syntax-level errors
        try:
            r = subprocess.run([sys.executable, "-m", "ruff", "check", "--select", "E9,F63,F7,F82",
                                "--no-cache", "--output-format", "concise", str(path)],
                               capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
            if r.returncode == 1 and r.stdout.strip():
                lines = [line for line in r.stdout.replace(str(path), "main.py").splitlines()
                         if line.strip() and not line.startswith(("Found ", "No fixes", "[*]"))]
                return _result(False, "lint", _tail("\n".join(lines)))
        except Exception:
            notes.append("ruff install nahi, lint skip")

        # 3) imports: hallucinated package pakdo
        imports = _top_imports(tree)
        missing_known = []
        for mod in sorted(imports):
            if mod in _STDLIB or mod == "main":
                continue
            try:
                found = importlib.util.find_spec(mod) is not None
            except Exception:
                found = False
            if not found:
                if mod in C.KNOWN_PACKAGES:
                    missing_known.append(mod)
                else:
                    return _result(False, "import",
                                   f"ModuleNotFoundError: No module named '{mod}'. "
                                   f"Ye package exist nahi karta ya standard library me nahi hai - "
                                   f"standard library ya known packages use karo.")
        if missing_known:
            notes.append(f"{', '.join(missing_known)} is PC me install nahi - syntax check hua, run skip")
            return _result(True, "ok", "Syntax OK (run skip: packages missing)", notes)

        # 4) run
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", MPLBACKEND="Agg")
        if imports & WEB_LIBS:
            harness = run_dir / "_harness.py"
            harness.write_text(
                "import importlib.util, sys\n"
                "spec = importlib.util.spec_from_file_location('usercode', 'main.py')\n"
                "m = importlib.util.module_from_spec(spec)\n"
                "sys.modules['usercode'] = m\n"
                "spec.loader.exec_module(m)\n"
                "app = getattr(m, 'app', None)\n"
                "if app is not None and hasattr(app, 'routes'):\n"
                "    print('routes:', len(app.routes))\n"
                "print('import ok')\n", encoding="utf-8")
            cmd = [sys.executable, str(harness)]
            notes.append("web app: sirf import-check hua (server start nahi kiya)")
        else:
            cmd = [sys.executable, str(path)]

        try:
            p = subprocess.run(cmd, cwd=run_dir, env=env, capture_output=True, text=True,
                               timeout=timeout, stdin=subprocess.DEVNULL, encoding="utf-8",
                               errors="replace", preexec_fn=_limit_memory if os.name == "posix" else None)
        except subprocess.TimeoutExpired:
            return _result(False, "run", f"TIMEOUT: program {timeout}s me khatam nahi hua "
                                         f"(infinite loop? ya server/input wait?). Program terminate hona chahiye.")

        err = p.stderr or ""
        if p.returncode == 0:
            out = _tail(p.stdout, 10, 800)
            return _result(True, "ok", f"Run OK.\n{out}".strip(), notes)

        # EOFError on input() = interactive script, bug nahi
        if "EOFError" in err and "input(" in code:
            notes.append("script input() maangti hai - interactive, run-check skip")
            return _result(True, "ok", "Syntax OK (interactive script)", notes)
        # known package ruk gaya
        for mod in C.KNOWN_PACKAGES:
            if f"No module named '{mod}'" in err:
                notes.append(f"{mod} install nahi - run skip")
                return _result(True, "ok", "Syntax OK (package missing)", notes)
        return _result(False, "run", _tail(err or p.stdout).replace(str(run_dir), "."))
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def _ensure_work_dir() -> str:
    C.WORK_DIR.mkdir(parents=True, exist_ok=True)
    return str(C.WORK_DIR)
