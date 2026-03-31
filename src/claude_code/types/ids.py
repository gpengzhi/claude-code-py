"""Branded ID types.

Maps to src/types/ids.ts in the TypeScript codebase.
In Python we use NewType for nominal typing (no runtime overhead).
"""

from typing import NewType

SessionId = NewType("SessionId", str)
AgentId = NewType("AgentId", str)
UUID = NewType("UUID", str)
