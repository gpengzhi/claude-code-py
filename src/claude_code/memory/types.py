"""Memory types.

Maps to src/memdir/memoryTypes.ts in the TypeScript codebase.
"""

from __future__ import annotations

from typing import Literal

MemoryType = Literal["user", "feedback", "project", "reference"]

MEMORY_TYPES: dict[MemoryType, str] = {
    "user": "Information about the user's role, goals, and preferences",
    "feedback": "Guidance on how to approach work (corrections and confirmations)",
    "project": "Non-derivable project context (decisions, deadlines, incidents)",
    "reference": "Pointers to external systems and resources",
}
