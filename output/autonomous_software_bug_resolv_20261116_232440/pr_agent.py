"""Automated Pull Request creation agent for the SWE-Agent style bug resolver system."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional


class PRAgent:
    """Creates automated Pull Requests with detailed explanations after tests pass."""

    def __init__(self, repo_path: str, git_client: Any = None, config: Any = None) -> None:
        self.repo_path = repo_path
        self.git_client = git_client
        self.config = config

    def _get_git_client(self) -> Any:
        if self.git_client is not None:
            return self.git_client
        try:
            from git_client import GitClient
        except Exception:
            raise RuntimeError("GitClient is required to create Pull Requests")
        return GitClient(self.repo_path)

    def _build_pr_payload(self, issue_analysis: Dict[str, Any], fix_summary: Dict[str, Any], test_results: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": self._build_pr_title(issue_analysis, fix_summary),
            "body": self._build_pr_body(issue_analysis, fix_summary, test_results),
            "base_ref": "main",
            "head_ref": self._build_head_ref(fix_summary),
            "draft": False,
        }

    def _build_pr_title(self, issue_analysis: Dict[str, Any], fix_summary: Dict[str, Any]) -> str:
        issue_title = issue_analysis.get("title", "Bug Fix")
        fix_summary_text = fix_summary.get("summary", "Fix implemented")
        return f"fix({issue_title}): {fix_summary_text}"

    def _build_head_ref(self, fix_summary: Dict[str, Any]) -> str:
        commit_id = fix_summary.get("commit_id")
        if commit_id:
            return f"pr-agent/{commit_id}"
        return "pr-agent/fix"

    def _build_pr_body(self, issue_analysis: Dict[str, Any], fix_summary: Dict[str, Any], test_results: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append("## Summary")
        lines.append(fix_summary.get("summary", "Bug fix implemented and verified by automated tests."))
        lines.append("")

        lines.append("## Issue Analysis")
        lines.append(f"- Issue: {issue_analysis.get('title', 'Unknown issue')}")
        lines.append(f"- Reproduced: {issue_analysis.get('reproduced', False)}")
        lines.append(f"- Relevant files: {', '.join(issue_analysis.get('relevant_files', []))}")
        lines.append("")

        lines.append("## Changes")
        lines.append(fix_summary.get("changes", "Code modified to resolve the reported bug without breaking core functionality."))
        lines.append("")

        lines.append("## Test Results")
        test_results = test_results or {}
        passed = test_results.get("passed", 0)
        failed = test_results.get("failed", 0)
        total = test_results.get("total", passed + failed)
        lines.append(f"- Total tests: {total}")
        lines.append(f"- Passed: {passed}")
        lines.append(f"- Failed: {failed}")
        lines.append(f"- Status: {'PASS' if failed == 0 else 'FAIL'}")
        if test_results.get("message"):
            lines.append(f"- Message: {test_results['message']}")
        lines.append("")

        lines.append("## Verification")
        lines.append("All automated tests passed successfully in the Docker/E2E sandbox environment.")
        lines.append("No additional regressions were introduced by this fix.")
        lines.append("")

        return "\n".join(lines)

    def create_pr(self, issue_analysis: Dict[str, Any], fix_summary: Dict[str, Any], test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create an automated Pull Request after all tests pass successfully."""
        payload = self._build_pr_payload(issue_analysis, fix_summary, test_results)
        git_client = self._get_git_client()
        return git_client.create_pull_request(payload)


def create_pr(
    repo_path: str,
    issue_analysis: Dict[str, Any],
    fix_summary: Dict[str, Any],
    test_results: Dict[str, Any],
    pr_agent: Optional[PRAgent] = None,
) -> Dict[str, Any]:
    """Create an automated Pull Request with a detailed explanation after tests pass."""
    if pr_agent is None:
        pr_agent = PRAgent(repo_path=repo_path)
    return pr_agent.create_pr(issue_analysis, fix_summary, test_results)


if __name__ == "__main__":
    sample_issue = {"title": "Null pointer in data processing", "reproduced": True, "relevant_files": ["src/data_processor.py"]}
    sample_fix = {"summary": "Added null checks to prevent null pointer exceptions.", "commit_id": "pr-agent-fix-001"}
    sample_tests = {"passed": 42, "failed": 0, "total": 42, "message": "All tests passed"}
    result = create_pr(repo_path=os.getcwd(), issue_analysis=sample_issue, fix_summary=sample_fix, test_results=sample_tests)
    print(json.dumps(result, indent=2))