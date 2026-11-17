import os
import shutil
import tempfile
import numpy as np
from pathlib import Path
import pytest
from concurrent.futures import ThreadPoolExecutor

import pipeline
import rag
from rag import VectorStore


def test_scenario_5_pipeline_notes_persistence(tmp_path):
    """Verify that finalize step writes pipeline metadata into _pipeline_notes."""
    out_dir = str(tmp_path / "notes_project")
    state = {
        "user_input": "Test task",
        "spec": "# Test Spec\n1. Requirement A\n",
        "doc_context": "# Doc Notes\nFastAPI 0.115\n",
        "research": "# Research\nLatest specs\n",
        "best": {
            "status": "success",
            "files": {"main.py": "print('ok')\n"},
            "file_path": "main.py",
            "output_dir": out_dir,
        },
    }
    res = pipeline.finalize(state)
    notes_dir = Path(out_dir) / "_pipeline_notes"
    assert notes_dir.exists(), "_pipeline_notes directory was not created"
    assert (notes_dir / "spec.md").exists()
    assert (notes_dir / "docs_notes.md").exists()
    assert (notes_dir / "research.md").exists()


def test_scenario_5_vector_store_persistence(tmp_path):
    """Verify VectorStore state and vectors are incrementally saved and reloaded."""
    store_file = tmp_path / "test_store.pkl"
    store1 = VectorStore(store_file)
    chunks1 = [{"text": "Chunk 1", "library": "lib1", "source": "f1.pdf"}]
    vecs1 = np.ones((1, 384), dtype="float32")
    store1.add(chunks1, vecs1)
    store1.save()

    assert store_file.exists()

    # Load store in another instance and verify data integrity
    store2 = VectorStore.load(store_file)
    assert len(store2.chunks) == 1
    assert store2.libraries() == ["lib1"]
    assert store2.vecs.shape == (1, 384)

    # Add second chunk
    chunks2 = [{"text": "Chunk 2", "library": "lib2", "source": "f2.pdf"}]
    vecs2 = np.zeros((1, 384), dtype="float32")
    store2.add(chunks2, vecs2)
    store2.save()

    store3 = VectorStore.load(store_file)
    assert len(store3.chunks) == 2
    assert "lib2" in store3.libraries()


def test_scenario_5_concurrent_pipeline_directory_isolation(tmp_path):
    """Verify concurrent pipeline executions do not clash or overwrite files."""
    os.environ["MOCK_LLM"] = "1"

    def run_isolated(task_idx):
        target_dir = str(tmp_path / f"isolated_run_{task_idx}")
        return pipeline.run_pipeline(
            user_input=f"Task {task_idx}",
            research="off",
            output_dir=target_dir,
        )

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(run_isolated, i) for i in range(3)]
            results = [f.result() for f in futures]

        dirs = [r["out_dir"] for r in results]
        assert len(dirs) == 3
        assert len(set(dirs)) == 3, "Output directories clashed between concurrent runs!"
        for d in dirs:
            assert Path(d).exists()
    finally:
        os.environ.pop("MOCK_LLM", None)
