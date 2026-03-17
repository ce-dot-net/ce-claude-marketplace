#!/usr/bin/env python3
import sys
from pathlib import Path

# Add current directory to path so we can import the package
# We need to add the parent of 'lib' which is '.agent/ace'
sys.path.insert(0, str(Path(__file__).parent))

try:
    from lib.main import main
except ImportError:
    # Fallback for when running from root
    sys.path.insert(0, str(Path.cwd() / '.agent' / 'ace'))
    from lib.main import main

if __name__ == "__main__":
    main()
