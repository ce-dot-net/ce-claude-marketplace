#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
ACE Task Detector - Heuristic-based task completion detection for main agent work.

Detects when the main agent has completed a substantial task by analyzing:
- Tool usage patterns
- User message signals
- Time-based heuristics
- Context signals (todos, commits)
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

class ACETaskDetector:
    """Detects task completion using multiple heuristics (OR logic)."""

    # User confirmation keywords
    CONFIRMATION_KEYWORDS = [
        "thanks", "thank you", "perfect", "great", "good", "excellent",
        "done", "complete", "finished", "ok", "okay", "nice",
        "next", "moving on", "that's all", "all set"
    ]

    # Time threshold for idle detection (seconds)
    IDLE_THRESHOLD = 30

    def __init__(self, state_file: str = ".claude/data/logs/ace-task-state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load persistent state from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            "last_tool_time": None,
            "tool_count": 0,
            "last_user_message": None,
            "last_tool_name": None
        }

    def _save_state(self):
        """Save persistent state to disk."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            print(f"[WARN] Failed to save state: {e}", file=sys.stderr)

    def check_tool_sequence(self, tool_name: str) -> bool:
        """
        Heuristic 1: Tool sequence pattern.
        Detect 3+ tool uses in sequence (substantial work pattern).
        """
        self.state["tool_count"] = self.state.get("tool_count", 0) + 1
        self.state["last_tool_name"] = tool_name
        self.state["last_tool_time"] = datetime.now(timezone.utc).isoformat()
        self._save_state()

        # If we've seen 3+ tools, this indicates substantial work
        return self.state["tool_count"] >= 3

    def check_user_confirmation(self, user_message: Optional[str]) -> bool:
        """
        Heuristic 2: User confirmation signals.
        Detect user messages indicating task completion.
        """
        if not user_message:
            return False

        message_lower = user_message.lower().strip()

        # Check for confirmation keywords
        for keyword in self.CONFIRMATION_KEYWORDS:
            if keyword in message_lower:
                return True

        return False

    def check_time_based_pause(self) -> bool:
        """
        Heuristic 3: Time-based idle detection.
        Detect 30+ seconds since last tool use (natural pause after work).
        """
        last_tool_time = self.state.get("last_tool_time")
        if not last_tool_time:
            return False

        try:
            last_time = datetime.fromisoformat(last_tool_time)
            now = datetime.now(timezone.utc)
            elapsed = (now - last_time).total_seconds()

            return elapsed >= self.IDLE_THRESHOLD
        except Exception:
            return False

    def check_todo_completion(self, event_data: Dict[str, Any]) -> bool:
        """
        Heuristic 4: Todo completion signal.
        Detect TodoWrite tool marking all todos as completed.
        """
        tool_name = event_data.get("tool_name", "")
        if tool_name != "TodoWrite":
            return False

        # Check if todos exist and all are completed
        tool_input = event_data.get("tool_input", {})
        todos = tool_input.get("todos", [])

        if not todos:
            return False

        # All todos completed?
        return all(todo.get("status") == "completed" for todo in todos)

    def check_git_commit(self, event_data: Dict[str, Any]) -> bool:
        """
        Heuristic 5: Successful git commit.
        Detect Bash tool executing git commit successfully.
        """
        tool_name = event_data.get("tool_name", "")
        if tool_name != "Bash":
            return False

        tool_input = event_data.get("tool_input", {})
        command = tool_input.get("command", "")

        # Check if it's a git commit command
        return "git commit" in command.lower()

    def detect_task_complete(
        self,
        event_data: Dict[str, Any],
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main detection logic - OR all heuristics.

        Returns:
            {
                "task_complete": bool,
                "triggered_by": str,  # Which heuristic triggered
                "confidence": float,  # 0.0 - 1.0
                "details": str
            }
        """
        tool_name = event_data.get("tool_name", "unknown")

        # Check all heuristics (OR logic)
        heuristics = [
            ("tool_sequence", self.check_tool_sequence(tool_name)),
            ("user_confirmation", self.check_user_confirmation(user_message)),
            ("time_based_pause", self.check_time_based_pause()),
            ("todo_completion", self.check_todo_completion(event_data)),
            ("git_commit", self.check_git_commit(event_data))
        ]

        # Find first matching heuristic
        for name, matches in heuristics:
            if matches:
                # Reset tool count after detection
                self.state["tool_count"] = 0
                self._save_state()

                return {
                    "task_complete": True,
                    "triggered_by": name,
                    "confidence": self._get_confidence(name),
                    "details": self._get_details(name, event_data, user_message)
                }

        # No heuristics matched
        return {
            "task_complete": False,
            "triggered_by": None,
            "confidence": 0.0,
            "details": f"Tool count: {self.state['tool_count']}"
        }

    def _get_confidence(self, heuristic: str) -> float:
        """Get confidence level for each heuristic."""
        confidence_map = {
            "user_confirmation": 0.95,  # Very high confidence
            "todo_completion": 0.90,    # High confidence
            "git_commit": 0.85,         # High confidence
            "tool_sequence": 0.70,      # Medium confidence
            "time_based_pause": 0.60    # Lower confidence
        }
        return confidence_map.get(heuristic, 0.5)

    def _get_details(
        self,
        heuristic: str,
        event_data: Dict[str, Any],
        user_message: Optional[str]
    ) -> str:
        """Get human-readable details for triggered heuristic."""
        details_map = {
            "user_confirmation": f"User said: '{user_message}'",
            "todo_completion": "All todos marked completed",
            "git_commit": f"Git commit executed",
            "tool_sequence": f"{self.state['tool_count']} tools used in sequence",
            "time_based_pause": f"30+ seconds since last tool use"
        }
        return details_map.get(heuristic, "Task completion detected")


def main():
    parser = argparse.ArgumentParser(description="Detect task completion using heuristics")
    parser.add_argument("--user-message", help="Optional user message to analyze")
    args = parser.parse_args()

    # Read PostToolUse event from stdin
    try:
        event_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"task_complete": False, "error": "Invalid JSON input"}))
        sys.exit(1)

    # Detect task completion
    detector = ACETaskDetector()
    result = detector.detect_task_complete(event_data, args.user_message)

    # Output result as JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
