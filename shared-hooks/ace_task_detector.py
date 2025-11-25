#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
ACE Task Detector - Heuristic-based task completion detection for main agent work.

v5.2.0 CHANGES (CRITICAL - Fix Garbage Data):
- Changed from OR logic to AND logic (require MULTIPLE signals)
- Increased IDLE_THRESHOLD: 30 → 120 seconds
- Increased TOOL_THRESHOLD: 3 → 10 tools
- Added STATE-CHANGE verification (Read-only ops don't count!)
- Added trivial task filtering (ACE commands don't trigger)

Per ACE Research Paper: Learning should only occur with "meaningful execution feedback"
The old heuristics (3 tools = substantial work) were producing GARBAGE patterns.

Detects when the main agent has completed a substantial task by analyzing:
- Tool usage patterns (state-changing tools only!)
- User message signals
- Time-based heuristics (longer threshold)
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
    """
    Detects task completion using multiple heuristics.

    v5.2.0: Changed to AND logic - require MULTIPLE signals to prevent garbage.
    Old OR logic produced 835+ false positives per session!
    """

    # User confirmation keywords (must be combined with OTHER signals)
    CONFIRMATION_KEYWORDS = [
        "thanks", "thank you", "perfect", "great", "good", "excellent",
        "done", "complete", "finished", "ok", "okay", "nice",
        "next", "moving on", "that's all", "all set"
    ]

    # v5.2.0: Time threshold increased from 30 → 120 seconds
    # 30 seconds was triggering while user reads output (garbage!)
    IDLE_THRESHOLD = 120

    # v5.2.0: Tool threshold increased from 3 → 10 tools
    # 3 Read operations is NOT substantial work!
    TOOL_THRESHOLD = 10

    # State-changing tools (vs read-only)
    # Only these count toward "substantial work"
    STATE_CHANGING_TOOLS = ['Edit', 'Write', 'Bash', 'NotebookEdit', 'mcp__']
    READ_ONLY_TOOLS = ['Read', 'Glob', 'Grep', 'WebFetch', 'WebSearch', 'TodoWrite']

    # Trivial task patterns (should NEVER trigger learning)
    TRIVIAL_PATTERNS = [
        'ace:ace-', '/ace-', 'ace-status', 'ace-patterns', 'ace-search',
        'ace-learn', 'ace-configure', 'ace-bootstrap', 'ace-clear'
    ]

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
            "state_change_count": 0,  # v5.2.0: Track state-changing tools separately
            "recent_tools": [],       # v5.2.0: Track recent tool names for analysis
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

        v5.2.0 CHANGES:
        - Threshold increased from 3 → TOOL_THRESHOLD (10)
        - Now tracks state-changing vs read-only tools separately
        - Requires STATE-CHANGING tools, not just any tools

        Read-only operations (Read, Glob, Grep) don't count as substantial work!
        """
        self.state["tool_count"] = self.state.get("tool_count", 0) + 1
        self.state["last_tool_name"] = tool_name
        self.state["last_tool_time"] = datetime.now(timezone.utc).isoformat()

        # Track recent tools (keep last 20)
        recent = self.state.get("recent_tools", [])
        recent.append(tool_name)
        self.state["recent_tools"] = recent[-20:]  # Keep last 20

        # v5.2.0: Count state-changing tools separately
        is_state_change = any(sc in tool_name for sc in self.STATE_CHANGING_TOOLS)
        if is_state_change:
            self.state["state_change_count"] = self.state.get("state_change_count", 0) + 1

        self._save_state()

        # v5.2.0: Require TOOL_THRESHOLD (10) tools AND at least 1 state change
        has_enough_tools = self.state["tool_count"] >= self.TOOL_THRESHOLD
        has_state_change = self.state.get("state_change_count", 0) >= 1

        return has_enough_tools and has_state_change

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

    def is_trivial_context(self, event_data: Dict[str, Any], user_message: Optional[str] = None) -> bool:
        """
        v5.2.0: Check if current context is trivial (should never trigger learning).

        Prevents learning from ACE commands like /ace-status, /ace-patterns, etc.
        """
        # Check tool input for ACE command patterns
        tool_input = event_data.get("tool_input", {})
        command = tool_input.get("command", "")

        for pattern in self.TRIVIAL_PATTERNS:
            if pattern.lower() in command.lower():
                return True

        # Check user message for ACE command patterns
        if user_message:
            for pattern in self.TRIVIAL_PATTERNS:
                if pattern.lower() in user_message.lower():
                    return True

        return False

    def has_state_changing_tools(self) -> bool:
        """
        v5.2.0: Check if recent tools include state-changing operations.

        Reading files is NOT substantial work - need actual modifications!
        """
        recent_tools = self.state.get("recent_tools", [])

        for tool in recent_tools:
            if any(sc in tool for sc in self.STATE_CHANGING_TOOLS):
                return True
        return False

    def detect_task_complete(
        self,
        event_data: Dict[str, Any],
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main detection logic.

        v5.2.0 CRITICAL CHANGE: Changed from OR to AND logic!

        OLD (broken): Any single heuristic triggers learning (835+ false positives!)
        NEW (fixed): Require MULTIPLE signals to trigger learning

        Returns:
            {
                "task_complete": bool,
                "triggered_by": str,  # Which heuristics triggered
                "confidence": float,  # 0.0 - 1.0
                "details": str
            }
        """
        tool_name = event_data.get("tool_name", "unknown")

        # v5.2.0: FIRST CHECK - Is this a trivial context? (ACE commands, etc.)
        if self.is_trivial_context(event_data, user_message):
            return {
                "task_complete": False,
                "triggered_by": None,
                "confidence": 0.0,
                "details": "Trivial context (ACE command) - skipped"
            }

        # Check all heuristics
        heuristics = {
            "tool_sequence": self.check_tool_sequence(tool_name),
            "user_confirmation": self.check_user_confirmation(user_message),
            "time_based_pause": self.check_time_based_pause(),
            "todo_completion": self.check_todo_completion(event_data),
            "git_commit": self.check_git_commit(event_data)
        }

        # v5.2.0: Count how many heuristics match
        matching = [name for name, matches in heuristics.items() if matches]
        signal_count = len(matching)

        # v5.2.0: CRITICAL - Require at least 2 signals (AND logic, not OR!)
        # Exception: High-confidence signals (git_commit, todo_completion) can stand alone
        #            but ONLY if there are state-changing tools
        high_confidence_signals = ["git_commit", "todo_completion"]
        has_high_confidence = any(s in matching for s in high_confidence_signals)
        has_state_change = self.has_state_changing_tools()

        task_complete = False
        triggered_by = None

        if signal_count >= 2 and has_state_change:
            # Multiple signals + state change = real task completion
            task_complete = True
            triggered_by = ", ".join(matching)
        elif has_high_confidence and has_state_change:
            # High-confidence single signal + state change = real task completion
            task_complete = True
            triggered_by = matching[0] if matching else "unknown"

        if task_complete:
            # Reset state after detection
            self.state["tool_count"] = 0
            self.state["state_change_count"] = 0
            self.state["recent_tools"] = []
            self._save_state()

            # Calculate confidence based on signal count and type
            confidence = self._calculate_confidence(matching, signal_count)

            return {
                "task_complete": True,
                "triggered_by": triggered_by,
                "confidence": confidence,
                "details": self._get_multi_details(matching, event_data, user_message)
            }

        # Not enough signals
        return {
            "task_complete": False,
            "triggered_by": None,
            "confidence": 0.0,
            "details": f"Tool count: {self.state['tool_count']}, State changes: {self.state.get('state_change_count', 0)}, Signals: {signal_count}/2 required"
        }

    def _calculate_confidence(self, matching: list, signal_count: int) -> float:
        """v5.2.0: Calculate confidence based on signal count and types."""
        # Base confidence from signal count
        base = min(0.5 + (signal_count * 0.15), 0.95)

        # Boost for high-confidence signals
        if "git_commit" in matching:
            base = min(base + 0.10, 0.98)
        if "todo_completion" in matching:
            base = min(base + 0.10, 0.98)

        return base

    def _get_multi_details(
        self,
        matching: list,
        event_data: Dict[str, Any],
        user_message: Optional[str]
    ) -> str:
        """v5.2.0: Get details for multiple matching heuristics."""
        details = []
        for name in matching:
            details.append(self._get_details(name, event_data, user_message))
        return " | ".join(details)

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
