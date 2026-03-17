
import sys
import json
import os
import subprocess
import time
from pathlib import Path
from ..config import get_config
from datetime import datetime

def is_trivial_task(task_description):
    """Filter out trivial tasks (commands, simple queries)"""
    trivial_patterns = [
        'ace-cli', 'ace-', '/ace', 'ace_start', 'ace_finish',
        'what is', 'how to', 'list', 'show', 'check'
    ]
    task_lower = task_description.lower()
    for p in trivial_patterns:
        if p in task_lower:
            return True
    return False

def reconstruct_trajectory(transcript_path=None):
    """
    Heuristic to reconstruct trajectory from Antigravity logs/files.
    Since we don't have a PostToolUse hook, we have to parse what we can find.
    """
    trajectory = []
    
    # Strategy 1: If transcript_path (from Antigravity) is provided and exists
    if transcript_path and os.path.exists(transcript_path):
        try:
            # Placeholder: Parsing Logic would go here if we knew the format
            # For now, we return a simple placeholder to test the pipe
            pass
        except Exception:
            pass
            
    # Strategy 2: Look for local history files or artifacts
    # (Leaving this simple for the first iteration)
    
    return trajectory

def run(task_description, transcript_path=None):
    """
    Run post-task logic:
    1. Filter trivial tasks
    2. Reconstruct trajectory (Accumulator Gap fix)
    3. Call ace-cli learn
    4. Provide output to user
    """
    try:
        # Get config
        config = get_config()
        if not config['project']:
             print("⚠️ [ACE] No project context found. Run '/ace_configure' or 'ace-cli configure'")
             return

        # 1. Quality Gate
        if is_trivial_task(task_description):
            print("ℹ️  [ACE] Trivial task - skipping learning")
            return

        # 2. Reconstruct Trajectory
        # Native doesn't have the accumulator, so we do our best
        trajectory = reconstruct_trajectory(transcript_path)
        
        # Create a trace object compliant with ACE Paper
        trace = {
            "task": f"User request: {task_description}",
            "trajectory": trajectory,
            "result": {
                "success": True, # Optimistic default for now
                "output": "Task completed" 
            },
            "timestamp": datetime.now().isoformat()
        }

        # 3. Call ace-cli learn
        cmd = ['ace-cli', 'learn', '--stdin', '--json']
        
        env = dict(os.environ)
        if config['org']:
            env['ACE_ORG_ID'] = config['org']
        if config['project']:
            env['ACE_PROJECT_ID'] = config['project']
        if 'verbosity' in config:
             env['ACE_VERBOSITY'] = config['verbosity']

        try:
            result = subprocess.run(
                cmd,
                input=json.dumps(trace),
                text=True,
                capture_output=True,
                env=env,
                timeout=30 # Short timeout for learning
            )
            
            if result.returncode == 0:
                 # Parse JSON output if possible to give pretty stats
                 try:
                     resp = json.loads(result.stdout)
                     stats = resp.get('learning_statistics', {})
                     # (Simplification: just print success message for now)
                     print("✅ [ACE] Learning captured!")
                 except:
                     print("✅ [ACE] Learning captured!")
            else:
                 print(f"⚠️ [ACE] Learning capture failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            print("⚠️ [ACE] Learning capture timed out")

    except Exception as e:
        print(f"❌ [ACE] Post-task hook error: {e}")
