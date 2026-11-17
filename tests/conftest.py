import os
import sys
import shutil
import tempfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as C

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Ensure tests run cleanly with isolated outputs."""
    try:
        from coder.code_dev import set_doc_retriever
        set_doc_retriever(None)
    except Exception:
        pass
    temp_dir = tempfile.mkdtemp(prefix="agent_test_")
    monkeypatch.setenv("AGENT_WORKSPACE", temp_dir)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
    try:
        from coder.code_dev import set_doc_retriever
        set_doc_retriever(None)
    except Exception:
        pass
