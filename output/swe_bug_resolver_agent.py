"""Autonomous SWE Bug Resolver & PR Reviewer Agent.

Automated software engineering agent that triages GitHub issues, pinpoints
root-cause files/functions in a codebase, synthesizes AST-valid patches,
verifies them inside a sandboxed test runner, and drafts production PRs.
"""
from __future__ import annotations

import ast
import difflib
import json
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

# Graceful LangSmith Tracing Integration
try:
    import config  # Configures LANGCHAIN_PROJECT, API key & environment
    from langsmith import traceable
except Exception:
    def traceable(*args, **kwargs):
        def decorator(f):
            return f
        return decorator


# ============================================================================
# Domain Models & Data Structures
# ============================================================================

class IssueTicket(BaseModel):
    """GitHub or Jira issue report."""
    issue_id: str
    title: str
    description: str
    stack_trace: Optional[str] = None
    labels: List[str] = Field(default_factory=list)


class PatchProposal(BaseModel):
    """File-level code modification."""
    file_path: str
    original_code: str
    patched_code: str
    diff: str
    ast_valid: bool
    explanation: str


class TestExecutionResult(BaseModel):
    """Sandboxed test run output."""
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_message: Optional[str] = None
    success: bool


class PullRequestPayload(BaseModel):
    """Formally reviewed and finalized Pull Request."""
    pr_id: str
    title: str
    target_branch: str
    source_branch: str
    body_markdown: str
    changed_files: List[str]
    diff_stat: str
    security_audit_passed: bool
    created_at: float


# ============================================================================
# Virtual Codebase Sandbox & Git Mock
# ============================================================================

class VirtualGitRepo:
    """In-memory virtual repository simulating git branches and file states."""

    def __init__(self, initial_files: Optional[Dict[str, str]] = None):
        self._files: Dict[str, str] = dict(initial_files or {})
        self.branches: Dict[str, Dict[str, str]] = {"main": dict(self._files)}
        self.active_branch: str = "main"
        self.commit_history: List[Dict[str, Any]] = []

    def get_file(self, path: str) -> Optional[str]:
        return self._files.get(path)

    def write_file(self, path: str, content: str) -> None:
        self._files[path] = content

    def create_branch(self, branch_name: str) -> None:
        self.branches[branch_name] = dict(self._files)
        self.active_branch = branch_name

    def commit(self, message: str, author: str = "SWE-Agent <agent@local>") -> str:
        commit_id = f"commit_{len(self.commit_history) + 1:04x}"
        self.branches[self.active_branch] = dict(self._files)
        self.commit_history.append({
            "commit_id": commit_id,
            "branch": self.active_branch,
            "message": message,
            "author": author,
            "timestamp": time.time(),
        })
        return commit_id

    def list_files(self) -> List[str]:
        return sorted(self._files.keys())


# ============================================================================
# Specialist Agents: Triage, Patch, Sandbox, PR Reviewer
# ============================================================================

class TriageAgent:
    """Pinpoints relevant source files and functions based on issue traces."""

    @staticmethod
    def identify_culprits(repo: VirtualGitRepo, issue: IssueTicket) -> List[Tuple[str, float, str]]:
        scores: List[Tuple[str, float, str]] = []
        keywords = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", f"{issue.title} {issue.description}"))

        for file_path in repo.list_files():
            content = repo.get_file(file_path) or ""
            score = 0.0
            reasons = []

            # 1. Exact file path match in stack trace
            if issue.stack_trace and file_path in issue.stack_trace:
                score += 10.0
                reasons.append("Exact file path in stack trace")

            # 2. File name mentioned in issue description
            file_base = os.path.basename(file_path)
            if file_base in issue.description or file_base in issue.title:
                score += 5.0
                reasons.append(f"Filename '{file_base}' cited in issue")

            # 3. Token overlap with source content
            file_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", content))
            common_tokens = keywords.intersection(file_tokens)
            score += min(len(common_tokens) * 0.5, 5.0)

            if score > 0:
                scores.append((file_path, score, "; ".join(reasons) or "Semantic token overlap"))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores


class ASTPatchValidator:
    """Ensures patches are valid Python syntax and adhere to safe AST patterns."""

    FORBIDDEN_CALLS = {"eval", "exec", "__import__"}

    @classmethod
    def validate_code(cls, code: str) -> Tuple[bool, Optional[str]]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in cls.FORBIDDEN_CALLS:
                    return False, f"Security Violation: Forbidden call '{func.id}' detected."
        return True, None


