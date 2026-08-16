import asyncio

import pytest

from app.services.generation_task_manager import GenerationTaskManager


@pytest.mark.asyncio
async def test_generation_task_manager_enforces_global_and_per_user_capacity() -> None:
    manager = GenerationTaskManager(
        max_concurrency=1,
        max_active_tasks=2,
        max_tasks_per_user=1,
    )

    assert manager.try_reserve(1)
    assert not manager.try_reserve(1)
    assert manager.try_reserve(2)
    assert not manager.try_reserve(3)
    assert manager.release_reservation(1)
    assert manager.try_reserve(3)
    await manager.shutdown()


@pytest.mark.asyncio
async def test_generation_task_manager_releases_capacity_when_task_finishes() -> None:
    manager = GenerationTaskManager(
        max_concurrency=1,
        max_active_tasks=1,
        max_tasks_per_user=1,
    )
    release = asyncio.Event()

    async def operation() -> None:
        await release.wait()

    assert manager.try_reserve(1)
    assert manager.start(10, operation, user_id=1)
    assert not manager.try_reserve(1)

    release.set()
    while manager.is_running(10):
        await asyncio.sleep(0)

    assert manager.try_reserve(1)
    assert manager.release_reservation(1)
    await manager.shutdown()


@pytest.mark.asyncio
async def test_generation_task_manager_requires_a_reservation_before_start() -> None:
    manager = GenerationTaskManager()

    with pytest.raises(RuntimeError, match="capacity was not reserved"):
        manager.start(10, lambda: asyncio.sleep(0), user_id=1)

    await manager.shutdown()
