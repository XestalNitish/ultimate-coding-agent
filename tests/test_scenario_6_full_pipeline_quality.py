import os
import ast
import subprocess
import sys
from pathlib import Path
import pytest
from unittest.mock import patch

from coder.code_dev import run_code_dev_task, validate_content


def test_scenario_6_multi_file_quality_and_clean_execution(tmp_path):
    """Scenario 6: Verify full-pipeline output quality, stub-free code, and multi-file coherence."""
    out_dir = str(tmp_path / "quality_project")

    spec_json = """{
        "project_name": "inventory_system",
        "needs_docs": false,
        "entry_point": "main.py",
        "run_mode": "script",
        "synthesized_spec": "Modular inventory manager with in-memory storage and validation",
        "files": [
            {
                "path": "models/item.py",
                "purpose": "Define Item data container",
                "exports": ["Item"],
                "depends_on": []
            },
            {
                "path": "services/store.py",
                "purpose": "Inventory CRUD operations",
                "exports": ["InventoryStore"],
                "depends_on": ["models/item.py"]
            },
            {
                "path": "main.py",
                "purpose": "Run end-to-end integration test",
                "exports": [],
                "depends_on": ["services/store.py", "models/item.py"]
            }
        ],
        "dependencies": []
    }"""

    item_code = (
        "class Item:\n"
        "    def __init__(self, name: str, quantity: int, price: float):\n"
        "        if quantity < 0 or price < 0:\n"
        "            raise ValueError('Invalid item attributes')\n"
        "        self.name = name\n"
        "        self.quantity = quantity\n"
        "        self.price = price\n\n"
        "    def total_value(self) -> float:\n"
        "        return self.quantity * self.price\n"
    )

    store_code = (
        "from models.item import Item\n\n"
        "class InventoryStore:\n"
        "    def __init__(self):\n"
        "        self._items = {}\n\n"
        "    def add_item(self, item: Item) -> None:\n"
        "        self._items[item.name] = item\n\n"
        "    def get_total_inventory_value(self) -> float:\n"
        "        return sum(item.total_value() for item in self._items.values())\n"
    )

    main_code = (
        "from models.item import Item\n"
        "from services.store import InventoryStore\n\n"
        "if __name__ == '__main__':\n"
        "    store = InventoryStore()\n"
        "    store.add_item(Item('Widget', 10, 5.0))\n"
        "    store.add_item(Item('Gadget', 2, 25.0))\n"
        "    val = store.get_total_inventory_value()\n"
        "    assert val == 100.0, f'Expected 100.0, got {val}'\n"
        "    print(f'INVENTORY_AUDIT_PASS: total={val}')\n"
    )

    responses = iter([spec_json, item_code, store_code, main_code])

    def mock_llm_text(*args, **kwargs):
        return next(responses)

    with patch("coder.code_dev._llm_text", side_effect=mock_llm_text):
        result = run_code_dev_task(
            task="Build a modular Python inventory management system with assertions",
            output_dir=out_dir,
            max_iterations=1,
        )

    # 1. Output Quality: Success status and full file creation
    assert result["status"] == "success", f"Pipeline failed: {result.get('error')}"
    files = result["files"]
    assert "models/item.py" in files
    assert "services/store.py" in files
    assert "main.py" in files
    assert "models/__init__.py" in files
    assert "services/__init__.py" in files

    # 2. Code Quality: AST Syntax Verification & Stub check
    for path, code in files.items():
        tree = ast.parse(code)
        assert tree is not None
        val_err = validate_content(path, code)
        assert val_err is None, f"Code quality error in {path}: {val_err}"

    # 3. Execution Soundness: Run generated code in clean subprocess
    main_file = Path(out_dir) / "main.py"
    proc = subprocess.run(
        [sys.executable, str(main_file)],
        cwd=out_dir,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"Execution failed: {proc.stderr}"
    assert "INVENTORY_AUDIT_PASS: total=100.0" in proc.stdout
