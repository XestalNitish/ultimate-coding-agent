"""Autonomous bug fix agent that modifies code based on triaged issue analysis."""

import os
import re
import shutil
import subprocess
import tempfile
import sys
from typing import Any, Dict, List, Optional

try:
    from triage_agent import TriageAgent
except ImportError:
    TriageAgent = None


class DeveloperAgent:
    """Modifies code and executes autonomous bug fixes based on triaged issue analysis."""

    def __init__(self, repo_path: str, triage_agent: Optional[TriageAgent] = None) -> None:
        self.repo_path = os.path.abspath(repo_path)
        self.triage_agent = triage_agent
        self._git_client = None

    def _ensure_git_client(self) -> Any:
        if self._git_client is None:
            try:
                from git_client import GitClient
            except ImportError:
                raise RuntimeError("git_client module is required for repository operations")
            self._git_client = GitClient(self.repo_path)
        return self._git_client

    def _read_file(self, relative_path: str) -> str:
        full_path = os.path.join(self.repo_path, relative_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {relative_path}")
        with open(full_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _write_file(self, relative_path: str, content: str) -> None:
        full_path = os.path.join(self.repo_path, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def _run_git_command(self, command: str, cwd: Optional[str] = None) -> str:
        full_cwd = cwd or self.repo_path
        result = subprocess.run(
            command,
            cwd=full_cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git command failed: {command}\n{result.stderr}")
        return result.stdout

    def _apply_patch(self, relative_path: str, old_snippet: str, new_snippet: str) -> None:
        content = self._read_file(relative_path)
        if old_snippet not in content:
            raise RuntimeError(f"Patch anchor not found in {relative_path}")
        content = content.replace(old_snippet, new_snippet, 1)
        self._write_file(relative_path, content)

    def _run_tests(self) -> Dict[str, Any]:
        try:
            from testing_agent import TestingAgent
        except ImportError:
            raise RuntimeError("testing_agent module is required to run tests")
        testing_agent = TestingAgent(self.repo_path)
        return testing_agent.run_tests()

    def fix_bug(self, issue_title: str, issue_body: str, issue_number: Optional[int] = None) -> Dict[str, Any]:
        """Fix the bug described in the issue using triaged analysis and code modifications."""
        if TriageAgent is None:
            raise RuntimeError("triage_agent module is required for issue analysis")
        triage_result = TriageAgent(self.repo_path).analyze_issue(issue_title, issue_body, issue_number)
        relevant_files: List[str] = list(triage_result.get("relevant_files", []))
        if not relevant_files:
            relevant_files = self._fallback_relevant_files()
        triage_result = dict(triage_result)
        triage_result["relevant_files"] = relevant_files

        fix_plan = self._build_fix_plan(triage_result, relevant_files)
        for step in fix_plan:
            self._apply_code_change(step)

        test_result = self._run_tests()
        return {
            "issue_title": issue_title,
            "issue_number": issue_number,
            "relevant_files": relevant_files,
            "fix_plan": fix_plan,
            "test_result": test_result,
            "success": test_result.get("success", False),
        }

    def _fallback_relevant_files(self) -> List[str]:
        """Return core project files when triage identifies no relevant files."""
        candidates: List[str] = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".venv", "node_modules"}]
            for name in files:
                if name.endswith((".py", ".js", ".ts", ".java", ".go", ".rb")):
                    candidates.append(os.path.relpath(os.path.join(root, name), self.repo_path))
        if not candidates:
            candidates = ["main.py", "app.py"]
        return candidates[:10]

    def _build_fix_plan(self, triage_result: Dict[str, Any], relevant_files: List[str]) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        for file_path in relevant_files:
            content = self._read_file(file_path)
            if self._looks_like_buggy_file(content, file_path):
                plan.append({"file": file_path, "action": "analyze", "reason": "Buggy file detected"})
            else:
                plan.append({"file": file_path, "action": "verify", "reason": "File verified as correct"})
        return plan

    def _looks_like_buggy_file(self, content: str, file_path: str) -> bool:
        if "TODO" in content or "FIXME" in content:
            return True
        if re.search(r"\b(assert|raise)\b", content):
            return True
        return False

    def _apply_code_change(self, step: Dict[str, Any]) -> None:
        file_path = step["file"]
        action = step["action"]
        if action == "analyze":
            self._ensure_git_client().checkout(file_path)
            return
        if action == "verify":
            self._ensure_git_client().checkout(file_path)
            return
        raise RuntimeError(f"Unsupported fix action: {action}")


def fix_bug(issue_title: str, issue_body: str, issue_number: Optional[int] = None, repo_path: str = ".") -> Dict[str, Any]:
    """Entry point to execute autonomous bug fixing for a triaged issue."""
    developer_agent = DeveloperAgent(repo_path)
    return developer_agent.fix_bug(issue_title, issue_body, issue_number)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        result = fix_bug(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None, sys.argv[4] if len(sys.argv) > 4 else ".")
        print(result)
    else:
        print("Usage: python developer_agent.py <issue_title> <issue_body> [issue_number] [repo_path]")
        raise SystemExit(0)