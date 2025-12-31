"""
Utility functions for ANSI terminal rendering.
"""

import re


"""
Remove ANSI escape sequences from text.

Args:
    text: Text that may contain ANSI codes

Returns:
    Text with ANSI codes removed
"""
def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


"""
Get the visible length of text (excluding ANSI codes).

Args:
    text: Text that may contain ANSI codes

Returns:
    Visible character count
"""
def visible_length(text: str) -> int:
    return len(strip_ansi(text))
