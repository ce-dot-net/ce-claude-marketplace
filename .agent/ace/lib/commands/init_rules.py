
import os
from pathlib import Path
from ..utils.formatting import print_success, print_warning, print_error

ACE_RULES_CONTENT = """
## ACE Workflow (Automatic Context Engineering)

The agent **MUST** follow this workflow for every coding task:

1.  **Before starting work**:
    - ALWAYS run `.agent/ace/adapter.py start "<concise task description>"` to search for relevant patterns and context.
    - Read the patterns found to guide your implementation.

2.  **During work**:
    - If you shift focus to a new domain (e.g., from frontend to backend), run `start` again with the new context.

3.  **After completing work**:
    - ALWAYS run `.agent/ace/adapter.py finish "<concise task description>"` to capture learning.
    - This captures the tools you used and the outcome (success/failure) to improve future suggestions.

## General Guidelines

- Use the Native ACE Pack located in `.agent/ace/`.
- If `ace-cli` is missing, run `.agent/ace/install.sh` to install it.
- **Do not ask for permission** to run these commands; they are part of your core operating procedure.
"""

def run():
    """
    Initialize or update .antigravity/rules.md with ACE instructions.
    """
    try:
        antigravity_dir = Path(".antigravity")
        antigravity_dir.mkdir(exist_ok=True)
        
        rules_file = antigravity_dir / "rules.md"
        
        if not rules_file.exists():
            rules_file.write_text("# Antigravity Agent Rules\n" + ACE_RULES_CONTENT)
            print_success(f"Created {rules_file} with ACE instructions.")
            return

        content = rules_file.read_text()
        
        if "ACE Workflow" in content:
            print_success(f"ACE instructions already present in {rules_file}.")
        else:
            # Append to existing file
            with rules_file.open("a") as f:
                f.write("\n" + ACE_RULES_CONTENT)
            print_success(f"Appended ACE instructions to {rules_file}.")
            
    except Exception as e:
        print_error(f"Failed to initialize rules: {e}")
