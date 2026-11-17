import os
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path
import pytest
from unittest.mock import patch

import pipeline
from coder.code_dev import run_code_dev_task


def test_scenario_1_happy_path_code_dev(tmp_path):
    """Scenario 1A: End-to-end happy path for multi-file code dev task."""
    out_dir = str(tmp_path / "happy_project")
    
    task_desc = "Create a statistics module `calc/stats.py` with `mean(nums)` and `main.py` that tests it."
    spec_json = """{
        "project_name": "stats_calculator",
        "needs_docs": false,
        "entry_point": "main.py",
        "run_mode": "script",
        "synthesized_spec": "Clean calculator module with entry point test",
        "files": [
            {
                "path": "calc/stats.py",
                "purpose": "Provide mean calculation",
                "exports": ["mean"],
                "depends_on": []
            },
            {
                "path": "main.py",
                "purpose": "Test mean calculation",
                "exports": [],
                "depends_on": ["calc/stats.py"]
            }
        ],
        "dependencies": []
    }"""
    stats_code = "def mean(nums: list[float]) -> float:\n    return sum(nums) / len(nums) if nums else 0.0\n"
    main_code = (
        "from calc.stats import mean\n\n"
        "if __name__ == '__main__':\n"
        "    data = [10.0, 20.0, 30.0]\n"
        "    res = mean(data)\n"
        "    assert res == 20.0, f'Expected 20.0, got {res}'\n"
        "    print(f'CALCULATED_MEAN={res}')\n"
    )

    responses = iter([spec_json, stats_code, main_code])

    def mock_llm_text(*args, **kwargs):
        return next(responses)

    with patch("coder.code_dev._llm_text", side_effect=mock_llm_text):
        result = run_code_dev_task(
            task=task_desc,
            language="python",
            output_dir=out_dir,
        )

    # 1. Check status and output
    assert result["status"] == "success", f"Task failed: {result.get('error')}"
    assert "calc/stats.py" in result["files"]
    assert "main.py" in result["files"]
    assert "calc/__init__.py" in result["files"]

    # 2. Verify files written to disk
    main_disk = Path(out_dir) / "main.py"
    stats_disk = Path(out_dir) / "calc" / "stats.py"
    assert main_disk.exists(), "main.py was not saved to disk"
    assert stats_disk.exists(), "calc/stats.py was not saved to disk"

    # 3. Execute entry point independently to prove execution soundness
    proc = subprocess.run(
        [sys.executable, str(main_disk)],
        cwd=out_dir,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"Generated code failed execution: {proc.stderr}"
    assert "CALCULATED_MEAN=20.0" in proc.stdout


def test_scenario_1_happy_path_full_pipeline(tmp_path):
    """Scenario 1B: Unified pipeline run from intake to finalize."""
    out_dir = str(tmp_path / "pipeline_project")
    task_desc = "Write a python script that returns factorial of a number."

    os.environ["MOCK_LLM"] = "1"
    try:
        result = pipeline.run_pipeline(
            user_input=task_desc,
            language="python",
            research="off",
            output_dir=out_dir,
        )
        assert result.get("ok") is True or result.get("status") in ("success", "partial")
        assert Path(result.get("out_dir", out_dir)).exists()
    finally:
        os.environ.pop("MOCK_LLM", None)
