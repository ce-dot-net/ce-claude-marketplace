#!/usr/bin/env python3
"""
Todo CLI - Simple command-line todo manager.

Usage:
    python todo_cli.py add "Buy groceries"
    python todo_cli.py list
    python todo_cli.py done 1
    python todo_cli.py clear
"""

import argparse
import json
from pathlib import Path
from datetime import datetime

TODO_FILE = Path("/tmp/todos.json")


def load_todos() -> list:
    """Load todos from JSON file."""
    if not TODO_FILE.exists():
        return []
    try:
        return json.loads(TODO_FILE.read_text())
    except json.JSONDecodeError:
        return []


def save_todos(todos: list):
    """Save todos to JSON file."""
    TODO_FILE.write_text(json.dumps(todos, indent=2))


def get_next_id(todos: list) -> int:
    """Get the next available todo ID."""
    if not todos:
        return 1
    return max(t["id"] for t in todos) + 1


def cmd_add(args):
    """Add a new todo."""
    todos = load_todos()
    todo = {
        "id": get_next_id(todos),
        "text": args.text,
        "done": False,
        "created_at": datetime.now().isoformat()
    }
    todos.append(todo)
    save_todos(todos)
    print(f"✅ Added todo #{todo['id']}: {todo['text']}")


def cmd_list(args):
    """List all todos."""
    todos = load_todos()
    if not todos:
        print("📋 No todos yet. Add one with: todo_cli.py add \"Your task\"")
        return

    print("📋 Your todos:\n")
    for todo in todos:
        status = "✓" if todo["done"] else "○"
        done_style = "done" if todo["done"] else ""
        print(f"  [{status}] #{todo['id']} - {todo['text']}")

    total = len(todos)
    done = sum(1 for t in todos if t["done"])
    print(f"\n  {done}/{total} completed")


def cmd_done(args):
    """Mark a todo as done."""
    todos = load_todos()
    for todo in todos:
        if todo["id"] == args.id:
            todo["done"] = True
            save_todos(todos)
            print(f"✅ Marked todo #{args.id} as done")
            return

    print(f"❌ Todo #{args.id} not found")


def cmd_clear(args):
    """Clear all todos."""
    save_todos([])
    print("🗑️  Cleared all todos")


def main():
    parser = argparse.ArgumentParser(
        description="Simple todo CLI manager",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # add command
    add_parser = subparsers.add_parser("add", help="Add a new todo")
    add_parser.add_argument("text", help="Todo text")
    add_parser.set_defaults(func=cmd_add)

    # list command
    list_parser = subparsers.add_parser("list", help="List all todos")
    list_parser.set_defaults(func=cmd_list)

    # done command
    done_parser = subparsers.add_parser("done", help="Mark a todo as done")
    done_parser.add_argument("id", type=int, help="Todo ID to mark as done")
    done_parser.set_defaults(func=cmd_done)

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all todos")
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
