"""Generic reactive store.

Maps to src/state/store.ts in the TypeScript codebase.
Minimal store with get/set/subscribe semantics.
"""

from __future__ import annotations

from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Store(Generic[T]):
    """A minimal reactive store with immutable update semantics."""

    def __init__(
        self,
        initial_state: T,
        on_change: Callable[[T, T], None] | None = None,
    ) -> None:
        self._state = initial_state
        self._listeners: set[Callable[[], None]] = set()
        self._on_change = on_change

    def get_state(self) -> T:
        """Get the current state."""
        return self._state

    def set_state(self, updater: Callable[[T], T]) -> None:
        """Update state using an immutable updater function."""
        prev = self._state
        next_state = updater(prev)
        if next_state is prev:
            return
        self._state = next_state
        if self._on_change:
            self._on_change(next_state, prev)
        for listener in list(self._listeners):
            listener()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to state changes. Returns an unsubscribe function."""
        self._listeners.add(listener)

        def unsubscribe() -> None:
            self._listeners.discard(listener)

        return unsubscribe