class SandboxTestRunner:
    """Executes verification tests against virtual repository states."""

    @staticmethod
    def run_tests(code: str, test_suite_code: str) -> TestExecutionResult:
        """Runs test assertions inside a clean namespace."""
        is_valid, err = ASTPatchValidator.validate_code(code)
        if not is_valid:
            return TestExecutionResult(total_tests=1, passed_tests=0, failed_tests=1,
                                       error_message=err, success=False)

        global_env: Dict[str, Any] = {"__builtins__": __builtins__}
        local_env: Dict[str, Any] = {}

        try:
            exec(compile(code, "<sandbox_src>", "exec"), global_env, local_env)
            # Inject source symbols into test namespace
            test_env = dict(local_env)
            test_env["__builtins__"] = __builtins__
            exec(compile(test_suite_code, "<sandbox_tests>", "exec"), test_env, test_env)

            # Discover and execute test functions
            test_funcs = [v for k, v in test_env.items() if k.startswith("test_") and callable(v)]
            if not test_funcs:
                # If test suite contains direct asserts rather than def test_
                return TestExecutionResult(total_tests=1, passed_tests=1, failed_tests=0, success=True)

            passed = 0
            for fn in test_funcs:
                fn()
                passed += 1

            return TestExecutionResult(total_tests=len(test_funcs), passed_tests=passed,
                                       failed_tests=0, success=True)
        except AssertionError as ae:
            return TestExecutionResult(total_tests=1, passed_tests=0, failed_tests=1,
                                       error_message=f"AssertionError: {ae}", success=False)
        except Exception as exc:
            return TestExecutionResult(total_tests=1, passed_tests=0, failed_tests=1,
                                       error_message=f"{type(exc).__name__}: {exc}", success=False)


class PRReviewAuditor:
    """Generates formatted pull requests with diff metrics and security verification."""

    @staticmethod
    def format_pull_request(issue: IssueTicket, branch: str, patches: List[PatchProposal],
                             test_res: TestExecutionResult) -> PullRequestPayload:
        changed_files = [p.file_path for p in patches]
        total_added = sum(p.diff.count("\n+") for p in patches)
        total_removed = sum(p.diff.count("\n-") for p in patches)
        diff_stat = f"{len(changed_files)} file(s) changed, +{total_added} additions, -{total_removed} deletions"

        body_lines = [
            f"## Automated Pull Request: Fix for Issue #{issue.issue_id}",
            f"**Closes:** #{issue.issue_id} - *{issue.title}*",
            "",
            "### Root Cause & Triage Analysis",
            issue.description,
            "",
            "### Verification & Test Suite Status",
            f"- **Tests Passed:** {test_res.passed_tests}/{test_res.total_tests}",
            f"- **Execution Result:** {'PASS (All Tests Green)' if test_res.success else 'FAIL'}",
            "",
            "### Patch Overview",
        ]

        for p in patches:
            body_lines.append(f"#### `{p.file_path}`")
            body_lines.append(f"*{p.explanation}*")
            body_lines.append("```diff")
            body_lines.append(p.diff.strip())
            body_lines.append("```")

        body_lines.extend([
            "",
            "### Security & AST Audit",
            "- AST Syntax: Valid",
            "- Bandit/Security Guard: Zero forbidden calls (`eval`/`exec`) detected.",
            "- Signed-off by: SWE-Agent v1.0",
        ])

        return PullRequestPayload(
            pr_id=f"PR-{issue.issue_id}",
            title=f"fix({issue.issue_id}): {issue.title}",
            target_branch="main",
            source_branch=branch,
            body_markdown="\n".join(body_lines),
            changed_files=changed_files,
            diff_stat=diff_stat,
            security_audit_passed=test_res.success,
            created_at=time.time(),
        )


# ============================================================================
# Master Orchestrator: Autonomous SWE Resolver
# ============================================================================

class SWEBugResolverAgent:
    """Autonomous agent executing Triage -> Patch -> Sandboxed Test -> PR."""

    def __init__(self, repo: VirtualGitRepo):
        self.repo = repo

    @traceable(name="swe_resolve_issue")
    def resolve_issue(
        self,
        issue: IssueTicket,
        test_suite_code: str,
        patch_synthesizer: Callable[[str, IssueTicket, Optional[str]], str],
        max_attempts: int = 3,
    ) -> PullRequestPayload:
        branch_name = f"agent/fix-{issue.issue_id.lower()}"
        self.repo.create_branch(branch_name)

        # 1. Triage
        culprits = TriageAgent.identify_culprits(self.repo, issue)
        if not culprits:
            raise RuntimeError(f"Triage failed: No relevant files found for issue {issue.issue_id}")

        target_file = culprits[0][0]
        original_code = self.repo.get_file(target_file) or ""

        # 2. Patch & Test Loop
        last_error = issue.stack_trace
        accepted_patch: Optional[PatchProposal] = None
        test_result: Optional[TestExecutionResult] = None

        for attempt in range(1, max_attempts + 1):
            candidate_code = patch_synthesizer(original_code, issue, last_error)
            is_valid, syntax_err = ASTPatchValidator.validate_code(candidate_code)

            if not is_valid:
                last_error = syntax_err
                continue

            test_result = SandboxTestRunner.run_tests(candidate_code, test_suite_code)
            if test_result.success:
                diff_lines = list(difflib.unified_diff(
                    original_code.splitlines(keepends=True),
                    candidate_code.splitlines(keepends=True),
                    fromfile=f"a/{target_file}",
                    tofile=f"b/{target_file}",
                ))
                diff_text = "".join(diff_lines)
                accepted_patch = PatchProposal(
                    file_path=target_file,
                    original_code=original_code,
                    patched_code=candidate_code,
                    diff=diff_text,
                    ast_valid=True,
                    explanation=f"Fixed bug identified in #{issue.issue_id} on attempt {attempt}.",
                )
                self.repo.write_file(target_file, candidate_code)
                self.repo.commit(f"fix({target_file}): resolve {issue.issue_id}", author="SWE-Agent")
                break
            else:
                last_error = test_result.error_message

        if not accepted_patch or not test_result or not test_result.success:
            raise RuntimeError(f"Failed to synthesize working patch after {max_attempts} attempts. Last error: {last_error}")

        # 3. PR Generation
        pr = PRReviewAuditor.format_pull_request(issue, branch_name, [accepted_patch], test_result)
        return pr


