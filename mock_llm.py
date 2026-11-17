"""Fake LLM - sirf selftest ke liye (MOCK_LLM=1). Real model ki zarurat nahi."""
import json
import os

_state = {"coder": 0, "debugger": 0}

BUGGY = '''import math


def circle_area(r):
    return math.pi * radius * radius   # BUG: radius defined nahi hai


if __name__ == "__main__":
    assert abs(circle_area(1) - math.pi) < 1e-9
    print("ok")
'''

FIXED = '''import math


def circle_area(r):
    return math.pi * r * r


if __name__ == "__main__":
    assert abs(circle_area(1) - math.pi) < 1e-9
    print("ok")
'''


def reset():
    _state["coder"] = 0
    _state["debugger"] = 0


def mock_chat(role: str, task: str, system: str, user: str) -> str:
    always_fail = os.environ.get("MOCK_ALWAYS_FAIL") == "1"
    sys_lower = (system or "").lower()
    usr_lower = (user or "").lower()

    if "web research is needed" in sys_lower or "gate" in sys_lower:
        return json.dumps({"needs_research": False, "reason": "simple task"})

    if "retrieval planner" in sys_lower or "mediator" in sys_lower or task == "mediator":
        return json.dumps({"needs_rag": False, "questions": []})

    if "extract from the documentation" in sys_lower or task == "doc_summary":
        return "math.pi is a float constant (3.14159...). Import with `import math`."

    if "senior software planner" in sys_lower or "synthesize" in sys_lower or "spec for a coder" in sys_lower:
        return json.dumps({
            "summary": "Calculate area of circle",
            "requirements": ["Import math", "Define circle_area(r)", "Add self-test asserting unit circle"],
            "acceptance": ["circle_area(1) == math.pi"],
            "constraints": ["Standard library only"],
            "needs_docs": False,
            "doc_questions": [],
        })

    if "software architect" in sys_lower or "file tree planner" in sys_lower or "architect" in sys_lower:
        return json.dumps({
            "project_name": "circle_project",
            "needs_docs": False,
            "entry_point": "main.py",
            "run_mode": "script",
            "synthesized_spec": "Calculate circle area function",
            "files": [
                {
                    "path": "main.py",
                    "purpose": "Define circle_area and self-test",
                    "exports": ["circle_area"],
                    "depends_on": [],
                }
            ],
            "dependencies": [],
        })

    if "writer" in role.lower() or "senior software developer" in sys_lower or "file writer" in sys_lower or role == "writer":
        _state["coder"] += 1
        if _state["coder"] == 1:
            return "```python\n" + BUGGY + "```"
        return "```python\n" + (BUGGY if always_fail else FIXED) + "```"

    if "debugger" in sys_lower or task == "debugger":
        _state["debugger"] += 1
        return json.dumps({
            "root_cause": "Variable radius is not defined, parameter is r",
            "fix_instructions": "Change radius to r in math.pi * r * r",
        })

    if "previous coding attempt failed" in sys_lower or task == "failure_summary":
        return "Previous attempt failed: variable radius was used instead of parameter r."

    if "search" in task or "search" in sys_lower:
        return json.dumps({"search": None})

    if task == "research_queries":
        return json.dumps({"queries": ["python circle area"]})
    if task == "research_summary":
        return "Area of circle = pi * r^2. Use math.pi."

    return "```python\n" + (BUGGY if (_state["coder"] == 0 or always_fail) else FIXED) + "```"
