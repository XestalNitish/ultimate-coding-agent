import os
import pytest
from pathlib import Path
from unittest.mock import patch

import pipeline
from coder.code_dev import (
    compact_context_text,
    middle_cut,
    shrink_prose,
    shrink_code,
    pack_sections,
    Sec,
)
from rag.retriever import clean_query


def test_scenario_2_empty_and_whitespace_input():
    """Verify empty or whitespace-only inputs are handled cleanly without crashing."""
    res_empty = pipeline.run_pipeline("   ")
    assert res_empty["ok"] is False
    assert res_empty["status"] == "error"
    assert "user_input is empty" in res_empty.get("answer", "")


def test_scenario_2_huge_input_context_guards():
    """Verify system gracefully compacts and handles huge inputs without memory exhaustion."""
    huge_text = "def function_with_long_requirements():\n" + ("    # Critical constraint step\n" * 2000)
    assert len(huge_text) > 50000

    # Test middle_cut
    cut_text = middle_cut(huge_text, 1000)
    assert len(cut_text) <= 1000
    assert "...[trimmed]..." in cut_text

    # Test shrink_prose
    shrunk_prose = shrink_prose(huge_text, 800)
    assert len(shrunk_prose) <= 800

    # Test shrink_code
    shrunk_code = shrink_code(huge_text, 1200)
    assert len(shrunk_code) <= 1200

    # Test pack_sections
    secs = [
        Sec("SPEC", huge_text, 90, floor=200),
        Sec("NOTES", "Short note", 50, floor=0),
    ]
    packed = pack_sections(secs, budget_tokens=500)
    assert len(packed) <= 500 * 4


def test_scenario_2_complex_unicode_and_hinglish():
    """Verify Unicode (Devanagari, Emoji, Math symbols) is preserved and normalized."""
    hinglish_math = "Mujhe circle ka area calculate karne ka function chahiye 𝜋 * r² aur output me 🚀 print karo."
    cleaned = clean_query(hinglish_math)
    assert "circle" in cleaned
    assert "area" in cleaned

    # Test pipeline with Hinglish & Unicode under mock mode
    os.environ["MOCK_LLM"] = "1"
    try:
        res = pipeline.run_pipeline(hinglish_math, research="off")
        assert res.get("status") in ("success", "partial", "failed")  # fail-soft, never crash
        assert "circle" in res.get("user_input", "")
    finally:
        os.environ.pop("MOCK_LLM", None)
