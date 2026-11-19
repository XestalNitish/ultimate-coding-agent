import os
import json
import subprocess
import tempfile
import shutil
from typing import Any, Dict, List, Optional

try:
    from config import Config
except ImportError:
    Config = None

try:
    from git_client import GitClient
except ImportError:
    GitClient = None

try:
    from triage_agent import TriageAgent
except ImportError:
    TriageAgent = None

try:
    from developer_agent import DeveloperAgent
except ImportError:
    DeveloperAgent = None

try:
    from testing_agent import TestingAgent
except ImportError:
    TestingAgent = None

try:
    from pr_agent import PRAgent
except ImportError:
    PRAgent = None


def run_agent_workflow(
    issue_title: str,
    issue_body: str,
    issue_number: Optional[int] = None,
    repo_path: str = ".",
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    if config is None:
        config = Config()

    git_client = GitClient(repo_path, config.GITHUB_TOKEN)
    triage_agent = TriageAgent(repo_path, config.GITHUB_TOKEN)
    developer_agent = DeveloperAgent(repo_path, triage_agent)
    testing_agent = TestingAgent(repo_path, config.E2B_API_KEY, config.TEST_TIMEOUT)
    pr_agent = PRAgent(repo_path, git_client, config)

    issue_analysis = triage_agent.analyze_issue(issue_title, issue_body, issue_number)
    fix_summary = developer_agent.fix_bug(issue_title, issue_body, issue_number)
    test_results = testing_agent.run_sandbox_tests(repo_path, config.E2B_API_KEY, config.TEST_TIMEOUT)

    if test_results.get("success", False):
        pr_result = pr_agent.create_pr(issue_analysis, fix_summary, test_results)
        return {
            "issue_analysis": issue_analysis,
            "fix_summary": fix_summary,
            "test_results": test_results,
            "pull_request": pr_result,
            "workflow_status": "completed",
        }
    return {
        "issue_analysis": issue_analysis,
        "fix_summary": fix_summary,
        "test_results": test_results,
        "pull_request": None,
        "workflow_status": "failed",
    }


if __name__ == "__main__":
    sample_issue = {
        "title": "Autonomous bug resolver workflow orchestration",
        "body": "Verify that the agent workflow executes seamlessly without manual intervention.",
        "number": 1,
    }
    result = run_agent_workflow(
        issue_title=sample_issue["title"],
        issue_body=sample_issue["body"],
        issue_number=sample_issue["number"],
        repo_path=".",
    )
    print(json.dumps(result, indent=2))