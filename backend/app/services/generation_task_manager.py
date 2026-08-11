import asyncio
from collections.abc import Awaitable, Callable


class GenerationTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[None]] = {}

    def start(self, task_id: int, operation: Callable[[], Awaitable[None]]) -> None:
        existing = self._tasks.get(task_id)
        if existing is not None and not existing.done():
            async def run_after_existing() -> None:
                await asyncio.gather(existing, return_exceptions=True)
                await operation()

            task = asyncio.create_task(run_after_existing(), name=f"image-generation-{task_id}")
        else:
            task = asyncio.create_task(operation(), name=f"image-generation-{task_id}")
        self._tasks[task_id] = task
        task.add_done_callback(lambda completed: self._discard(task_id, completed))

    async def cancel(self, task_id: int) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _discard(self, task_id: int, completed: asyncio.Task[None]) -> None:
        if self._tasks.get(task_id) is completed:
            self._tasks.pop(task_id, None)
