"""
ACE FastMCP Client - Entry point

Thin MCP client that proxies requests to remote ACE server.
"""

import os
import sys
from .client import run_client


def main():
    """Main entry point for ACE client"""
    # Check required environment variables
    server_url = os.getenv("ACE_SERVER_URL")
    api_token = os.getenv("ACE_API_TOKEN")

    if not server_url:
        print("❌ Error: ACE_SERVER_URL environment variable not set", file=sys.stderr)
        print("", file=sys.stderr)
        print("Set it in your plugin.json:", file=sys.stderr)
        print('  "env": {', file=sys.stderr)
        print('    "ACE_SERVER_URL": "https://ace.your-domain.com/mcp"', file=sys.stderr)
        print('  }', file=sys.stderr)
        sys.exit(1)

    if not api_token:
        print("❌ Error: ACE_API_TOKEN environment variable not set", file=sys.stderr)
        print("", file=sys.stderr)
        print("Set it in your plugin.json:", file=sys.stderr)
        print('  "env": {', file=sys.stderr)
        print('    "ACE_API_TOKEN": "${ACE_API_TOKEN}"', file=sys.stderr)
        print('  }', file=sys.stderr)
        sys.exit(1)

    # Run the client
    run_client(server_url, api_token)


if __name__ == "__main__":
    main()
