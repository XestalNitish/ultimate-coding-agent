import os
import sys
import argparse
import json
import subprocess
from typing import List, Optional

try:
    from pydantic import BaseModel, Field
    from datetime import datetime
except Exception:
    BaseModel = None
    Field = None
    datetime = None

try:
    from rich.console import Console
    from rich.table import Table
except Exception:
    Console = None
    Table = None

try:
    from ui import run_ui
except Exception:
    run_ui = None


def _get_storage_path() -> str:
    env_path = os.getenv("TASK_DATA_PATH", "todos.json")
    return env_path


def load_todos() -> List[dict]:
    path = _get_storage_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, IOError):
        return []


def save_todos(todos: List[dict]) -> None:
    path = _get_storage_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(todos, f, indent=2, ensure_ascii=False)


def add_todo(title: str, priority: str = "Medium", tag: str = "General", due_date: Optional[str] = None) -> dict:
    todos = load_todos()
    new_id = len(todos) + 1 if todos else 1
    new_todo = {
        "id": new_id,
        "title": title,
        "description": "",
        "status": "pending",
        "priority": priority,
        "tag": tag,
        "due_date": due_date,
        "created_at": datetime.utcnow().isoformat() if datetime else "",
    }
    todos.append(new_todo)
    save_todos(todos)
    return new_todo


def update_status(todo_id: int, status: str) -> bool:
    todos = load_todos()
    for todo in todos:
        if todo.get("id") == todo_id:
            todo["status"] = status
            save_todos(todos)
            return True
    return False


def delete_todo(todo_id: int) -> bool:
    todos = load_todos()
    filtered = [t for t in todos if t.get("id") != todo_id]
    if len(filtered) != len(todos):
        save_todos(filtered)
        return True
    return False


def get_stats() -> dict:
    todos = load_todos()
    total = len(todos)
    pending = sum(1 for t in todos if t.get("status") == "pending")
    completed = sum(1 for t in todos if t.get("status") == "completed")
    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "completion_rate": round((completed / total * 100), 2) if total > 0 else 0.0
    }


def _print_stats(stats: dict) -> None:
    if Console:
        console = Console()
        table = Table(title="Task Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Total Tasks", str(stats.get("total", 0)))
        table.add_row("Pending", str(stats.get("pending", 0)))
        table.add_row("Completed", str(stats.get("completed", 0)))
        table.add_row("Completion Rate", f"{stats.get('completion_rate', 0.0)}%")
        console.print(table)


def _print_list(todos: List[dict], status_filter: Optional[str] = None, tag_filter: Optional[str] = None) -> None:
    if not todos:
        if Console:
            Console.print("[yellow]No tasks found.[/yellow]")
        return

    filtered = todos
    if status_filter:
        filtered = [t for t in filtered if t.get("status") == status_filter]
    if tag_filter:
        filtered = [t for t in filtered if t.get("tag") == tag_filter]

    if Console:
        console = Console()
        table = Table(title="Task List")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Status", style="green" if filtered else "red")
        table.add_column("Priority", style="yellow")
        table.add_column("Tag", style="blue")
        for todo in filtered:
            table.add_row(
                str(todo.get("id", "")),
                str(todo.get("title", "")),
                str(todo.get("status", "")),
                str(todo.get("priority", "")),
                str(todo.get("tag", ""))
            )
        console.print(table)


def add(args: argparse.Namespace) -> int:
    title = args.title.strip()
    if not title:
        if Console:
            Console.print("[red]Error: Title cannot be empty.[/red]")
        return 1

    priority = args.priority or "Medium"
    tag = args.tag or "General"
    due_date = args.due or None

    new_todo = add_todo(title, priority, tag, due_date)
    if Console:
        Console.print(f"[green]Task added successfully.[/green] ID: {new_todo['id']}")
    return 0


def list(args: argparse.Namespace) -> int:
    todos = load_todos()
    status_filter = args.status
    tag_filter = args.tag

    _print_list(todos, status_filter, tag_filter)
    return 0


def done(args: argparse.Namespace) -> int:
    if not args.id.isdigit():
        if Console:
            Console.print("[red]Error: Invalid task ID.[/red]")
        return 1

    success = update_status(int(args.id), "completed")
    if success:
        if Console:
            Console.print(f"[green]Task {args.id} marked as completed.[/green]")
    else:
        if Console:
            Console.print("[red]Error: Task not found.[/red]")
        return 1
    return 0


def delete(args: argparse.Namespace) -> int:
    if not args.id.isdigit():
        if Console:
            Console.print("[red]Error: Invalid task ID.[/red]")
        return 1

    success = delete_todo(int(args.id))
    if success:
        if Console:
            Console.print(f"[green]Task {args.id} deleted successfully.[/green]")
    else:
        if Console:
            Console.print("[red]Error: Task not found.[/red]")
        return 1
    return 0


def stats(args: argparse.Namespace) -> int:
    stats_data = get_stats()
    _print_stats(stats_data)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI Todo Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("title", required=True)
    add_parser.add_argument("--priority", default="Medium")
    add_parser.add_argument("--tag", default="General")
    add_parser.add_argument("--due", default=None)
    add_parser.set_defaults(func=add)

    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--status", default=None)
    list_parser.add_argument("--tag", default=None)
    list_parser.set_defaults(func=list)

    done_parser = subparsers.add_parser("done", help="Mark task as done")
    done_parser.add_argument("id", type=int)
    done_parser.set_defaults(func=done)

    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("id", type=int)
    delete_parser.set_defaults(func=delete)

    stats_parser = subparsers.add_parser("stats", help="Show statistics")
    stats_parser.set_defaults(func=stats)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        return

    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()