# ============================================================================
# Deterministic Standalone Self-Test Suite
# ============================================================================

def selftest() -> bool:
    """Non-interactive test suite running in <2 seconds with zero network."""
    buggy_code = (
        "def calculate_discount(price: float, discount_pct: float) -> float:\n"
        "    # Bug: missing zero check and wrong calculation\n"
        "    if discount_pct > 100:\n"
        "        raise ValueError('Invalid discount')\n"
        "    return price / discount_pct\n"
    )

    test_suite = (
        "def test_discount_normal():\n"
        "    assert calculate_discount(100.0, 20.0) == 80.0\n"
        "def test_discount_fifty():\n"
        "    assert calculate_discount(200.0, 50.0) == 100.0\n"
        "def test_discount_zero():\n"
        "    assert calculate_discount(100.0, 0.0) == 100.0\n"
    )

    # 1. Verify sandbox catches the bug in original code
    res_initial = SandboxTestRunner.run_tests(buggy_code, test_suite)
    assert not res_initial.success, "Initial buggy code should fail tests"

    # 2. Setup virtual repository
    repo = VirtualGitRepo({"pricing/engine.py": buggy_code, "README.md": "# Shop Engine\n"})
    assert repo.get_file("pricing/engine.py") == buggy_code

    # 3. Create issue ticket
    issue = IssueTicket(
        issue_id="ISSUE-402",
        title="ZeroDivisionError when discount is 0% in pricing/engine.py",
        description="Users with 0% discount trigger ZeroDivisionError in calculate_discount.",
        stack_trace="ZeroDivisionError: division by zero at pricing/engine.py:5",
        labels=["bug", "pricing"],
    )

    # 4. Triage Test
    culprits = TriageAgent.identify_culprits(repo, issue)
    assert len(culprits) > 0
    assert culprits[0][0] == "pricing/engine.py", f"Expected pricing/engine.py, got {culprits[0][0]}"

    # 5. Security Validator Test: Ensure dangerous code is rejected
    malicious_code = "import os\ndef test():\n    eval('2+2')\n"
    is_safe, sec_err = ASTPatchValidator.validate_code(malicious_code)
    assert not is_safe
    assert "Forbidden call 'eval'" in (sec_err or "")

    # 6. Mock patch synthesizer simulating agent self-repair
    attempt_counter = {"count": 0}

    def mock_synthesizer(orig: str, iss: IssueTicket, err: Optional[str]) -> str:
        attempt_counter["count"] += 1
        if attempt_counter["count"] == 1:
            # First attempt produces incomplete fix
            return "def calculate_discount(price: float, discount_pct: float) -> float:\n    return price - discount_pct\n"
        # Second attempt produces correct mathematical fix
        return (
            "def calculate_discount(price: float, discount_pct: float) -> float:\n"
            "    if discount_pct < 0 or discount_pct > 100:\n"
            "        raise ValueError('Invalid discount')\n"
            "    return price * (1.0 - (discount_pct / 100.0))\n"
        )

    agent = SWEBugResolverAgent(repo)
    pr = agent.resolve_issue(issue, test_suite, mock_synthesizer, max_attempts=3)

    assert pr.pr_id == "PR-ISSUE-402"
    assert pr.security_audit_passed is True
    assert "pricing/engine.py" in pr.changed_files
    assert "1.0 - (discount_pct / 100.0)" in pr.body_markdown
    assert "agent/fix-issue-402" == pr.source_branch

    # Verify repository has updated commit
    assert len(repo.commit_history) == 1
    assert "fix(pricing/engine.py)" in repo.commit_history[0]["message"]

    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        print("[SWE-Agent] Running Interactive/Demo Mode...")
        selftest()
        print("[SWE-Agent] Demo workflow passed successfully!")
    else:
        selftest()
        print("SELFTEST OK")
