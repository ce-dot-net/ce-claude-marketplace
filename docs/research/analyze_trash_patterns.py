#!/usr/bin/env python3
"""
Analyze what generates "trash" patterns in ACE playbook.

This script simulates the trace building logic to understand
where empty/minimal descriptions come from.
"""

import json


def simulate_posttooluse_trace():
    """Simulate ace_task_complete.py trace building."""
    print("="*60)
    print("SIMULATING PostToolUse (ace_task_complete.py)")
    print("="*60)
    print()

    # Test case 1: Empty tool description
    print("Test 1: Empty tool description")
    print("-" * 40)
    
    event = {
        "tool_name": "Edit",
        "description": ""  # EMPTY!
    }
    
    tool_name = event.get('tool_name', 'unknown')
    tool_description = event.get('description', '')
    
    # Line 161 from ace_task_complete.py
    task_description = f"Task completed: {tool_description[:200]}" if tool_description else "Task completed"
    
    # Line 180 from ace_task_complete.py
    action = f"{tool_name} - {tool_description}"
    
    print(f"  Event: {event}")
    print(f"  Generated task: '{task_description}'")
    print(f"  Generated action: '{action}'")
    print(f"  ❌ PROBLEM: Action is 'Edit - ' (empty content!)")
    print()
    
    # Test case 2: Single character description
    print("Test 2: Single character description")
    print("-" * 40)
    
    event2 = {
        "tool_name": "Write",
        "description": " "  # WHITESPACE!
    }
    
    tool_name2 = event2.get('tool_name', 'unknown')
    tool_description2 = event2.get('description', '')
    
    task_description2 = f"Task completed: {tool_description2[:200]}" if tool_description2 else "Task completed"
    action2 = f"{tool_name2} - {tool_description2}"
    
    print(f"  Event: {event2}")
    print(f"  Generated task: '{task_description2}'")
    print(f"  Generated action: '{action2}'")
    print(f"  ❌ PROBLEM: Action is 'Write -  ' (whitespace only!)")
    print()


def simulate_precompact_trace():
    """Simulate ace_after_task.py trace building."""
    print("="*60)
    print("SIMULATING PreCompact (ace_after_task.py)")
    print("="*60)
    print()

    # Test case 1: Empty tool description in tool_uses
    print("Test 1: Empty tool description")
    print("-" * 40)
    
    tool_uses = [
        {
            "tool_name": "Edit",
            "description": "",  # EMPTY!
            "result": {"summary": "completed"}
        }
    ]
    
    # Line 64-76 from ace_after_task.py
    for idx, tool in enumerate(tool_uses, 1):
        tool_name = tool.get('tool_name', 'unknown')
        tool_desc = tool.get('description', '')
        
        # Line 76
        action = f"{tool_name} - {tool_desc}"
        
        print(f"  Tool: {tool}")
        print(f"  Generated action: '{action}'")
        print(f"  ❌ PROBLEM: Action is 'Edit - ' (empty content!)")
    print()
    
    # Test case 2: Empty user message
    print("Test 2: Empty user message")
    print("-" * 40)
    
    messages = [
        {"role": "user", "content": ""},  # EMPTY!
        {"role": "assistant", "content": "I completed the task"}
    ]
    
    # Line 50-56 from ace_after_task.py
    user_messages = [m for m in messages if m.get('role') == 'user']
    if user_messages:
        first_user = user_messages[0]
        content = first_user.get('content', '')
        if content:
            task_description = f"User request: {content[:250]}"
        else:
            task_description = "Session work"  # Fallback
    
    print(f"  Messages: {messages}")
    print(f"  Generated task: '{task_description}'")
    print(f"  ⚠️ Falls back to 'Session work' but should filter this out")
    print()


