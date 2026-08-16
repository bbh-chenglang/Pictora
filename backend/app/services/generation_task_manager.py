import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4


class GenerationTaskManager:
    def __init__(
        self,
        max_concurrency: int = 4,
        *,
        max_active_tasks: int = 32,
        max_tasks_per_user: int = 4,
    ) -> None:
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._task_users: dict[int, int] = {}
        self._reservations: dict[int, int] = {}
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._max_active_tasks = max(1, max_active_tasks)
        self._max_tasks_per_user = max(1, max_tasks_per_user)
        self.worker_id = uuid4().hex

    def try_reserve(self, user_id: int) -> bool:
        self._prune_completed()
        active_count = len(self._task_users) + sum(self._reservations.values())
        user_count = sum(1 for owner_id in self._task_users.values() if owner_id == user_id)
        user_count += self._reservations.get(user_id, 0)
        if active_count >= self._max_active_tasks or user_count >= self._max_tasks_per_user:
            return False
        self._reservations[user_id] = self._reservations.get(user_id, 0) + 1
        return True

    def release_reservation(self, user_id: int) -> bool:
        count = self._reservations.get(user_id, 0)
        if count <= 0:
            return False
        if count == 1:
            self._reservations.pop(user_id, None)
        else:
            self._reservations[user_id] = count - 1
        return True

    def start(
        self,
        task_id: int,
        operation: Callable[[], Awaitable[None]],
        *,
        user_id: int,
    ) -> bool:
        if self._reservations.get(user_id, 0) <= 0:
            raise RuntimeError("Generation task capacity was not reserved")
        existing = self._tasks.get(task_id)
        if existing is not None and not existing.done():
            self.release_reservation(user_id)
            return False

        async def run_limited() -> None:
            async with self._semaphore:
                await operation()

        task = asyncio.create_task(run_limited(), name=f"image-generation-{task_id}")
        self.release_reservation(user_id)
        self._tasks[task_id] = task
        self._task_users[task_id] = user_id
        task.add_done_callback(lambda completed: self._discard(task_id, completed))
        return True

    def is_running(self, task_id: int) -> bool:
        task = self._tasks.get(task_id)
        return task is not None and not task.done()

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
        self._task_users.clear()
        self._reservations.clear()

    def _discard(self, task_id: int, completed: asyncio.Task[None]) -> None:
        if self._tasks.get(task_id) is completed:
            self._tasks.pop(task_id, None)
            self._task_users.pop(task_id, None)

    def _prune_completed(self) -> None:
        for task_id, task in list(self._tasks.items()):
            if task.done():
                self._discard(task_id, task)
