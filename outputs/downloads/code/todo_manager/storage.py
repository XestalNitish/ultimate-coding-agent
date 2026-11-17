from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pydantic
from pydantic import BaseModel, Field

from models import TodoItem


class TodoStorage:
    """
    JSON-based persistence engine with atomic writes and thread-safe CRUD operations.
    """

    def __init__(self, storage_path: str = "todos.json") -> None:
        self.storage_path = Path(storage_path)
        self._lock = threading.RLock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Initializes the JSON storage file if it does not exist."""
        if not self.storage_path.exists():
            self.storage_path.write_text("[]", encoding="utf-8")

    def _load_raw(self) -> List[Dict[str, Any]]:
        """Loads raw data from the JSON file."""
        try:
            with self._lock:
                if not self.storage_path.exists():
                    return []
                return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_raw(self, data: List[Dict[str, Any]]) -> None:
        """Saves raw data to the JSON file atomically."""
        with self._lock:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".tmp",
                delete=False,
                encoding="utf-8",
            ) as tmp_file:
                json.dump(data, tmp_file, ensure_ascii=False, indent=2)
                tmp_path = tmp_file.name
                try:
                    os.replace(tmp_path, self.storage_path)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

    def load_todos(self) -> List[dict]:
        """Loads all todos from the JSON storage file."""
        with self._lock:
            raw_data = self._load_raw()
            return [item for item in raw_data if isinstance(item, dict)]

    def save_todos(self, todos: List[dict]) -> None:
        """Saves the provided list of todo dictionaries to the storage file."""
        with self._lock:
            self._save_raw(todos)

    def add_todo(
        self,
        title: str,
        priority: str = "Medium",
        tag: str = "General",
        due_date: Optional[str] = None,
    ) -> dict:
        """Adds a new todo item to the storage and returns the created dict."""
        with self._lock:
            raw_data = self._load_raw()
            max_id = max((int(item.get("id", 0)) for item in raw_data), default=0)
            new_id = max_id + 1
            created_at = datetime.utcnow().isoformat()
            new_todo = {
                "id": new_id,
                "title": title,
                "description": "",
                "status": "pending",
                "priority": priority,
                "tag": tag,
                "due_date": due_date,
                "created_at": created_at,
            }
            raw_data.append(new_todo)
            self._save_raw(raw_data)
            return new_todo

    def update_status(self, todo_id: int, status: str) -> bool:
        """Updates the status of a todo item. Returns True if updated."""
        with self._lock:
            raw_data = self._load_raw()
            for item in raw_data:
                if isinstance(item, dict) and item.get("id") == todo_id:
                    item["status"] = status
                    self._save_raw(raw_data)
                    return True
            return False

    def delete_todo(self, todo_id: int) -> bool:
        """Deletes a todo item by ID. Returns True if deleted."""
        with self._lock:
            raw_data = self._load_raw()
            new_data = [item for item in raw_data if not (isinstance(item, dict) and item.get("id") == todo_id)]
            self._save_raw(new_data)
            return len(new_data) < len(raw_data)

    def get_stats(self) -> dict:
        """Returns statistics for the current todo list."""
        with self._lock:
            raw_data = self._load_raw()
            total = len(raw_data)
            pending = sum(1 for item in raw_data if isinstance(item, dict) and item.get("status") == "pending")
            completed = total - pending
            return {
                "total": total,
                "pending": pending,
                "completed": completed,
            }


# Module-level singleton instance
storage = TodoStorage()


def load_todos() -> List[dict]:
    """Loads all todos from the global storage instance."""
    return storage.load_todos()


def save_todos(todos: List[dict]) -> None:
    """Saves todos to the global storage instance."""
    storage.save_todos(todos)


def add_todo(
    title: str,
    priority: str = "Medium",
    tag: str = "General",
    due_date: Optional[str] = None,
) -> dict:
    """Adds a todo to the global storage instance and returns the created dict."""
    return storage.add_todo(title, priority, tag, due_date)


def update_status(todo_id: int, status: str) -> bool:
    """Updates the status of a todo in the global storage instance."""
    return storage.update_status(todo_id, status)


def delete_todo(todo_id: int) -> bool:
    """Deletes a todo from the global storage instance."""
    return storage.delete_todo(todo_id)


def get_stats() -> dict:
    """Returns statistics from the global storage instance."""
    return storage.get_stats()