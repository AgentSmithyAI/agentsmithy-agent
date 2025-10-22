from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.callbacks.manager import BaseCallbackManager
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool as LCBaseTool

SseCallback = Callable[[dict[str, Any]], Awaitable[None]]


class BaseTool(LCBaseTool, ABC):
    """Base class for server-side tools.

    Tools receive validated arguments and can emit SSE-compatible events via
    the provided callback. Subclasses should implement `arun`.
    """

    # Tool subclasses should declare: name: str, description: str, args_schema: type[BaseModel]

    # If True, executor must not persist tool output to history/storage
    # but should still pass inline results back to the model.
    ephemeral: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Ensure Pydantic/LangChain BaseTool initialization runs
        super().__init__(*args, **kwargs)
        # Internal, non-pydantic state
        self._sse_callback: SseCallback | None = None
        self._dialog_id: str | None = None
        self._project_root: str | None = None

    def set_sse_callback(self, callback: SseCallback | None) -> None:
        self._sse_callback = callback

    def set_dialog_id(self, dialog_id: str | None) -> None:
        self._dialog_id = dialog_id

    def set_project_root(self, project_root: str | None) -> None:
        self._project_root = project_root

    async def emit_event(self, event: dict[str, Any]) -> None:
        if self._sse_callback is not None:
            await self._sse_callback(event)

    # Match LangChain signature for compatibility and type-checking
    async def arun(
        self,
        tool_input: str | dict[Any, Any],
        verbose: bool | None = None,
        start_color: str | None = None,
        color: str | None = None,
        callbacks: list[BaseCallbackHandler] | BaseCallbackManager | None = None,
        *,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        run_name: str | None = None,
        run_id: UUID | None = None,
        config: RunnableConfig | None = None,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute tool asynchronously. Default calls LangChain _arun hook."""
        if not isinstance(tool_input, dict):
            raise TypeError(
                "tool_input must be a dict of arguments; callers should pass structured args via tool_input"
            )
        merged_kwargs: dict[Any, Any] = {**tool_input, **kwargs}
        return await self._arun(**merged_kwargs)

    # Provide a compatibility _run that bridges to async _arun when LangChain
    # chooses the sync path (it offloads _run via thread executor by default).
    # This lets tests and runtime succeed even if LC calls _arun -> _run.
    def _run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        import asyncio
        import inspect

        # Find the first _arun defined by a concrete tool subclass (not LCBaseTool)
        impl = None
        for cls in type(self).__mro__:
            if cls is BaseTool:
                continue
            # Avoid picking LCBaseTool._arun which offloads to _run again
            if cls.__name__ == "BaseTool" and cls.__module__.startswith(
                "langchain_core.tools"
            ):
                continue
            maybe = cls.__dict__.get("_arun")
            if maybe is not None:
                impl = maybe.__get__(self, type(self))  # bind to instance
                break

        if impl is None:
            raise NotImplementedError("Tool must implement async _arun")

        coro = impl(**kwargs)
        if inspect.iscoroutine(coro):
            return asyncio.run(coro)
        # If implementation returned a plain value, return as-is
        return coro
