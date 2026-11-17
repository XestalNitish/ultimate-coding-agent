import os
import pytest
from unittest.mock import patch, MagicMock
import requests

import pipeline
from coder.code_dev import run_code_dev_task, _llm_text
from rag.retriever import hybrid_search, RAGAgent


def test_scenario_3_llm_network_failure_fallback(tmp_path):
    """Test that when writer LLM raises ConnectionError, system falls back or fails gracefully."""
    out_dir = str(tmp_path / "fail_project")
    
    def simulate_connection_failure(*args, **kwargs):
        raise requests.ConnectionError("Connection refused: 127.0.0.1:8084")

    with patch("coder.code_dev._llm_text", side_effect=simulate_connection_failure):
        result = run_code_dev_task(
            task="Build a web scraper",
            output_dir=out_dir,
            max_iterations=1,
        )

    # Fail-soft: system must return structured error dict, never uncaught crash
    assert result["status"] in ("failed", "error")
    assert result.get("error") is not None or "Connection refused" in str(result.get("reply"))


def test_scenario_3_garbage_json_from_planner(tmp_path):
    """Test that when the planner returns malformed non-JSON, fallback single-file plan activates."""
    out_dir = str(tmp_path / "garbage_plan_project")

    fallback_code = (
        "def main():\n"
        "    print('Fallback executed successfully')\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    responses = iter([
        "NOT_JSON_AT_ALL! Just some broken raw text...",  # Malformed planner output
        fallback_code,  # Fallback code
    ])

    def mock_llm_text(*args, **kwargs):
        try:
            return next(responses)
        except StopIteration:
            return fallback_code

    with patch("coder.code_dev._llm_text", side_effect=mock_llm_text):
        result = run_code_dev_task(
            task="Create a simple printer function",
            output_dir=out_dir,
            max_iterations=1,
        )

    # Verifies fallback plan took over and produced the entry point
    assert "main.py" in result["files"]
    assert result["status"] == "success"


def test_scenario_3_rag_store_missing_fallback():
    """Test that hybrid_search falls back to standard search without crash when DB is missing."""
    docs = hybrid_search("test query", workspace_id="non_existent_workspace_999")
    # Must return a list (empty or fallback), never raise an unhandled exception
    assert isinstance(docs, list)