def analyze_root_cause():
    """Analyze the root cause of trash patterns."""
    print("="*60)
    print("ROOT CAUSE ANALYSIS")
    print("="*60)
    print()
    
    print("WHERE ARE TRASH PATTERNS COMING FROM?")
    print("-" * 40)
    print()
    print("1. POSTTOOLUSE (ace_task_complete.py):")
    print("   - Line 180: f\"{tool_name} - {tool_description}\"")
    print("   - When tool_description is empty: 'Edit - ', 'Write - ', etc.")
    print("   - These get sent to server as trajectory actions!")
    print()
    print("2. PRECOMPACT (ace_after_task.py):")
    print("   - Line 76: f\"{tool_name} - {tool_desc}\"")
    print("   - Same issue: empty tool_desc creates empty actions")
    print("   - Current check (line 178-181) only filters 'Session work'")
    print()
    print("WHY AREN'T THEY BEING FILTERED?")
    print("-" * 40)
    print()
    print("PostToolUse (ace_task_complete.py):")
    print("  - is_substantial_task() checks:")
    print("    1. Tool name == 'Task' ✓")
    print("    2. Git commit ✓")
    print("    3. Edit sequence completion ✓")
    print("  - ❌ MISSING: Check for empty descriptions!")
    print()
    print("PreCompact (ace_after_task.py):")
    print("  - has_substantial_work checks:")
    print("    1. trajectory exists ✓ (even if empty actions)")
    print("    2. task != 'Session work' ✓")
    print("  - ❌ MISSING: Check for trajectory quality!")
    print()
    print("EXAMPLES OF TRASH GETTING THROUGH:")
    print("-" * 40)
    print()
    print("Scenario 1: PostToolUse with empty Edit")
    print("  Event: {tool_name: 'Edit', description: ''}")
    print("  → is_substantial_task() returns False (no trigger)")
    print("  → BUT if part of edit sequence, TRIGGERS!")
    print("  → Sends trajectory with 'Edit - ' actions")
    print()
    print("Scenario 2: PreCompact with minimal tools")
    print("  Event: {tool_uses: [{tool_name: 'Read', description: ''}]}")
    print("  → has_substantial_work = True (trajectory exists!)")
    print("  → task != 'Session work' ✓")
    print("  → Sends trajectory with empty actions")
    print()
    

def propose_solution():
    """Propose solutions to filter trash patterns."""
    print("="*60)
    print("PROPOSED SOLUTIONS")
    print("="*60)
    print()
    
    print("SOLUTION 1: Filter Empty Descriptions (BEST)")
    print("-" * 40)
    print()
    print("In ace_task_complete.py, line 180:")
    print("BEFORE:")
    print("  trajectory.append({")
    print("    'step': len(trajectory) + 1,")
    print("    'action': f'{tool_name} - {tool_description}',")
    print("    'result': 'completed'")
    print("  })")
    print()
    print("AFTER:")
    print("  # Skip empty/whitespace-only descriptions")
    print("  if tool_description and tool_description.strip():")
    print("    trajectory.append({")
    print("      'step': len(trajectory) + 1,")
    print("      'action': f'{tool_name} - {tool_description}',")
    print("      'result': 'completed'")
    print("    })")
    print()
    print("In ace_after_task.py, line 74-84:")
    print("BEFORE:")
    print("  trajectory_entry = {")
    print("    'step': idx,")
    print("    'action': f'{tool_name} - {tool_desc}',")
    print("    'result': ...")
    print("  }")
    print("  trajectory.append(trajectory_entry)")
    print()
    print("AFTER:")
    print("  # Skip empty/whitespace-only descriptions")
    print("  if tool_desc and tool_desc.strip() and len(tool_desc.strip()) >= 5:")
    print("    trajectory_entry = {")
    print("      'step': idx,")
    print("      'action': f'{tool_name} - {tool_desc}',")
    print("      'result': ...")
    print("    }")
    print("    trajectory.append(trajectory_entry)")
    print()
    print("SOLUTION 2: Trajectory Quality Check")
    print("-" * 40)
    print()
    print("In ace_task_complete.py, add check before capture_learning():")
    print()
    print("  # Check trajectory quality")
    print("  if not trajectory or len(trajectory) == 0:")
    print("    print(json.dumps({}))")
    print("    sys.exit(0)")
    print()
    print("  # Ensure at least one meaningful action")
    print("  meaningful_actions = [")
    print("    t for t in trajectory")
    print("    if t.get('action') and len(t['action'].split(' - ', 1)[1].strip()) >= 5")
    print("  ]")
    print()
    print("  if len(meaningful_actions) == 0:")
    print("    # All actions are empty/trash - skip learning")
    print("    print(json.dumps({}))")
    print("    sys.exit(0)")
    print()
    print("SOLUTION 3: Minimum Task Description Length")
    print("-" * 40)
    print()
    print("In ace_after_task.py, line 178-181:")
    print()
    print("BEFORE:")
    print("  has_substantial_work = (")
    print("    trace['trajectory'] and len(trace['trajectory']) > 0 and")
    print("    not trace['task'].startswith('Session work')")
    print("  )")
    print()
    print("AFTER:")
    print("  # Check for meaningful trajectory actions")
    print("  meaningful_actions = [")
    print("    t for t in trace['trajectory']")
    print("    if t.get('action') and len(t['action'].split(' - ', 1)[1].strip()) >= 5")
    print("  ]")
    print()
    print("  has_substantial_work = (")
    print("    len(meaningful_actions) > 0 and")
    print("    not trace['task'].startswith('Session work') and")
    print("    len(trace['task']) >= 20  # Minimum task description length")
    print("  )")
    print()
    print("="*60)
    print("RECOMMENDED: Implement ALL 3 solutions for robust filtering")
    print("="*60)
    print()


if __name__ == '__main__':
    simulate_posttooluse_trace()
    print()
    simulate_precompact_trace()
    print()
    analyze_root_cause()
    print()
    propose_solution()
