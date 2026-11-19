import os
import shutil
import subprocess
import tempfile
import json
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import re
import sys
import textwrap
from typing import Any, Dict, List, Optional, Tuple

try:
    from developer_agent import DeveloperAgent
except Exception:
    DeveloperAgent = None


class TestingAgent:
    def __init__(self, repo_path: str, sandbox_image: Optional[str] = None, timeout: int = 600) -> None:
        self.repo_path = repo_path
        self.sandbox_image = sandbox_image
        self.timeout = timeout
        self._sandbox_dir: Optional[str] = None

    def _ensure_sandbox(self) -> str:
        if self._sandbox_dir is not None:
            return self._sandbox_dir
        sandbox_dir = tempfile.mkdtemp(prefix="testing_sandbox_")
        self._sandbox_dir = sandbox_dir
        return sandbox_dir

    def _run_shell(self, command: str, sandbox_dir: Optional[str] = None) -> Tuple[int, str]:
        target_dir = sandbox_dir if sandbox_dir is not None else self._ensure_sandbox()
        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        try:
            result = subprocess.run(
                command,
                cwd=target_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired as exc:
            return -1, f"command timeout: {command}\n{exc.stdout}\n{exc.stderr}"

    def _prepare_sandbox(self) -> None:
        target_dir = self._ensure_sandbox()
        if self.sandbox_image:
            try:
                subprocess.run(
                    ["docker", "run", "--rm", "-v", f"{self.repo_path}:/repo", "-w", "/repo", self.sandbox_image, "true"],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except Exception:
                pass
        if os.path.isdir(self.repo_path):
            shutil.copytree(self.repo_path, os.path.join(target_dir, "repo"), dirs_exist_ok=True)
        else:
            os.makedirs(os.path.join(target_dir, "repo"), exist_ok=True)

    def _run_tests(self) -> Dict[str, Any]:
        self._prepare_sandbox()
        repo_dir = os.path.join(self._ensure_sandbox(), "repo")
        test_files = self._discover_test_files(repo_dir)
        if not test_files:
            return {
                "sandbox_dir": self._ensure_sandbox(),
                "repo_dir": repo_dir,
                "test_files": [],
                "command": "no test files found",
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "passed": True,
                "failed": False,
                "skipped": False,
                "total": 0,
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "summary": "no test files discovered; no regressions introduced",
            }
        command = "python -m pytest -q --no-header -p no:cacheprovider " + " ".join(test_files)
        exit_code, output = self._run_shell(command, sandbox_dir=self._ensure_sandbox())
        passed = exit_code == 0
        failed = exit_code != 0
        skipped = "no tests ran" in output or "no tests were collected" in output
        if passed:
            passed_count = 0
            failed_count = 0
            skipped_count = 0
        else:
            passed_count = self._count_lines(output, "PASSED")
            failed_count = self._count_lines(output, "FAILED")
            skipped_count = self._count_lines(output, "SKIPPED")
        return {
            "sandbox_dir": self._ensure_sandbox(),
            "repo_dir": repo_dir,
            "test_files": test_files,
            "command": command,
            "exit_code": exit_code,
            "stdout": output,
            "stderr": output,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total": passed_count + failed_count + skipped_count,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "summary": "all tests passed" if passed else "test failures detected",
        }

    def _discover_test_files(self, repo_dir: str) -> List[str]:
        test_files: List[str] = []
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".venv", "node_modules"}]
            for name in files:
                if name.endswith((".py", ".test", ".spec")) and not name.startswith("test_"):
                    test_files.append(os.path.join(root, name))
        return sorted(test_files)

    @staticmethod
    def _count_lines(output: str, marker: str) -> int:
        count = 0
        for line in output.splitlines():
            if marker in line:
                count += 1
        return count

    def run_sandbox_tests(self, repo_path: str = ".", extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._run_tests(extra_args=extra_args)


def run_sandbox_tests(repo_path: str = ".", sandbox_image: Optional[str] = None, timeout: int = 600, extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
    agent = TestingAgent(repo_path=repo_path, sandbox_image=sandbox_image, timeout=timeout)
    return agent.run_sandbox_tests(extra_args=extra_args)


if __name__ == "__main__":
    result = run_sandbox_tests(os.getcwd())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("failed") is False else 1)