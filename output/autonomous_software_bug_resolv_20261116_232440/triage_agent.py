"""Triage Agent: Analyzes GitHub issues and performs code search/embeddings to identify relevant files."""

import json
import re
from typing import Any, Dict, List, Optional


class TriageAgent:
    """Analyzes GitHub issues and identifies relevant code files via code search and embeddings."""

    def __init__(self, repo_path: str, token: Optional[str] = None) -> None:
        self.repo_path = repo_path
        self.token = token
        self._git_client = None

    def _get_git_client(self) -> Any:
        if self._git_client is None:
            try:
                from git_client import GitClient
            except Exception:
                raise RuntimeError("git_client module is not available")
            self._git_client = GitClient(self.repo_path, self.token)
        return self._git_client

    def analyze_issue(self, issue_title: str, issue_body: str, issue_number: Optional[int] = None) -> Dict[str, Any]:
        """Analyze a GitHub issue and return relevant files, search results, and extracted context."""
        git = self._get_git_client()
        relevant_files: List[str] = []
        search_results: List[Dict[str, Any]] = []
        extracted_context: Dict[str, Any] = {
            "title": issue_title,
            "body": issue_body,
            "issue_number": issue_number,
            "relevant_files": relevant_files,
            "search_results": search_results,
            "summary": "",
        }

        try:
            git.checkout(ref="main" if git.get_branch_list() else "master")
            file_list = git.list_files()
            relevant_files = self._search_relevant_files(file_list, issue_title, issue_body)
            search_results = self._perform_code_search(relevant_files, issue_title, issue_body)
            extracted_context["summary"] = self._build_summary(issue_title, issue_body, relevant_files)
        except Exception as exc:
            extracted_context["error"] = str(exc)

        return extracted_context

    def _search_relevant_files(self, file_list: List[str], title: str, body: str) -> List[str]:
        """Identify relevant files by keyword matching and code structure heuristics."""
        keywords = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", title)
        keywords.extend(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", body))
        keywords = list(set(keywords))
        if not keywords:
            keywords = ["file", "code", "bug", "fix"]

        relevant: List[str] = []
        for path in file_list:
            if any(keyword in path for keyword in keywords):
                relevant.append(path)
        return relevant[:20]

    def _perform_code_search(self, files: List[str], title: str, body: str) -> List[Dict[str, Any]]:
        """Perform lightweight code search using file content and keyword matching."""
        results: List[Dict[str, Any]] = []
        try:
            git = self._get_git_client()
            for path in files:
                try:
                    content = git.get_file_content(path)
                except Exception:
                    continue
                matches = [keyword for keyword in keywords if keyword in content]
                if matches:
                    results.append({
                        "file": path,
                        "matches": matches,
                        "snippet": self._extract_snippet(content, matches[0]),
                    })
        except Exception as exc:
            results.append({"error": str(exc)})
        return results

    def _extract_snippet(self, content: str, keyword: str, max_len: int = 200) -> str:
        """Extract a short snippet around the keyword from file content."""
        idx = content.find(keyword)
        if idx == -1:
            return ""
        start = max(0, idx - max_len // 2)
        end = min(len(content), idx + len(keyword) + max_len // 2)
        return content[start:end].strip()

    def _build_summary(self, title: str, body: str, files: List[str]) -> str:
        """Build a concise summary of the triage analysis."""
        return f"Analyzed issue '{title}'. Identified {len(files)} relevant files: {', '.join(files[:5])}"


def analyze_issue(issue_title: str, issue_body: str, issue_number: Optional[int] = None, repo_path: str = ".") -> Dict[str, Any]:
    """Entry point to analyze a GitHub issue and return relevant files."""
    agent = TriageAgent(repo_path=repo_path)
    return agent.analyze_issue(issue_title, issue_body, issue_number)


if __name__ == "__main__":
    sample = analyze_issue("Fix null pointer in user service", "Null pointer error occurs when user is None.", 123)
    print(json.dumps(sample, indent=2))