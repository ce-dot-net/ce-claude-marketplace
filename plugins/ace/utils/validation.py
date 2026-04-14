"""
Validation utilities for ACE Orchestration Plugin

Example usage:
    >>> from validation import validate_pattern_id, is_valid_pattern_id
    >>>
    >>> # Valid pattern ID
    >>> is_valid = is_valid_pattern_id("ctx-abc123")
    >>> print(is_valid)
    True
    >>>
    >>> # Invalid pattern ID (no prefix)
    >>> is_valid, error = validate_pattern_id("invalid")
    >>> print(error)
    Pattern ID must start with 'ctx-' prefix
"""

import re
from typing import Optional


_UUID_RE = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)
_CTX_SUFFIX_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')


def validate_pattern_id(pattern_id: str) -> tuple[bool, Optional[str]]:
    """
    Validate ACE pattern ID format.

    Two accepted formats (both first-class, permanent per server contract):
      1. Legacy ctx- prefix: "ctx-" followed by lowercase alphanumeric,
         optionally with hyphen-separated segments (e.g. ctx-1234567890-abcd).
      2. UUID v4/v5 (post spec-06 Qdrant migration, 2026-03-29):
         8-4-4-4-12 hex, case-insensitive (server may send mixed case).

    Args:
        pattern_id: The pattern ID to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if pattern ID is valid, False otherwise
        - error_message: None if valid, error description if invalid

    Examples:
        >>> validate_pattern_id("ctx-abc123")
        (True, None)

        >>> validate_pattern_id("326df3ab-4d4c-5f16-8f63-3847cb2b9ac3")
        (True, None)

        >>> validate_pattern_id("invalid")[0]
        False

        >>> validate_pattern_id("ctx-ABC")[0]
        False
    """
    # Check if pattern_id is a string
    if not isinstance(pattern_id, str):
        return False, f"Pattern ID must be a string, got {type(pattern_id).__name__}"

    # Check if empty
    if not pattern_id:
        return False, "Pattern ID cannot be empty"

    # UUID v4/v5 path (case-insensitive) — post-Qdrant migration format
    if _UUID_RE.match(pattern_id):
        return True, None

    # Legacy ctx- prefix path
    if not pattern_id.startswith("ctx-"):
        return False, "Pattern ID must start with 'ctx-' prefix or be a UUID"

    suffix = pattern_id[4:]
    if not suffix:
        return False, "Pattern ID must have content after 'ctx-' prefix"

    if not _CTX_SUFFIX_RE.match(suffix):
        return False, "Pattern ID must contain only lowercase letters, numbers, and hyphens after 'ctx-' prefix"

    return True, None


def is_valid_pattern_id(pattern_id: str) -> bool:
    """
    Simple boolean check for pattern ID validity.

    Args:
        pattern_id: The pattern ID to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_pattern_id("ctx-abc123")
        True

        >>> is_valid_pattern_id("invalid")
        False
    """
    is_valid, _ = validate_pattern_id(pattern_id)
    return is_valid


def format_pattern_score(helpful: int, harmful: int) -> str:
    """
    Format pattern helpful/harmful scores for display.

    Args:
        helpful: Number of times pattern was marked helpful (positive score)
        harmful: Number of times pattern was marked harmful (negative score)

    Returns:
        Formatted string like "+8/-0" or "+5/-2"

    Examples:
        >>> format_pattern_score(8, 0)
        '+8/-0'

        >>> format_pattern_score(5, 2)
        '+5/-2'

        >>> format_pattern_score(0, 0)
        '+0/-0'
    """
    return f"+{helpful}/-{harmful}"
