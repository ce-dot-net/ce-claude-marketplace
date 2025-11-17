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


def validate_pattern_id(pattern_id: str) -> tuple[bool, Optional[str]]:
    """
    Validate ACE pattern ID format.

    Pattern IDs should follow the format: "ctx-" prefix followed by
    alphanumeric characters (lowercase letters and numbers).

    Args:
        pattern_id: The pattern ID to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if pattern ID is valid, False otherwise
        - error_message: None if valid, error description if invalid

    Examples:
        >>> validate_pattern_id("ctx-abc123")
        (True, None)

        >>> validate_pattern_id("invalid")
        (False, "Pattern ID must start with 'ctx-' prefix")

        >>> validate_pattern_id("ctx-ABC")
        (False, "Pattern ID must contain only lowercase letters and numbers after 'ctx-' prefix")
    """
    # Check if pattern_id is a string
    if not isinstance(pattern_id, str):
        return False, f"Pattern ID must be a string, got {type(pattern_id).__name__}"

    # Check if empty
    if not pattern_id:
        return False, "Pattern ID cannot be empty"

    # Check for "ctx-" prefix
    if not pattern_id.startswith("ctx-"):
        return False, "Pattern ID must start with 'ctx-' prefix"

    # Extract the part after "ctx-"
    suffix = pattern_id[4:]

    # Check if suffix is empty
    if not suffix:
        return False, "Pattern ID must have content after 'ctx-' prefix"

    # Check if suffix contains only lowercase letters and numbers
    if not re.match(r'^[a-z0-9]+$', suffix):
        return False, "Pattern ID must contain only lowercase letters and numbers after 'ctx-' prefix"

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
