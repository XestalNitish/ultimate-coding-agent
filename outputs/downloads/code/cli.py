import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

import rich
from rich.console import Console
from rich.table import Table

import storage
from models import TodoItem


def _get_storage_path() -> str:
    env_path = os.getenv("TODOS_STORAGE_PATH", "todos.json")
    return env_path


def add(args: argparse.Namespace) -> int:
    try:
        storage_path = _get_storage_path()
        title = args.title.strip()
        if not title:
            raise ValueError("Title cannot be empty.")

        due_date = None
        if args.due:
            try:
                due_date = args.due
            except ValueError:
                raise ValueError("Invalid due date format.")

        result = storage.add_todo(
            title=title,
            priority=args.priority,
            tag=args.tag,
            due_date=due_date,
            storage_path=storage_path,
        )

        console = Console()
        console.print(f"[bold green]✓[/] Todo added successfully!")
        console.print(f"ID: {result['id']}")
        console.print(f"Title: {result['title']}")
        console.print(f"Status: {result['status']}")

        return 0
    except Exception as e:
        console = Console()
        console.print(f"[bold red]✗[/] Error adding todo: {e}")
        return 1


def list(args: argparse.Namespace) -> int:
    try:
        storage_path = _get_storage_path()
        todos = storage.load_todos(storage_path=storage_path)

        table = Table(title="Task List", show_lines=True)
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Status", style="yellow")
        table.add_column("Priority", style="green")
        table.add_column("Tag", style="blue")

        if not todos:
            table.add_row("No tasks found", "-", "-", "-", "-", "-")
        else:
            for todo in todos:
                table.add_row(
                    str(todo.get("id", "")),
                    str(todo.get("title", "")),
                    str(todo.get("status", "")),
                    str(todo.get("priority", "")),
                    str(todo.get("tag", "")),
                )

        console = Console()
        console.print(table)

        if args.status:
            filtered = [t for t in todos if t.get("status") == args.status]
            console.print(f"\n[bold]Filtered by status: {args.status}[/]")
            if filtered:
                table = Table(title=f"Filtered Tasks ({len(filtered)})", show_lines=True)
                table.add_column("ID", style="cyan")
                table.add_column("Title", style="magenta")
                table.add_column("Status", style="yellow")
                table.add_column("Priority", style="green")
                table.add_column("Tag", style="blue")
                for todo in filtered:
                    table.add_row(
                        str(todo.get("id", "")),
                        str(todo.get("title", "")),
                        str(todo.get("status", "")),
                        str(todo.get("priority", "")),
                        str(todo.get("tag", "")),
                    )
                console.print(table)
            else:
                console.print("[yellow]No tasks match the filter.[/]")

        if args.tag:
            filtered = [t for t in todos if t.get("tag") == args.tag]
            console.print(f"\n[bold]Filtered by tag: {args.tag}[/]")
            if filtered:
                table = Table(title=f"Filtered Tasks ({len(filtered)})", show_lines=True)
                table.add_column("ID", style="cyan")
                table.add_column("Title", style="magenta")
                table.add_column("Status", style="yellow")
                table.add_column("Priority", style="green")
                table.add_column("Tag", style="blue")
                for todo in filtered:
                    table.add_row(
                        str(todo.get("id", "")),
                        str(todo.get("title", "")),
                        str(todo.get("status", "")),
                        str(todo.get("priority", "")),
                        str(todo.get("tag", "")),
                    )
                console.print(table)
            else:
                console.print("[yellow]No tasks match the tag filter.[/]")

        return 0
    except Exception as e:
        console = Console()
        console.print(f"[bold red]✗[/] Error listing tasks: {e}")
        return 1


def done(args: argparse.Namespace) -> int:
    try:
        storage_path = _get_storage_path()
        success = storage.update_status(
            todo_id=args.id,
            status="completed",
            storage_path=storage_path,
        )
        if success:
            console = Console()
            console.print(f"[bold green]✓[/] Task {args.id} marked as completed.")
            return 0
        else:
            console = Console()
            console.print(f"[bold red]✗[/] Task {args.id} not found or invalid.")
            return 1
    except Exception as e:
        console = Console()
        console.print(f"[bold red]✗[/] Error updating task: {e}")
        return 1


def delete(args: argparse.Namespace) -> int:
    try:
        storage_path = _get_storage_path()
        success = storage.delete_todo(
            todo_id=args.id,
            storage_path=storage_path,
        )
        if success:
            console = Console()
            console.print(f"[bold green]✓[/] Task {args.id} deleted successfully.")
            return 0
        else:
            console = Console()
            console.print(f"[bold red]✗[/] Task {args.id} not found or invalid.")
            return 1
    except Exception as e:
        console = Console()
        console.print(f"[bold red]✗[/] Error deleting task: {e}")
        return 1


def stats(args: argparse.Namespace) -> int:
    try:
        storage_path = _get_storage_path()
        stats_data = storage.get_stats(storage_path=storage_path)

        console = Console()
        console.print("[bold cyan]📊 Task Statistics[/]")
        console.print(f"Total Tasks: [bold yellow]{stats_data.get('total', 0)}[/]")
        console.print(f"Pending: [bold green]{stats_data.get('pending', 0)}[/]")
        console.print(f"Completed: [bold blue]{stats_data.get('completed', 0)}[/]")

        if stats_data.get("total", 0) > 0:
            completion_rate = (stats_data.get("completed", 0) / stats_data.get("total", 1)) * 100
            console.print(f"Completion Rate: [bold magenta]{completion_rate:.1f}%[/]")

        return 0
    except Exception as e:
        console = Console()
        console.print(f"[bold red]✗[/] Error retrieving stats: {e}")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI Todo Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a new todo")
    add_parser.add_argument("title", required=True, help="Title of the todo")
    add_parser.add_argument("--priority", default="Medium", choices=["Low", "Medium", "High"])
    add_parser.add_argument("--tag", default="General", help="Tag for the todo")
    add_parser.add_argument("--due", default=None, help="Due date (YYYY-MM-DD)")

    list_parser = subparsers.add_parser("list", help="List all todos")
    list_parser.add_argument("--status", default=None, choices=["pending", "completed"])
    list_parser.add_argument("--tag", default=None)

    done_parser = subparsers.add_parser("done", help="Mark a todo as completed")
    done_parser.add_argument("id", type=int, required=True)

    delete_parser = subparsers.add_parser("delete", help="Delete a todo")
    delete_parser.add_argument("id", type=int, required=True)

    stats_parser = subparsers.add_parser("stats", help="Display statistics")

    args = parser.parse_args()

    if args.command == "add":
        sys.exit(add(args))
    elif args.command == "list":
        sys.exit(list(args))
    elif args.command == "done":
        sys.exit(done(args))
    elif args.command == "delete":
        sys.exit(delete(args))
    elif args.command == "stats":
        sys.exit(stats(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()