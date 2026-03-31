"""Color themes for the TUI.

Maps to the theme system in the TypeScript codebase.
Provides dark and light theme color palettes.
"""

from __future__ import annotations

# Theme colors matching Claude Code's aesthetic
DARK_THEME = {
    "bg": "#1a1a2e",
    "fg": "#e0e0e0",
    "accent": "#c084fc",         # Purple accent (Claude brand)
    "accent_dim": "#7c3aed",
    "success": "#4ade80",
    "error": "#f87171",
    "warning": "#fbbf24",
    "muted": "#6b7280",
    "border": "#374151",
    "surface": "#1f2937",
    "user_msg": "#e0e0e0",
    "assistant_msg": "#c084fc",
    "tool_use": "#60a5fa",
    "tool_result": "#6b7280",
    "thinking": "#fbbf24",
    "permission": "#f59e0b",
}

LIGHT_THEME = {
    "bg": "#ffffff",
    "fg": "#1f2937",
    "accent": "#7c3aed",
    "accent_dim": "#a78bfa",
    "success": "#16a34a",
    "error": "#dc2626",
    "warning": "#d97706",
    "muted": "#9ca3af",
    "border": "#d1d5db",
    "surface": "#f3f4f6",
    "user_msg": "#1f2937",
    "assistant_msg": "#7c3aed",
    "tool_use": "#2563eb",
    "tool_result": "#6b7280",
    "thinking": "#d97706",
    "permission": "#d97706",
}
