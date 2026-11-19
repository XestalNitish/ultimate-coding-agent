"""Configuration, constants, and environment variables for the autonomous SWE-agent system."""

import os


def _load_env_variable(name: str, default: str = "") -> str:
    """Load an environment variable, falling back to the provided default."""
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else default


class Config:
    """Central configuration object for the agent workflow."""

    def __init__(self) -> None:
        self.REPO_PATH = _load_env_variable("REPO_PATH", "/default/repo")
        self.GITHUB_TOKEN = _load_env_variable("GITHUB_TOKEN", "")
        self.E2B_API_KEY = _load_env_variable("E2B_API_KEY", "")
        self.TEST_TIMEOUT = int(_load_env_variable("TEST_TIMEOUT", "120"))
        self.SANDBOX_IMAGE = _load_env_variable("SANDBOX_IMAGE", "python:3.11-slim")
        self.MAX_TRIAGE_FILES = int(_load_env_variable("MAX_TRIAGE_FILES", "20"))
        self.MAX_DEVELOPER_EDITS = int(_load_env_variable("MAX_DEVELOPER_EDITS", "5"))
        self.PR_DETAIL_LEVEL = _load_env_variable("PR_DETAIL_LEVEL", "full")

    def as_dict(self) -> dict:
        """Return the configuration as a dictionary for serialization."""
        return {
            "REPO_PATH": self.REPO_PATH,
            "GITHUB_TOKEN": self.GITHUB_TOKEN,
            "E2B_API_KEY": self.E2B_API_KEY,
            "TEST_TIMEOUT": self.TEST_TIMEOUT,
            "SANDBOX_IMAGE": self.SANDBOX_IMAGE,
            "MAX_TRIAGE_FILES": self.MAX_TRIAGE_FILES,
            "MAX_DEVELOPER_EDITS": self.MAX_DEVELOPER_EDITS,
            "PR_DETAIL_LEVEL": self.PR_DETAIL_LEVEL,
        }


REPO_PATH = Config().REPO_PATH
GITHUB_TOKEN = Config().GITHUB_TOKEN
E2B_API_KEY = Config().E2B_API_KEY
TEST_TIMEOUT = Config().TEST_TIMEOUT

__all__ = [
    "Config",
    "REPO_PATH",
    "GITHUB_TOKEN",
    "E2B_API_KEY",
    "TEST_TIMEOUT",
]