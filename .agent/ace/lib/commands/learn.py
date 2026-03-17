
import sys
import subprocess
import json
from ..config import get_config
from ..utils.formatting import print_error, print_warning
from ..utils.trivial_filter import is_trivial_task

def run(task, trajectory, success):
    # Quality Gate: Check for trivial tasks
    if is_trivial_task(task):
        print_warning(f"Skipping learning for trivial task: {task[:50]}...")
        return

    config = get_config()
    
    if not config['org'] or not config['project']:
        print_error("Project context not found. Run 'adapter.py configure' first.")
        sys.exit(1)
        
    env = {
        'ACE_ORG_ID': config['org'],
        'ACE_PROJECT_ID': config['project'],
        'ACE_VERBOSITY': config.get('verbosity', 'detailed'),
        **subprocess.os.environ
    }
    
    try:
        # Parse trajectory if it's a JSON string
        try:
            traj_data = json.loads(trajectory)
        except:
            traj_data = trajectory

        payload = {
            "task": task,
            "trajectory": traj_data,
            "result": {
                "success": str(success).lower() == 'true',
                "output": "Task completed"
            }
        }

        subprocess.run(
            ['ace-cli', 'learn', '--stdin', '--json'],
            input=json.dumps(payload),
            text=True,
            env=env,
            check=True
        )
    except subprocess.CalledProcessError:
        sys.exit(1)
    except FileNotFoundError:
        print_error("ace-cli not found. Install with: npm install -g @ace-sdk/cli")
        sys.exit(1)
