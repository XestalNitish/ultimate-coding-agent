"""Git API client for repository state and codebase interactions."""

import os
import subprocess
from typing import Any, Dict, List, Optional

try:
    from gitpython import Repo
except ImportError:  # pragma: no cover
    Repo = None


class GitClient:
    """Handles all codebase and repository state interactions via the Git API."""

    def __init__(self, repo_path: str, token: Optional[str] = None) -> None:
        self.repo_path = repo_path
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self._repo: Optional[Repo] = None

    def _ensure_repo(self) -> Repo:
        if Repo is None:
            raise RuntimeError("gitpython is not installed; install via requirements.txt")
        if self._repo is None:
            self._repo = Repo(self.repo_path)
        return self._repo

    def clone_repo(self, remote_url: str, dest_path: Optional[str] = None) -> str:
        """Clone a repository into the destination path and return the path."""
        if Repo is None:
            raise RuntimeError("gitpython is not installed; install via requirements.txt")
        dest = dest_path or os.path.join(self.repo_path, "repo")
        if os.path.exists(dest) and os.listdir(dest):
            raise RuntimeError(f"Destination already exists: {dest}")
        subprocess.run(
            ["git", "clone", "--depth", "1", remote_url, dest],
            check=True,
            capture_output=True,
        )
        return dest

    def checkout(self, ref: str) -> None:
        """Checkout a specific git ref (branch, tag, or commit) in the repository."""
        repo = self._ensure_repo()
        repo.checkout(ref)

    def commit(self, message: str, files: Optional[List[str]] = None) -> str:
        """Commit staged changes with the given message and return the commit hash."""
        repo = self._ensure_repo()
        if files:
            repo.add(*files)
        repo.commit(message)
        return repo.head.commit.hexsha

    def pull_request(self, title: str, body: str, base: str, head: str) -> Dict[str, Any]:
        """Create an automated pull request and return its metadata."""
        if Repo is None:
            raise RuntimeError("gitpython is not installed; install via requirements.txt")
        repo = self._ensure_repo()
        payload = {
            "title": title,
            "body": body,
            "base": base,
            "head": head,
        }
        resp = repo.create_pull(
            title=title,
            body=body,
            base=base,
            head=head,
        )
        return {
            "url": resp.pull_request_url,
            "number": resp.pull_request_number,
            "state": resp.pull_request_state,
        }

    def get_file_content(self, file_path: str) -> str:
        """Return the raw content of a file in the repository."""
        repo = self._ensure_repo()
        return repo.repo_path.joinpath(file_path).read_text(encoding="utf-8")

    def list_files(self, path: Optional[str] = None) -> List[str]:
        """List files in the repository (optionally scoped to a directory)."""
        repo = self._ensure_repo()
        if path is None:
            return [str(p.relative_to(repo.repo_path)) for p in repo.repo_path.rglob("*") if p.is_file()]
        return [str(p.relative_to(repo.repo_path)) for p in repo.repo_path.joinpath(path).rglob("*") if p.is_file()]

    def get_branch_list(self) -> List[str]:
        """Return the list of available git branches."""
        repo = self._ensure_repo()
        return [b.name for b in repo.branches]

    def get_head_commit(self) -> str:
        """Return the current HEAD commit hash."""
        repo = self._ensure_repo()
        return repo.head.commit.hexsha

    def get_status(self) -> Dict[str, Any]:
        """Return the current repository status summary."""
        repo = self._ensure_repo()
        return {
            "branch": str(repo.active_branch),
            "head": repo.head.commit.hexsha,
            "status": [str(s.path) for s in repo.status.dirty_files],
        }

    def resolve_ref(self, ref: str) -> str:
        """Resolve a git ref to its commit hash."""
        repo = self._ensure_repo()
        return str(repo.rev_parse(ref))

    def diff(self, ref: str, base: str) -> str:
        """Return the diff between two git refs."""
        repo = self._ensure_repo()
        return repo.rev_parse_diff(ref, base)

    def read_file(self, file_path: str) -> str:
        """Read a file from the repository working tree."""
        return self.get_file_content(file_path)

    def write_file(self, file_path: str, content: str) -> None:
        """Write content to a file in the repository working tree."""
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def __enter__(self) -> "GitClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def clone_repo(remote_url: str, dest_path: Optional[str] = None) -> str:
    """Clone a repository into the destination path and return the path."""
    client = GitClient(repo_path=dest_path or os.path.join(os.getcwd(), "repo"))
    return client.clone_repo(remote_url, dest_path)


def checkout(repo_path: str, ref: str) -> None:
    """Checkout a specific git ref in the repository."""
    GitClient(repo_path=repo_path).checkout(ref)


def commit(repo_path: str, message: str, files: Optional[List[str]] = None) -> str:
    """Commit staged changes with the given message and return the commit hash."""
    return GitClient(repo_path=repo_path).commit(message, files)


def pull_request(repo_path: str, title: str, body: str, base: str, head: str) -> Dict[str, Any]:
    """Create an automated pull request and return its metadata."""
    return GitClient(repo_path=repo_path).pull_request(title, body, base, head)


__all__ = [
    "GitClient",
    "clone_repo",
    "checkout",
    "commit",
    "pull_request",
]