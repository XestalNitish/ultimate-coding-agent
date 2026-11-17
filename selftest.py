"""Fake LLM + hash embeddings se poora flow check (real model/download ki zarurat nahi).
    python main.py --selftest
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["MOCK_LLM"] = "1"

import config as C          # noqa: E402

RESULTS = []


def check(name: str, cond: bool, extra: str = ""):
    RESULTS.append(cond)
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f"  -> {extra}" if (extra and not cond) else ""))


def make_pdf(path: Path):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    doc = fitz.open()
    page = doc.new_page()
    y = 60

    def block(text, size=11):
        nonlocal y
        for line in text.splitlines():
            page.insert_text((60, y), line, fontsize=size)
            y += size + 4
        y += 26                     # bada gap -> naya block

    block("Background Tasks", 16)
    block("You can define background tasks to be run after returning a response. "
          "Import BackgroundTasks from fastapi and declare a parameter of that type in your path function.")
    block("from fastapi import BackgroundTasks, FastAPI\napp = FastAPI()\n"
          "@app.post('/send')\ndef send(bg: BackgroundTasks):\n    bg.add_task(print, 'hi')")
    block("Session State", 16)
    block("Streamlit reruns your script on each interaction. Use st.session_state to keep values "
          "between reruns. It behaves like a dictionary.")
    doc.save(path)


def run() -> int:
    from rag.upload__docs import upload_file
    import pipeline
    import rag
    import tools
    import mock_llm

    tmp = Path(tempfile.mkdtemp(prefix="selftest_"))
    C.ROOT, C.DB_DIR, C.DOCS_DIR = tmp, tmp / "db", tmp / "docs"
    C.LOG_DIR, C.WORK_DIR = tmp / "logs", tmp / "work"
    C.CHUNK_CHARS = 300             # chhota PDF bhi kai chunks me tute
    try:
        print("1) RAG ingest + search")
        (C.DOCS_DIR / "fastapi@0.115").mkdir(parents=True)
        pdf_path = C.DOCS_DIR / "fastapi@0.115" / "guide.pdf"
        make_pdf(pdf_path)
        upload_file(str(pdf_path), library="fastapi", file_type="pdf")
        store = rag.get_store(reload=True)
        check("chunks bane", len(store.chunks) >= 1, str(len(store.chunks)))
        check("library metadata", "fastapi" in store.libraries())
        hits = rag.search("how to run background tasks after response", k=2)
        check("search sahi chunk laya", bool(hits) and "BackgroundTasks" in hits[0]["text"],
              hits[0]["text"][:80] if hits else "no hits")
        code_chunk = next((c for c in store.chunks if "add_task" in c["text"]), None)
        check("code block ek chunk me saath", code_chunk is not None and "@app.post" in code_chunk["text"]
              and "def send" in code_chunk["text"])

        print("2) Tester (real tools)")
        t = tools.test_code("print('hi')\n")
        check("sahi code PASS", t["ok"], str(t))
        t = tools.test_code("def f(:\n  pass\n")
        check("syntax error pakda", (not t["ok"]) and t["stage"] == "syntax")
        t = tools.test_code("x = undefined_name + 1\nprint(x)\n")
        check("NameError pakda", (not t["ok"]) and t["stage"] in ("lint", "run"), str(t))
        t = tools.test_code("import totally_fake_pkg_xyz\n")
        check("hallucinated import pakda", (not t["ok"]) and t["stage"] == "import", str(t))
        t = tools.test_code("name = input('n: ')\nprint(name)\n")
        check("input() script bug nahi maani", t["ok"], str(t))
        t = tools.test_code("while True:\n    pass\n", timeout=3)
        check("infinite loop timeout", (not t["ok"]) and "TIMEOUT" in t["report"], str(t))
        t = tools.test_code("assert 1 + 1 == 3, 'math toota'\n")
        check("assert fail pakda", (not t["ok"]) and "math toota" in t["report"], str(t))

        print("3) Pipeline: bug -> debugger -> pass")
        mock_llm.reset()
        os.environ.pop("MOCK_ALWAYS_FAIL", None)
        final = pipeline.run_pipeline("circle ka area nikalne ka function", research="off")
        check("final ok", final.get("ok") is True, str(final.get("answer")))
        check("debugger ne fix kiya", final.get("attempts", 1) >= 1, str(final.get("attempts")))
        check("output file bani", Path(final.get("out_path", "")).exists())

        print("4) Pipeline: hamesha fail -> retry x restart")
        mock_llm.reset()
        os.environ["MOCK_ALWAYS_FAIL"] = "1"
        final = pipeline.run_pipeline("circle ka area nikalne ka function", research="off")
        check("ok False", final.get("ok") is False)
        check("planner restart record hua", final.get("restarts", 0) > 0 or not final.get("ok"),
              str(final.get("restarts")))
        check("failure summary ya error aage gayi", bool(final.get("failure_summary") or final.get("status") in ("failed", "error")))
        os.environ.pop("MOCK_ALWAYS_FAIL", None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = RESULTS.count(False)
    print(f"\n{'SAB OK' if not bad else str(bad) + ' check FAIL'} ({len(RESULTS)} checks)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(run())
