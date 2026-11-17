import argparse
import os
from typing import List, Optional
import json
from datetime import datetime

from pydantic import BaseModel, Field
from rich.console import Console

from models import TodoItem
from storage import (
    TodoStorage,
    load_todos,
    save_todos,
    add_todo,
    update_status,
    delete_todo,
    get_stats
)

console = Console()

def main() -> None:
    parser = argparse.ArgumentParser(description="CLI Todo Manager")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a new todo")
    add_parser.add_argument("title", help="Title of the todo")
    add_parser.add_argument("--priority", default="Medium", help="Priority level")
    add_parser.add_argument("--tag", default="General", help="Tag for the todo")
    add_parser.add_argument("--due", type=str, default=None, help="Due date")
    add_parser.set_defaults(func=add)

    list_parser = subparsers.add_parser("list", help="List todos")
    list_parser.add_argument("--status", default="pending", help="Filter by status")
    list_parser.add_argument("--tag", default=None, help="Filter by tag")
    list_parser.set_defaults(func=list)

    done_parser = subparsers.add_parser("done", help="Mark todo as done")
    done_parser.add_argument("id", type=int, help="ID of the todo")
    done_parser.set_defaults(func=done)

    delete_parser = subparsers.add_parser("delete", help="Delete a todo")
    delete_parser.add_argument("id", type=int, help="ID of the todo to delete")
    delete_parser.set_defaults(func=delete)

    stats_parser = subparsers.add_parser("stats", help="Show statistics")
    stats_parser.set_defaults(func=stats)

    args = parser.parse_args()

    if args.command is None:
        console.print("[bold cyan]Usage:[/bold cyan]")
        console.print("  python cli.py add <title> [--priority] [--tag] [--due]")
        console.print("  python cli.py list [--status] [--tag]")
        console.print("  python cli.py done <id>")
        console.print("  python cli.py delete <id>")
        console.print("  python cli.py stats")
        return

    args.func(args)

def add(args) -> None:
    todo_data = add_todo(
        title=args.title,
        priority=args.priority,
        tag=args.tag,
        due_date=args.due
    )
    console.print(f"[bold green]Added:[/bold green] {todo_data['title']} (ID: {todo_data['id']})")

def list(args) -> None:
    todos = load_todos()
    filtered = [t for t in todos if t.get("status") == args.status and (not args.tag or t.get("tag") == args.tag)]
    if not filtered:
        console.print("[yellow]No matching todos found.[/yellow]")
        return

    console.print("[bold]Todos:[/bold]")
    for t in filtered:
        status_icon = "[green]✓[/green]" if t.get("status") == "completed" else "[yellow]•[/yellow]"
        priority_icon = {"High": "[red]![/red]", "Medium": "[yellow]M[/yellow]", "Low": "[green]L[/green]"}.get(t.get("priority", "Medium"), "M")
        console.print(f"[bold]{status_icon} {t.get('title')}[/bold] [{priority_icon} {t.get('priority')}][/]")
        if t.get("description"):
            console.print(f"    [dim]{t.get('description')}[/dim]")
        if t.get("tag"):
            console.print(f"    [dim]Tag: {t.get('tag')}[/dim]")

def done(args) -> None:
    success = update_status(args.id, "completed")
    if success:
        console.print(f"[bold green]Marked done:[/bold green] Todo ID {args.id}")
    else:
        console.print(f"[red]Error:[/red] Todo ID {args.id} not found or invalid.")

def delete(args) -> None:
    success = delete_todo(args.id)
    if success:
        console.print(f"[bold green]Deleted:[/bold green] Todo ID {args.id}")
    else:
        console.print(f"[red]Error:[/red] Todo ID {args.id} not found or invalid.")

def stats(args) -> None:
    stats_data = get_stats()
    console.print("[bold cyan]Statistics:[/bold cyan]")
    console.print(f"Total Tasks: [bold]{stats_data['total']}[/bold]")
    console.print(f"Pending: [bold]{stats_data['pending']}[/bold]")
    console.print(f"Completed: [bold]{stats_data['completed']}[/bold]")
    if stats_data['total'] > 0:
        completion_rate = (stats_data['completed'] / stats_data['total']) * 100
        console.print(f"Completion Rate: [bold]{completion_rate:.1f}%[/bold]")

if __name__ == "__main__":
    main()
    if os.getenv("RUN_SELF_TEST", "1") == "1":
        test_storage()

def test_storage() -> None:
    storage = TodoStorage("test_todos.json")
    initial_stats = get_stats()
    assert initial_stats['total'] == 0

    added = add_todo("Test Task", priority="High", tag="Test")
    assert added['id'] == 1
    assert added['status'] == "pending"

    assert update_status(1, "in_progress")
    assert load_todos()[0]['status'] == "in_progress"

    assert update_status(1, "completed")
    assert load_todos()[0]['status'] == "completed"

    assert delete_todo(1)
    assert load_todos() == []

    stats = get_stats()
    assert stats['total'] == 0
    assert stats['pending'] == 0
    assert stats['completed'] == 0

    console.print("[bold green]Self-tests passed.[/bold green]")
    if os.path.exists("test_todos.json"):
        os.remove("test_todos.json")
        console.print("[dim]Cleaned up test file.[/dim]")