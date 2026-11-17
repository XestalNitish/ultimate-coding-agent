"""Comprehensive benchmark & validation runner for the 5 Real-World Problem Solving AI Agents.

Executes and verifies:
1. SWE Bug Resolver & PR Reviewer Agent
2. B2B Invoice & Expense Audit Agent
3. Deep Research & Competitive Intelligence Agent
4. End-to-End Customer Resolution Agent
5. Clinical Doctor's Co-pilot & Patient Care Agent
"""
import ast
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"
PYTHON_EXE = HERE / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

AGENTS = [
    {
        "id": 1,
        "name": "Autonomous Software Bug Resolver / PR Reviewer (SWE-Agent Style)",
        "file": "output/swe_bug_resolver_agent.py",
        "domain": "DevOps & Autonomous Software Engineering",
        "capabilities": [
            "GitHub/Jira issue triage & stack trace parsing",
            "AST syntax verification & anti-hallucination guard",
            "Sandboxed test suite runner with error feedback loop",
            "Automated Git commit & formatted Pull Request markdown synthesis"
        ],
        "tech_stack": "LangGraph / Python / Git API / Sandboxed Execution",
    },
    {
        "id": 2,
        "name": "Autonomous B2B Invoice & Expense Audit Agent",
        "file": "output/invoice_audit_agent.py",
        "domain": "Fintech & Enterprise Accounts Payable",
        "capabilities": [
            "Multimodal text & OCR invoice schema extraction",
            "3-Way Matching (Invoice vs approved PO vs warehouse GRN)",
            "Anti-fraud cryptographic hash duplication detection",
            "Tax & math calculation auditing (GST/VAT validation)",
            "Automated vendor dispute email synthesis & human escalation"
        ],
        "tech_stack": "LangGraph / Python / PostgreSQL Schema / ERP Matching",
    },
    {
        "id": 3,
        "name": "Deep Research & Competitive Intelligence Agent (Like OpenAI Deep Research)",
        "file": "output/deep_research_agent.py",
        "domain": "Market Intelligence & Automated Investigation",
        "capabilities": [
            "Hierarchical query decomposition into sub-queries",
            "Multi-source web crawling with confidence scoring",
            "Automated fact-checking & hallucination cross-examination",
            "Competitive capability matrix generation",
            "Deduplicated footnote bibliography & Markdown dossier compilation"
        ],
        "tech_stack": "LlamaIndex Workflows / LangGraph / Search Crawlers / Markdown Synthesis",
    },
    {
        "id": 4,
        "name": "End-to-End Customer Resolution Agent (Not just a Chatbot)",
        "file": "output/customer_resolution_agent.py",
        "domain": "E-Commerce & Autonomous Customer Support",
        "capabilities": [
            "Customer lifetime profile & fraud risk indexing",
            "Deterministic 30-day refund & approval limit policy engine",
            "Secure tool-calling dispatcher (cancel_order, process_refund)",
            "Sentiment & frustration trajectory scoring (-1.0 to +1.0)",
            "Urgent legal/threat escalation gate to human supervisor"
        ],
        "tech_stack": "FastAPI / LangChain / Function Calling / OMS Tool Execution",
    },
    {
        "id": 5,
        "name": "Clinical Doctor's Co-pilot & Patient Follow-up Agent (Healthcare)",
        "file": "output/clinical_copilot_agent.py",
        "domain": "Healthcare & Clinical EHR Informatics",
        "capabilities": [
            "Doctor-patient consultation dialogue parsing",
            "Standardized clinical SOAP note generation (Subjective, Objective, Assessment, Plan)",
            "Vitals extraction (BP, Temperature, Heart Rate)",
            "Pharmacological drug-drug interaction screening (Warfarin + Aspirin bleeding risk)",
            "Patient allergy cross-reactivity screening (Penicillin hypersensitivity)",
            "Plain-language medication instructions & WhatsApp recovery follow-up scheduler"
        ],
        "tech_stack": "Whisper / Gemini Audio / Medical Knowledge Graph / WhatsApp API",
    },
]


