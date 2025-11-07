"""Background task manager for API endpoints.

Provides a centralized way to manage background tasks with proper lifecycle:
- Track all running background tasks
- Graceful shutdown with timeout
- Automatic cleanup of completed tasks
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from agentsmithy.utils.logger import get_logger

logger = get_logger("api.background")


class BackgroundTaskManager:
    """Manages background tasks with proper lifecycle and cleanup."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()
        self._shutdown_event: asyncio.Event | None = None

    def set_shutdown_event(self, event: asyncio.Event) -> None:
        """Set the shutdown event for graceful termination."""
        self._shutdown_event = event

    def create_task(
        self, coro: Coroutine[Any, Any, None], name: str | None = None
    ) -> None:
        """Create a background task and track it.

        This uses asyncio.ensure_future() to truly defer execution until after
        the current coroutine yields control, preventing the task from blocking
        the endpoint response.

        Args:
            coro: Coroutine to run in background
            name: Optional name for the task (for debugging)
        """

        # Wrap in async function to defer execution
        async def _wrapped_task():
            """Wrapper to ensure task doesn't execute before endpoint returns."""
            # Yield control immediately to let endpoint return response first
            await asyncio.sleep(0)
            try:
                await coro
            except Exception as e:
                logger.error(
                    "Background task failed",
                    task_name=name or "unnamed",
                    error=str(e),
                    exc_info=True,
                )

        # Use ensure_future for true fire-and-forget
        task: asyncio.Task[None] = asyncio.ensure_future(_wrapped_task())
        if name:
            task.set_name(name)

        self._tasks.add(task)

        # Auto-cleanup when task completes
        task.add_done_callback(self._tasks.discard)

        logger.debug(
            "Scheduled background task",
            task_name=name or "unnamed",
            active_tasks=len(self._tasks),
        )

    def create_thread_task(
        self, coro: Coroutine[Any, Any, None], name: str | None = None
    ) -> None:
        """Run an async coroutine in a dedicated thread with its own event loop.

        This completely isolates heavy async jobs (CPU/disk bound) from the main
        server event loop to avoid any accidental starvation of request handling.

        Args:
            coro: Coroutine to execute in a separate thread/event loop
            name: Optional task name for debugging
        """

        async def _wrapped_thread_job() -> None:
            # Let the endpoint return first
            await asyncio.sleep(0)

            def _runner() -> None:
                try:
                    # Run the coroutine in a fresh event loop bound to this thread
                    asyncio.run(coro)
                except Exception as e:  # pragma: no cover - safety logging
                    logger.error(
                        "Background thread task failed",
                        task_name=name or "unnamed",
                        error=str(e),
                        exc_info=True,
                    )

            # Offload to a worker thread
            await asyncio.to_thread(_runner)

        task: asyncio.Task[None] = asyncio.ensure_future(_wrapped_thread_job())
        if name:
            task.set_name(name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.debug(
            "Scheduled background thread task",
            task_name=name or "unnamed",
            active_tasks=len(self._tasks),
        )

    async def shutdown(self, timeout: float = 5.0) -> None:
        """Gracefully shutdown all background tasks.

        Args:
            timeout: Maximum time to wait for tasks to complete (seconds)
        """
        if not self._tasks:
            logger.debug("No background tasks to shutdown")
            return

        logger.info("Shutting down background tasks", count=len(self._tasks))

        # Wait for tasks to complete with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=timeout,
            )
            logger.info("All background tasks completed gracefully")
        except TimeoutError:
            # Cancel remaining tasks
            logger.warning(
                "Background tasks timeout, cancelling remaining tasks",
                remaining=len([t for t in self._tasks if not t.done()]),
            )
            for task in self._tasks:
                if not task.done():
                    task.cancel()

            # Wait a bit for cancellation to propagate
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=True),
                    timeout=1.0,
                )
            except TimeoutError:
                logger.error("Some tasks did not respond to cancellation")

        self._tasks.clear()
        logger.info("Background task shutdown complete")

    @property
    def active_count(self) -> int:
        """Return number of active background tasks."""
        return len([t for t in self._tasks if not t.done()])

    @property
    def has_tasks(self) -> bool:
        """Return True if there are any tracked tasks (completed or pending)."""
        return len(self._tasks) > 0

    def cancel_all(self) -> None:
        """Cancel all pending tasks immediately (for testing/cleanup).

        This is a synchronous operation that cancels all tasks without waiting.
        Use shutdown() for graceful cleanup with timeout.
        """
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
        self._tasks.clear()


# Global instance
_background_manager: BackgroundTaskManager | None = None


def get_background_manager() -> BackgroundTaskManager:
    """Get or create the global background task manager."""
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundTaskManager()
    return _background_manager
