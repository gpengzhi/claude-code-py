"""Tests for the reactive store."""

from claude_code.state.store import Store


def test_store_initial_state():
    store: Store[int] = Store(42)
    assert store.get_state() == 42


def test_store_set_state():
    store: Store[int] = Store(0)
    store.set_state(lambda s: s + 1)
    assert store.get_state() == 1


def test_store_no_update_on_same_reference():
    """set_state should skip if updater returns the same object."""
    calls: list[int] = []
    store: Store[list[int]] = Store(calls)
    store.subscribe(lambda: None)

    listener_called = False

    def listener():
        nonlocal listener_called
        listener_called = True

    store.subscribe(listener)
    store.set_state(lambda s: s)  # Same reference
    assert not listener_called


def test_store_subscribe():
    store: Store[int] = Store(0)
    values: list[int] = []

    unsub = store.subscribe(lambda: values.append(store.get_state()))
    store.set_state(lambda s: 1)
    store.set_state(lambda s: 2)

    assert values == [1, 2]

    unsub()
    store.set_state(lambda s: 3)
    assert values == [1, 2]  # No more updates


def test_store_on_change():
    changes: list[tuple[int, int]] = []
    store: Store[int] = Store(0, on_change=lambda new, old: changes.append((new, old)))

    store.set_state(lambda s: 5)
    store.set_state(lambda s: 10)

    assert changes == [(5, 0), (10, 5)]
