from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TodoItem(BaseModel):
    id: int
    title: str
    description: Optional[str] = ""
    status: str = Field(default="pending")
    priority: str = Field(default="Medium")
    tag: str = Field(default="General")
    due_date: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TodoItem":
        return cls(**data)


class TodoStorage:
    def __init__(self, storage_path: str = "todos.json") -> None:
        self.storage_path = storage_path
        self._lock = threading.RLock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not os.path.exists(self.storage_path):
            self._write_todos([])

    def _read_raw(self) -> List[Dict[str, Any]]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_raw(self, todos: List[Dict[str, Any]]) -> None:
        with self._lock:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=os.path.dirname(os.path.abspath(self.storage_path)) or ".",
                delete=False,
            ) as tmp:
                json.dump(todos, tmp, ensure_ascii=False, indent=2)
                tmp_path = tmp.name
            try:
                os.replace(tmp_path, self.storage_path)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

    def load_todos(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._read_raw()

    def save_todos(self, todos: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._write_raw(todos)

    def add_todo(
        self,
        title: str,
        priority: str = "Medium",
        tag: str = "General",
        due_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            todos = self.load_todos()
            new_id = max((t.get("id", 0) for t in todos), default=0) + 1
            new_todo = {
                "id": new_id,
                "title": title,
                "description": "",
                "status": "pending",
                "priority": priority,
                "tag": tag,
                "due_date": due_date,
                "created_at": datetime.utcnow().isoformat(),
            }
            todos.append(new_todo)
            self.save_todos(todos)
            return new_todo

    def update_status(self, todo_id: int, status: str) -> bool:
        with self._lock:
            todos = self.load_todos()
            for todo in todos:
                if todo.get("id") == todo_id:
                    if status not in ("pending", "in_progress", "completed"):
                        return False
                    todo["status"] = status
                    self.save_todos(todos)
                    return True
            return False

    def delete_todo(self, todo_id: int) -> bool:
        with self._lock:
            todos = self.load_todos()
            remaining = [t for t in todos if t.get("id") != todo_id]
            if len(remaining) == len(todos):
                return False
            self.save_todos(remaining)
            return True

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            todos = self.load_todos()
            total = len(todos)
            pending = sum(1 for t in todos if t.get("status") == "pending")
            completed = sum(1 for t in todos if t.get("status") == "completed")
            return {
                "total": total,
                "pending": pending,
                "completed": completed,
                "completion_rate": round((completed / total * 100) if total else 0.0, 2),
            }


def load_todos(storage_path: str = "todos.json") -> List[Dict[str, Any]]:
    storage = TodoStorage(storage_path)
    return storage.load_todos()


def save_todos(todos: List[Dict[str, Any]], storage_path: str = "todos.json") -> None:
    storage = TodoStorage(storage_path)
    storage.save_todos(todos)


def add_todo(
    title: str,
    priority: str = "Medium",
    tag: str = "General",
    due_date: Optional[str] = None,
    storage_path: str = "todos.json",
) -> Dict[str, Any]:
    storage = TodoStorage(storage_path)
    return storage.add_todo(title, priority, tag, due_date)


def update_status(todo_id: int, status: str, storage_path: str = "todos.json") -> bool:
    storage = TodoStorage(storage_path)
    return storage.update_status(todo_id, status)


def delete_todo(todo_id: int, storage_path: str = "todos.json") -> bool:
    storage = TodoStorage(storage_path)
    return storage.delete_todo(todo_id)


def get_stats(storage_path: str = "todos.json") -> Dict[str, Any]:
    storage = TodoStorage(storage_path)
    return storage.get_stats()