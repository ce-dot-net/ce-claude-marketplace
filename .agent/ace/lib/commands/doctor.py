
import sys
import shutil
import subprocess
from ..config import get_config
from ..utils.formatting import print_error

def run():
    print("🩺 ACE Doctor - Health Diagnostic")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    checks = []
    
    # 1. CLI Check
    cli_path = shutil.which('ace-cli')
    if cli_path:
        try:
            ver = subprocess.check_output(['ace-cli', '--version']).decode().strip()
            checks.append(f"[1] CLI Availability........... ✅ PASS ({ver})")
        except:
            checks.append("[1] CLI Availability........... ⚠️  WARN (Error checking version)")
    else:
        checks.append("[1] CLI Availability........... ❌ FAIL (Not found)")
        
    # 2. Project Config
    config = get_config()
    if config and config.get('project'):
        checks.append(f"[2] Project Configuration...... ✅ PASS ({config['project']})")
    else:
        checks.append("[2] Project Configuration...... ❌ FAIL (Missing configuration)")
        
    # 3. Server Connection
    if cli_path and config.get('project'):
        env = {
            'ACE_ORG_ID': config['org'],
            'ACE_PROJECT_ID': config['project'],
            **subprocess.os.environ
        }
        try:
            subprocess.check_output(['ace-cli', 'status', '--json'], env=env, stderr=subprocess.DEVNULL)
            checks.append("[3] Server Connectivity........ ✅ PASS")
        except subprocess.CalledProcessError:
            checks.append("[3] Server Connectivity........ ❌ FAIL (Connection/Auth error)")
    else:
        checks.append("[3] Server Connectivity........ ⚪ SKIP")

    for check in checks:
        print(check)
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    if any("FAIL" in c for c in checks):
        print("Overall Health: 🔴 ISSUES FOUND")
        sys.exit(1)
    else:
        print("Overall Health: 🟢 HEALTHY")
