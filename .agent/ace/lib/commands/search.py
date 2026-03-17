
import sys
import subprocess
from ..config import get_config
from ..utils.formatting import print_error

def run(query):
    config = get_config()
    
    if not config['org'] or not config['project']:
        print_error("Project context not found. Run 'adapter.py configure' first.")
        sys.exit(1)
        
    env = {
        'ACE_ORG_ID': config['org'],
        'ACE_PROJECT_ID': config['project'],
        **subprocess.os.environ
    }
    
    try:
        subprocess.run(['ace-cli', 'search', query], env=env, check=True)
    except subprocess.CalledProcessError:
        sys.exit(1)
    except FileNotFoundError:
        print_error("ace-cli not found. Install with: npm install -g @ace-sdk/cli")
        sys.exit(1)
