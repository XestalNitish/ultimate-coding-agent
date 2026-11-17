"""
tests/test_checkpoint.py - Comprehensive tests for state persistence and checkpoint manager.
"""

import os
os.environ["MOCK_LLM"] = "1"

import json
from pathlib import Path
import shutil
import pytest

import checkpoint_manager as cm
from pipeline import intake, researcher, mediator, planner


@pytest.fixture(autouse=True)
def clean_checkpoints(tmp_path, monkeypatch):
    """Use a temporary checkpoint directory for isolated testing."""
    test_cp_dir = tmp_path / ".checkpoints"
    monkeypatch.setattr(cm, "CHECKPOINT_DIR", test_cp_dir)
    monkeypatch.setattr(cm, "ACTIVE_FILE", test_cp_dir / "active_session.json")
    monkeypatch.setattr(cm, "HISTORY_DIR", test_cp_dir / "history")
    cm.init_dirs()
    yield
    if test_cp_dir.exists():
        shutil.rmtree(test_cp_dir, ignore_errors=True)


def test_save_and_get_active_checkpoint():
    assert cm.get_active_checkpoint() is None

    sid = cm.save_checkpoint(
        task="Test Task: Build a calculator",
        stage="planner",
        pipeline_state={"spec": "Calculator spec", "plan": {"summary": "calc"}},
        coder_state={"files": {"calc.py": "def add(a, b): return a + b"}},
        description="Completed planner node",
    )

    cp = cm.get_active_checkpoint()
    assert cp is not None
    assert cp["session_id"] == sid
    assert cp["task"] == "Test Task: Build a calculator"
    assert cp["stage"] == "planner"
    assert cp["files_count"] == 1
    assert "calc.py" in cp["file_names"]
    assert cp["coder_state"]["files"]["calc.py"] == "def add(a, b): return a + b"
    assert cp["status"] == "in_progress"


def test_mark_interrupted():
    cm.save_checkpoint(
        task="Test interrupted task",
        stage="coder:writer",
        status="in_progress",
    )
    cm.mark_interrupted()

    cp = cm.get_active_checkpoint()
    assert cp is not None
    assert cp["status"] == "interrupted"
    assert "interrupted_at" in cp


def test_mark_completed_archives_and_cleans():
    sid = cm.save_checkpoint(
        task="Test completed task",
        stage="finalize",
        status="in_progress",
    )
    assert cm.get_active_checkpoint() is not None

    cm.mark_completed(final_output="SUCCESS: Task done")
    assert cm.get_active_checkpoint() is None

    # Verify archived in history
    archived = list(cm.HISTORY_DIR.glob(f"*{sid}*.json"))
    assert len(archived) >= 1
    data = json.loads(archived[0].read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert "SUCCESS" in data["final_output"]


def test_discard_active_checkpoint():
    cm.save_checkpoint(
        task="Task to discard",
        stage="coder",
        status="in_progress",
    )
    assert cm.get_active_checkpoint() is not None

    cm.discard_active_checkpoint()
    assert cm.get_active_checkpoint() is None

    # Verify archived as discarded
    discarded = list(cm.HISTORY_DIR.glob("*discarded*.json"))
    assert len(discarded) >= 1


def test_prompt_resume_flags():
    cm.save_checkpoint(
        task="Test flags task",
        stage="coder:debugger",
        coder_state={"files": {"app.py": "print('hello')"}},
    )

    # Force resume returns checkpoint without interactive input prompt
    res = cm.prompt_resume_if_available(force_resume=True)
    assert res is not None
    assert res["stage"] == "coder:debugger"

    # Force fresh discards checkpoint and returns None
    fresh = cm.prompt_resume_if_available(force_fresh=True)
    assert fresh is None
    assert cm.get_active_checkpoint() is None


def test_intake_node_preserves_resumed_state():
    state = {
        "user_input": "Build voice assistant",
        "resumed": True,
        "language": "python",
        "research": "Existing research content",
        "research_digest": "Digest 123",
        "spec": "Spec XYZ",
        "plan": {"summary": "Voice assistant"},
        "files": {"voice_agent.py": "# saved code"},
        "out_dir": "workspace/saved_run",
    }
    result = intake(state)
    assert result["user_input"] == "Build voice assistant"
    assert result["research"] == "Existing research content"
    assert result["research_digest"] == "Digest 123"
    assert result["spec"] == "Spec XYZ"
    assert "voice_agent.py" in result["files"]
    assert "Resumed from saved checkpoint" in result["notes"]


def test_researcher_node_skips_when_research_present():
    state = {
        "user_input": "Build voice assistant",
        "research": "Pre-computed research",
        "research_digest": "Pre-computed digest",
    }
    result = researcher(state)
    assert "notes" in result
    assert "research: reused from checkpoint" in result["notes"]


def test_mediator_node_skips_when_docs_present():
    state = {
        "user_input": "Build voice assistant",
        "resumed": True,
        "doc_context": "Pre-loaded official docs for sounddevice and winsound",
    }
    result = mediator(state)
    assert result["rag_available"] is True
    assert result["needs_rag"] is False
    assert result["questions"] == []


def test_planner_node_skips_when_plan_and_spec_present():
    state = {
        "user_input": "Build voice assistant",
        "resumed": True,
        "spec": "PRESERVED SPEC",
        "plan": {"summary": "Voice plan"},
    }
    result = planner(state)
    assert result["spec"] == "PRESERVED SPEC"
    assert result["plan"]["summary"] == "Voice plan"
    assert "plan: reused from checkpoint" in result["notes"]
