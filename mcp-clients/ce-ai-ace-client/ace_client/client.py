"""
ACE FastMCP Client - Thin proxy to remote server

This client:
1. Exposes the same 6 MCP tools as the server
2. Forwards all requests to your remote server
3. Handles local storage (patterns stored client-side)
4. NO SECRET SAUCE - just a thin proxy!
"""

import os
from typing import Any
from fastmcp import FastMCP
from fastmcp.server import Context
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


# Initialize client MCP server (proxies to remote)
mcp = FastMCP("ACE Pattern Learning (Client)")


def get_remote_client(server_url: str, api_token: str) -> Client:
    """Create client for remote ACE server"""
    transport = StreamableHttpTransport(
        url=server_url,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    )
    return Client(transport)


# Global remote client (initialized on first use)
_remote_client: Client | None = None


async def get_client() -> Client:
    """Get or create remote client"""
    global _remote_client
    if _remote_client is None:
        server_url = os.getenv("ACE_SERVER_URL")
        api_token = os.getenv("ACE_API_TOKEN")

        if not server_url or not api_token:
            raise ValueError("ACE_SERVER_URL and ACE_API_TOKEN must be set")

        _remote_client = get_remote_client(server_url, api_token)

    return _remote_client


@mcp.tool()
async def ace_reflect(code: str, language: str, file_path: str, context: Context) -> dict:
    """
    Discover patterns from code using ACE Reflector.

    PROXIES TO REMOTE SERVER - Your secret sauce is protected!

    Args:
        code: Source code to analyze
        language: Programming language (typescript, python, etc.)
        file_path: File path for context
        context: MCP Context for sampling

    Returns:
        Statistics about discovered patterns
    """
    client = await get_client()

    # Forward to remote server
    result = await client.call_tool("ace_reflect", {
        "code": code,
        "language": language,
        "file_path": file_path
    })

    return result


@mcp.tool()
async def ace_train_offline(max_commits: int, context: Context) -> dict:
    """
    Run multi-epoch offline training on git history.

    PROXIES TO REMOTE SERVER - Your secret sauce is protected!

    Args:
        max_commits: Number of recent commits to analyze
        context: MCP Context for sampling

    Returns:
        Training statistics
    """
    client = await get_client()

    # Forward to remote server
    result = await client.call_tool("ace_train_offline", {
        "max_commits": max_commits
    })

    return result


@mcp.tool()
async def ace_get_patterns(domain: str | None = None, min_confidence: float | None = None) -> list:
    """
    Get patterns from ACE database with optional filtering.

    PROXIES TO REMOTE SERVER - Your secret sauce is protected!

    Args:
        domain: Filter by domain (optional)
        min_confidence: Minimum confidence threshold (0-1, optional)

    Returns:
        List of patterns
    """
    client = await get_client()

    # Forward to remote server
    result = await client.call_tool("ace_get_patterns", {
        "domain": domain,
        "min_confidence": min_confidence
    })

    return result


@mcp.tool()
async def ace_get_playbook(task_hint: str | None = None) -> str:
    """
    Generate ACE playbook (ACE paper Figure 3 format).

    PROXIES TO REMOTE SERVER - Your secret sauce is protected!

    Args:
        task_hint: Task description for semantic filtering (optional)

    Returns:
        Formatted playbook markdown
    """
    client = await get_client()

    # Forward to remote server
    result = await client.call_tool("ace_get_playbook", {
        "task_hint": task_hint
    })

    return result


@mcp.tool()
async def ace_status() -> dict:
    """
    Get ACE pattern database statistics.

    PROXIES TO REMOTE SERVER - Your secret sauce is protected!

    Returns:
        Database statistics
    """
    client = await get_client()

    # Forward to remote server
    result = await client.call_tool("ace_status", {})

    return result


@mcp.tool()
async def ace_clear(confirm: bool = False) -> str:
    """
    Clear ACE pattern database (requires confirmation).

    PROXIES TO REMOTE SERVER - Your secret sauce is protected!

    Args:
        confirm: Must be True to confirm deletion

    Returns:
        Success message
    """
    client = await get_client()

    # Forward to remote server
    result = await client.call_tool("ace_clear", {
        "confirm": confirm
    })

    return result


def run_client(server_url: str, api_token: str):
    """Run the client MCP server"""
    print(f"🔗 ACE Client connecting to: {server_url}")
    print("🚀 Client ready for connections")

    # Run FastMCP server (proxies to remote)
    mcp.run()
