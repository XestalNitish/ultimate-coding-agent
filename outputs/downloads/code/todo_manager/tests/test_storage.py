from typing import List, Optional

import pytest
from pydantic import BaseModel, Field

from models import TodoItem
from storage import TodoStorage


@pytest.fixture
def storage(tmp_path):
    """Isolated storage instance for testing."""
    return TodoStorage(storage_path=str(tmp_path / "test_todos.json"))


def test_add_todo(storage):
    """Validates add_todo creates a new item with default values."""
    result = storage.add_todo(title="Test Task", priority="High", tag="Work")
    
    assert isinstance(result, dict)
    assert result["id"] == 1
    assert result["title"] == "Test Task"
    assert result["priority"] == "High"
    assert result["tag"] == "Work"
    assert result["status"] == "pending"
    assert result["created_at"] is not None


def test_add_todo_with_due_date(storage):
    """Validates add_todo correctly handles due_date parameter."""
    result = storage.add_todo(title="Due Task", due_date="2023-12-31")
    
    assert result["due_date"] == "2023-12-31"
    assert result["status"] == "pending"


def test_update_status(storage):
    """Validates update_status changes the status of an existing item."""
    todo = storage.add_todo(title="Update Task")
    
    assert storage.update_status(todo["id"], "in_progress") is True
    assert storage.get_todos()[todo["id"]]["status"] == "in_progress"
    
    assert storage.update_status(todo["id"], "completed") is True
    assert storage.get_todos()[todo["id"]]["status"] == "completed"


def test_update_status_invalid_id(storage):
    """Validates update_status returns False for non-existent IDs."""
    assert storage.update_status(999, "completed") is False


def test_delete_todo(storage):
    """Validates delete_todo removes an item and returns True."""
    todo = storage.add_todo(title="Delete Me")
    
    assert storage.delete_todo(todo["id"]) is True
    assert storage.get_todos() == []
    
    assert storage.delete_todo(todo["id"]) is False


def test_get_stats(storage):
    """Validates get_stats returns correct counts for the current state."""
    storage.add_todo(title="Pending 1")
    storage.add_todo(title="Pending 2")
    storage.add_todo(title="Completed 1", status="completed")
    
    stats = storage.get_stats()
    
    assert stats["total"] == 3
    assert stats["pending"] == 2
    assert stats["completed"] == 1


def test_load_and_save_todos(storage):
    """Validates load_todos and save_todos round-trip correctly."""
    initial = [{"id": 1, "title": "Initial", "status": "pending"}]
    storage.save_todos(initial)
    
    loaded = storage.load_todos()
    
    assert loaded == initial


def test_load_todos_empty(storage):
    """Validates load_todos returns empty list when no data exists."""
    assert storage.load_todos() == []