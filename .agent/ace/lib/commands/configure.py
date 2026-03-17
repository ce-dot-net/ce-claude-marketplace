
import sys
from ..config import save_project_config
from ..utils.formatting import print_success, print_error

def run(org_id, project_id):
    success, result = save_project_config(org_id, project_id)
    if success:
        print_success(f"Configuration saved to {result}")
    else:
        print_error(f"Error saving configuration: {result}")
        sys.exit(1)
