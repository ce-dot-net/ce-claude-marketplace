
import sys

def print_error(message):
    print(f"❌ {message}", file=sys.stderr)

def print_success(message):
    print(f"✅ {message}")

def print_warning(message):
    print(f"⚠️  {message}")

def print_info(message):
    print(f"ℹ️  {message}")
