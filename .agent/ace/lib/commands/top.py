
import sys
import subprocess
import json
from ..config import get_config
from ..utils.formatting import print_error

def run(limit="10"):
    config = get_config()
    
    if not config['org'] or not config['project']:
        print_error("Project context not found. Run 'adapter.py configure' first.")
        sys.exit(1)
        
    env = {
        'ACE_ORG_ID': config['org'],
        'ACE_PROJECT_ID': config['project'],
        **subprocess.os.environ
    }
    
    import tempfile
    import os

    try:
        # Create temp file
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tf:
            temp_path = tf.name

        # Export to temp file (logs go to stdout/stderr, JSON goes to file)
        subprocess.run(
            ['ace-cli', 'export', '--output', temp_path], 
            env=env, 
            stdout=subprocess.DEVNULL, # Suppress logs
            stderr=subprocess.DEVNULL,
            check=True
        )
        
        # Read JSON from file
        with open(temp_path, 'r') as f:
            data = json.load(f)
            
        # Clean up
        os.unlink(temp_path)
        
        # Collect all patterns from all sections
        all_patterns = []
        for section in ['strategies_and_hard_rules', 'snippets', 'troubleshooting', 'apis']:
            if section in data:
                all_patterns.extend(data[section])
        
        # Sort by confidence (descending)
        all_patterns.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        # Take top N
        limit_int = int(limit)
        top_patterns = all_patterns[:limit_int]
        
        print(f"🏆 Top {len(top_patterns)} Patterns (by confidence)")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for p in top_patterns:
            conf = p.get('confidence', 0)
            content = p.get('content', '')
            if len(content) > 80:
                content = content[:77] + '...'
            print(f"[{conf:.2f}] {content}")
            
    except json.JSONDecodeError:
        print_error("Failed to decode patterns JSON")
        if os.path.exists(temp_path):
            os.unlink(temp_path)
            
    except subprocess.CalledProcessError:
        sys.exit(1)
    except FileNotFoundError:
        print_error("ace-cli not found. Install with: npm install -g @ace-sdk/cli")
        sys.exit(1)
