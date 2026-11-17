"""
test_code_dev_agent.py — Complete Verification & Live Test Runner for code_dev_agent.py
=======================================================================================
Tests:
  1. Context Window Compaction Guard (15,000+ chars -> compacted cleanly)
  2. Topological File Dependency Sorting (leaf modules first, entry point last)
  3. Static AST Validator (catches syntax errors, pass/stub functions, broken internal imports)
  4. Zero-LLM Deterministic Debugger (pinpoints ImportError/AttributeError + AST symbol suggestions)
  5. Full LangGraph E2E Multi-File Pipeline (Mocked LLM + Live Local LLM if server is running)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from code_dev import (
    _deterministic_diagnose,
    _topological_sort_files,
    compact_context_text,
    run_code_dev_task,
    validate_content,
)


def print_banner(title: str) -> None:
    print(f"\n{'=' * 70}\n[TEST] {title}\n{'=' * 70}")


# --------------------------------------------------------------------------- #
# 1. Test Context Window Compactor
# --------------------------------------------------------------------------- #
def test_context_compactor() -> None:
    print_banner("1. Testing Context Window Overflow Guard (compact_context_text)")
    huge_research_text = (
        "# Architecture Spec\n"
        "- File: core/chunker.py\n"
        "def chunk_text(text: str, size: int) -> list[str]:\n"
        + ("This is filler background research text that overflows the context window. " * 300)
        + "\n# Final Constraint: Must return list of strings."
    )
    max_allowed = 1200
    compacted = compact_context_text(huge_research_text, max_chars=max_allowed, label="research_context")

    print(f"Original Length : {len(huge_research_text)} chars")
    print(f"Compacted Length: {len(compacted)} chars (Limit: {max_allowed})")
    assert len(compacted) <= max_allowed, "Compacted text exceeded max_chars!"
    assert "chunk_text" in compacted or "Architecture Spec" in compacted
    print("[PASS] Context window guard compacted text cleanly while preserving key headers/signatures.")


# --------------------------------------------------------------------------- #
# 2. Test Topological Multi-File Sorter
# --------------------------------------------------------------------------- #
def test_topological_sorter() -> None:
    print_banner("2. Testing Multi-File Topological Dependency Ordering")
    planned_files = [
        {"path": "main.py", "purpose": "entry", "depends_on": ["services/rag.py", "utils/cleaner.py"]},
        {"path": "services/rag.py", "purpose": "rag", "depends_on": ["utils/cleaner.py"]},
        {"path": "utils/cleaner.py", "purpose": "leaf utility", "depends_on": []},
        {"path": "requirements.txt", "purpose": "deps", "depends_on": []},
    ]
    sorted_plan = _topological_sort_files(planned_files, entry="main.py")
    order = [p["path"] for p in sorted_plan]
    print("Planned Order :", [p["path"] for p in planned_files])
    print("Sorted Order  :", order)

    assert order[0] == "requirements.txt", "requirements.txt must be first!"
    assert order.index("utils/cleaner.py") < order.index("services/rag.py"), "Leaf dependency must come before dependent!"
    assert order[-1] == "main.py", "Entry point must be written last!"
    print("[PASS] Files are ordered topologically (Dependencies -> Services -> Entry Point).")


# --------------------------------------------------------------------------- #
# 3. Test Static AST Validator (Stub & Import Check)
# --------------------------------------------------------------------------- #
def test_static_ast_validator() -> None:
    print_banner("3. Testing Static AST Validator (Stubs & Broken Internal Imports)")
    project_paths = ["utils/math_ops.py", "main.py"]

    # Case A: Stub function should be rejected
    stub_code = "def calculate_score(x: int) -> int:\n    pass\n"
    err_stub = validate_content("utils/math_ops.py", stub_code, project_paths)
    print("Stub Check Result       :", err_stub)
    assert err_stub and "stub" in err_stub.lower(), "Failed to catch pass-only stub function!"

    # Case B: Hallucinated internal submodule import should be rejected
    bad_import_code = "from utils.non_existent_helper import something\n\ndef main():\n    return 1\n"
    err_imp = validate_content("main.py", bad_import_code, project_paths)
    print("Bad Import Check Result :", err_imp)
    assert err_imp and "Invalid internal import" in err_imp, "Failed to catch hallucinated internal import!"

    # Case C: Valid complete code should pass
    valid_code = "def calculate_score(x: int) -> int:\n    return x * 2\n"
    err_valid = validate_content("utils/math_ops.py", valid_code, project_paths)
    print("Valid Code Check Result :", err_valid)
    assert err_valid is None, f"Valid code was unexpectedly rejected: {err_valid}"
    print("[PASS] Static validator catches stubs and fake internal imports with 100% precision.")


# --------------------------------------------------------------------------- #
# 4. Test Zero-LLM Deterministic Debugger
# --------------------------------------------------------------------------- #
def test_zero_llm_debugger() -> None:
    print_banner("4. Testing Zero-LLM Deterministic Debugger (_deterministic_diagnose)")
    mock_files = {
        "utils/math_ops.py": "def compute_ cosine_similarity(a, b):\n    return 1.0\n",
        "utils/scorer.py": "def calculate_bm25_score(query: str, doc: str) -> float:\n    return 0.95\n",
        "main.py": (
            "from utils.scorer import calc_bm25_score\n\n"
            "if __name__ == '__main__':\n"
            "    print(calc_bm25_score('ai', 'agentic ai'))\n"
        ),
    }
    fake_traceback = (
        'Traceback (most recent call last):\n'
        '  File "/tmp/sandbox/project/main.py", line 1, in <module>\n'
        '    from utils.scorer import calc_bm25_score\n'
        "ImportError: cannot import name 'calc_bm25_score' from 'utils.scorer' (/tmp/sandbox/project/utils/scorer.py)"
    )

    diagnosis, updated_targets = _deterministic_diagnose(fake_traceback, mock_files, ["main.py"])
    print("Deterministic Debugger Output:\n" + "-" * 40)
    print(diagnosis)
    print("-" * 40)
    print("Targeted Files for Fix:", updated_targets)

    assert "calculate_bm25_score" in diagnosis, "Debugger should suggest the exact AST match `calculate_bm25_score`!"
    assert "Line 1:" in diagnosis, "Debugger should extract the exact crashing line!"
    print("[PASS] Zero-LLM Debugger diagnosed ImportError and found the closest AST symbol via difflib.")


# --------------------------------------------------------------------------- #
# 5. Test Full Multi-File Pipeline (Simulated Self-Healing + RAG Fallback)
# --------------------------------------------------------------------------- #
def test_full_pipeline_simulated() -> None:
    print_banner("5. Testing Full LangGraph Multi-File Pipeline (RAG Fallback + Auto-Debug)")

    # Sequence of mocked LLM outputs:
    # 1) Planner JSON (Notice needs_docs=True, while rag_docs="" -> triggers fallback_no_rag)
    # 2) Writer writes `core/processor.py`
    # 3) Writer writes `main.py` with a deliberate typo (`process_dat` instead of `process_data`) on attempt 1
    # 4) Debugger runs WITHOUT LLM, catches the typo via AST, and Writer fixes `main.py` on attempt 2!
    planner_json = json.dumps({
        "project_name": "rag_text_pipeline",
        "needs_docs": True,
        "entry_point": "main.py",
        "run_mode": "script",
        "synthesized_spec": "Build a clean text processor module and main runner.",
        "files": [
            {
                "path": "core/processor.py",
                "purpose": "Normalize and tokenize input text chunks",
                "exports": ["process_data"],
                "depends_on": []
            },
            {
                "path": "main.py",
                "purpose": "Entry script that runs self-tests on process_data",
                "exports": [],
                "depends_on": ["core/processor.py"]
            }
        ],
        "dependencies": []
    })

    processor_code = (
        "def process_data(text: str) -> list[str]:\n"
        "    cleaned = text.strip().lower()\n"
        "    return [w for w in cleaned.split() if len(w) > 1]\n"
    )

    # Deliberate bug in 1st attempt of main.py: imports `process_dat` instead of `process_data`
    main_code_buggy = (
        "from core.processor import process_dat\n\n"
        "if __name__ == '__main__':\n"
        "    res = process_dat('  Hello Agentic World  ')\n"
        "    print('Processed tokens:', res)\n"
    )

    # Fixed main.py on 2nd attempt after Zero-LLM Debugger instructs writer to use `process_data`
    main_code_fixed = (
        "from core.processor import process_data\n\n"
        "if __name__ == '__main__':\n"
        "    res = process_data('  Hello Agentic World  ')\n"
        "    assert res == ['hello', 'agentic', 'world'], f'Unexpected: {res}'\n"
        "    print('SUCCESS -> Processed tokens:', res)\n"
    )

    responses = iter([planner_json, processor_code, main_code_buggy, main_code_fixed])

    def fake_llm_text(system: str, user: str, *args, **kwargs) -> str:
        return next(responses)

    temp_out = tempfile.mkdtemp(prefix="test_out_")
    try:
        with patch("code_dev._llm_text", side_effect=fake_llm_text):
            def on_step(node: str, update: dict) -> None:
                status = update.get("status", "")
                doc_st = update.get("doc_status", "")
                fix_inst = update.get("fix_instructions", "")
                extra = f" | status={status}" if status else ""
                extra += f" | doc_status={doc_st}" if doc_st else ""
                print(f"  -> Node [{node.upper()}] completed{extra}")
                if node == "debugger" and fix_inst:
                    print(f"     [Zero-LLM Debugger Fix Directive]: {fix_inst.splitlines()[0]}")

            result = run_code_dev_task(
                task="Build a multi-file text tokenizer pipeline with self-tests.",
                research_context="Use clean functional tokenization without external heavy libraries.",
                rag_docs="",  # Empty RAG docs -> tests fallback_no_rag
                output_dir=temp_out,
                use_llm_debugger=False,  # 100% Zero-LLM Debugger
                step_callback=on_step,
            )

        print("\n--- Final Execution Summary ---")
        print("Final Status     :", result["status"])
        print("RAG Doc Mode     :", result["doc_status"])
        print("Generated Files  :", list(result["files"].keys()))
        print("Execution Output :", result["execution_output"])

        assert result["status"] == "success", f"Expected success, got {result['status']} ({result.get('error')})"
        assert result["doc_status"] == "fallback_no_rag", "Planner should record fallback_no_rag when rag_docs is empty!"
        assert "core/__init__.py" in result["files"], "Auto __init__.py injection failed!"
        assert "SUCCESS -> Processed tokens:" in result["execution_output"]
        print("[PASS] End-to-End Multi-File Pipeline + RAG Fallback + Zero-LLM Self-Healing Verified!")
    finally:
        shutil.rmtree(temp_out, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 6. Optional Live LLM Test (Runs automatically if "--live" flag is passed)
# --------------------------------------------------------------------------- #
def run_live_llm_test() -> None:
    print_banner("6. Running LIVE LLM Multi-File Task (Real Model Inference)")
    res = run_code_dev_task(
        task=(
            "Create a 2-file Python project: `math_utils/stats.py` with functions `mean(nums)` and `median(nums)`, "
            "and `main.py` that imports them, runs assertion tests on sample data, and prints the results."
        ),
        research_context="Ensure division by zero is handled if an empty list is passed.",
        rag_docs="",  # Test working without RAG docs
        use_llm_debugger=False,
        step_callback=lambda node, upd: print(f"  [LIVE {node.upper()}] done"),
    )
    print("\n" + res["reply"])


if __name__ == "__main__":
    test_context_compactor()
    test_topological_sorter()
    test_static_ast_validator()
    test_zero_llm_debugger()
    test_full_pipeline_simulated()

    if "--live" in sys.argv:
        run_live_llm_test()
    else:
        print("\nTip: Run `python test_code_dev_agent.py --live` when your local LLM server is active to test live generation.")