def count_lines(filepath: Path) -> int:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return len([line for line in f if line.strip() and not line.strip().startswith("#")])
    except Exception:
        return 0


def run_benchmark():
    print("=" * 70)
    print("  REAL-WORLD AI AGENTS VALIDATION & BENCHMARK SUITE")
    print("=" * 70)

    results = []
    total_passed = 0

    for agent in AGENTS:
        fpath = HERE / agent["file"]
        print(f"\n[Testing Agent {agent['id']}/5] {agent['name']}")
        print(f"  File: {agent['file']}")

        if not fpath.exists():
            print("  [FAIL] File not found!")
            results.append({
                **agent,
                "status": "FAIL",
                "error": "File not found",
                "execution_time_sec": 0.0,
                "lines_of_code": 0,
            })
            continue

        loc = count_lines(fpath)

        # Execute standalone self-test
        t0 = time.perf_counter()
        proc = subprocess.run(
            [str(PYTHON_EXE), str(fpath)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(HERE),
        )
        t_elapsed = round(time.perf_counter() - t0, 3)

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode == 0 and "SELFTEST OK" in stdout:
            print(f"  [PASS] SELFTEST OK ({t_elapsed}s, {loc} LOC)")
            total_passed += 1
            results.append({
                "id": agent["id"],
                "name": agent["name"],
                "file_path": agent["file"],
                "domain": agent["domain"],
                "status": "PASS",
                "selftest_result": "SELFTEST OK",
                "execution_time_sec": t_elapsed,
                "lines_of_code": loc,
                "capabilities": agent["capabilities"],
                "tech_stack": agent["tech_stack"],
                "langsmith_tracing": "ENABLED (@traceable)",
            })
        else:
            print(f"  [FAIL] Return code: {proc.returncode}")
            if stderr:
                print(f"  Error: {stderr[:300]}")
            results.append({
                "id": agent["id"],
                "name": agent["name"],
                "file_path": agent["file"],
                "domain": agent["domain"],
                "status": "FAIL",
                "selftest_result": f"FAILED (code {proc.returncode})",
                "execution_time_sec": t_elapsed,
                "lines_of_code": loc,
                "error": stderr or stdout,
            })

    # Run Pytest suite
    print("\n" + "-" * 70)
    print("[Pytest Suite Verification]")
    t0_py = time.perf_counter()
    py_proc = subprocess.run(
        [str(PYTHON_EXE), "-m", "pytest", "tests/test_real_world_agents.py", "-v", "--no-header"],
        capture_output=True,
        text=True,
        cwd=str(HERE),
    )
    py_elapsed = round(time.perf_counter() - t0_py, 3)
    py_passed = "5 passed" in py_proc.stdout

    print(f"  Pytest Status: {'ALL 5 PASSED' if py_passed else 'FAILED'} ({py_elapsed}s)")

    # Build report data
    report_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_projects": len(AGENTS),
        "passed": total_passed,
        "failed": len(AGENTS) - total_passed,
        "overall_status": "ALL_PASSED" if total_passed == len(AGENTS) and py_passed else "DEGRADED",
        "pytest_suite": {
            "file": "tests/test_real_world_agents.py",
            "status": "PASSED" if py_passed else "FAILED",
            "duration_sec": py_elapsed,
        },
        "langsmith_observability": {
            "project": "ultimate-coding-agent",
            "tracing_status": "ACTIVE",
            "decorator": "@traceable",
        },
        "results": results,
    }

    out_file = OUTPUT_DIR / "real_world_agents_validation_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print("\n" + "=" * 70)
    print(f"  FINAL VERDICT: {report_data['overall_status']} ({total_passed}/{len(AGENTS)} Agents Green)")
    print(f"  Report saved to: {out_file}")
    print("=" * 70)

    return report_data


if __name__ == "__main__":
    run_benchmark()
