
import os
from pathlib import Path
from ..config import get_config

def run():
    """
    Clean up temporary session files:
    - /tmp/ace-session-*.txt
    - /tmp/ace-domains-*.json
    """
    count = 0
    try:
        config = get_config()
        project = config.get('project')
        
        # Files to remove
        files = []
        if project:
            files.append(Path(f"/tmp/ace-session-{project}.txt"))
            files.append(Path(f"/tmp/ace-domains-{project}.json"))
            files.append(Path(f"/tmp/ace-disabled-{project}.flag"))
        
        # Also clean generic patterns
        for f in Path('/tmp').glob('ace-session-*.txt'):
            files.append(f)
            
        for f in set(files):
            if f.exists():
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
                    
        print(f"✅ [ACE] Cleanup complete. Removed {count} temporary files.")
        
    except Exception as e:
        print(f"❌ [ACE] Cleanup failed: {e}")
