from __future__ import annotations

from bad_research.funnel._async import acall


async def test_acall_runs_sync_fn_in_thread_returns_value():
    def add(a, b):
        return a + b

    result = await acall(add, 2, 3)
    assert result == 5


async def test_acall_awaits_async_fn():
    async def amul(a, b):
        return a * b

    result = await acall(amul, 4, 5)
    assert result == 20


async def test_acall_passes_kwargs_to_sync_fn():
    def label(text, *, prefix="x"):
        return f"{prefix}:{text}"

    assert await acall(label, "hi", prefix="p") == "p:hi"


async def test_acall_passes_kwargs_to_async_fn():
    async def alabel(text, *, prefix="x"):
        return f"{prefix}:{text}"

    assert await acall(alabel, "hi", prefix="p") == "p:hi"


async def test_acall_does_not_block_event_loop_on_sync_call():
    # A blocking sync fn must run in a worker thread, not on the loop thread.
    import asyncio
    import threading

    loop_thread = threading.get_ident()
    seen: dict[str, int] = {}

    def blocking():
        seen["thread"] = threading.get_ident()
        return "done"

    # Run two blocking calls concurrently; if they were on the loop thread this
    # would serialize, but to_thread offloads them.
    results = await asyncio.gather(acall(blocking), acall(blocking))
    assert results == ["done", "done"]
    assert seen["thread"] != loop_thread
