
import re

def is_trivial_task(task_description: str) -> bool:
    """
    Filter out trivial tasks that shouldn't trigger learning.
    
    Based on ACE v5.1.9+ logic:
    - Skips ACE commands
    - Skips simple queries
    - Skips read-only git/file operations
    - Skips greetings
    """
    if not task_description:
        return True
        
    trivial_patterns = [
        # ACE commands
        r'<command-message>ace[:\-]',
        r'ace:ace-',
        r'/ace-',
        r'ace-status',
        r'ace-patterns',
        r'ace-search',
        r'ace-learn',
        r'ace-configure',
        r'ace-bootstrap',
        r'ace-clear',
        r'ace-doctor',
        r'ace-export',
        r'ace-import',
        r'ace-top',
        r'ace-tune',
        r'ace-delta',

        # Simple queries
        r'^(what|how|why|where|when|can you|could you|would you)\s.*\?$',
        r'^(list|show|display|print|view|see)\s',
        r'^(check|status|version|help|info)\s*$',

        # Git status checks
        r'git\s+(status|log|diff|branch|show)\s*$',

        # File listing
        r'^ls\s',
        r'^cat\s',
        r'^head\s',
        r'^tail\s',

        # Greetings
        r'^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure)\s*$',
        
        # System messages
        r'caveat:.*messages below were generated',
        r'^plugin\s*$',
        r'/plugin',
    ]

    task_lower = task_description.lower()
    for pattern in trivial_patterns:
        if re.search(pattern, task_lower, re.IGNORECASE):
            return True
            
    return False
