"""Storage system for tool execution results.

Stores tool results in a dedicated SQLite table (per project) and keeps
references in dialog history to reduce LLM context usage while allowing
on-demand retrieval of full results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

# SQLAlchemy ORM setup
from sqlalchemy import select
from sqlalchemy.engine import Engine

from agentsmithy_server.core.dialog_history import DialogHistory
from agentsmithy_server.db import BaseORM, ToolResultORM
from agentsmithy_server.db.base import get_engine, get_session
from agentsmithy_server.utils.logger import agent_logger

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


@dataclass
class ToolResultMetadata:
    """Metadata about a stored tool result."""

    tool_call_id: str
    tool_name: str
    timestamp: str
    size_bytes: int
    summary: str | None = None
    error: str | None = None


@dataclass
class ToolResultReference:
    """Reference to a stored tool result."""

    storage_type: str = "tool_results"
    dialog_id: str = ""
    tool_call_id: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {
            "storage_type": self.storage_type,
            "dialog_id": self.dialog_id,
            "tool_call_id": self.tool_call_id,
        }


class ToolResultsStorage:
    """Manages storage of tool execution results using SQLAlchemy ORM.

    Data is stored in the same SQLite database as dialog history and accessed
    via ORM models. Rows are scoped by `dialog_id`.
    """

    def __init__(self, project: Project, dialog_id: str, engine: Engine | None = None):
        self.project = project
        self.dialog_id = dialog_id
        # Reuse the same SQLite file as dialog history
        self._db_path: Path = DialogHistory(project, dialog_id).db_path
        self._engine: Engine | None = engine

    # --- SQLAlchemy ORM model definitions ---

    def _get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine(self._db_path)
        return self._engine

    def _ensure_db(self) -> None:
        """Ensure the SQLite tables exist using SQLAlchemy metadata.

        This is safe to call multiple times; it only creates missing tables.
        """
        engine = self._get_engine()
        BaseORM.metadata.create_all(engine)

    # ---------- Storage logic (class-owned) ----------

    def _generate_summary(
        self, tool_name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> str:
        # Tool-specific summary generation
        if tool_name == "read_file":
            file_path = args.get("path", args.get("target_file", "unknown"))
            content = result.get("content", "")
            lines = content.count("\n") + 1 if content else 0
            return f"Read file: {file_path} ({lines} lines)"
        elif tool_name == "write_file" or tool_name == "write_to_file":
            file_path = args.get("path", args.get("file_path", "unknown"))
            content = args.get("content", args.get("contents", ""))
            lines = content.count("\n") + 1 if content else 0
            return f"Wrote file: {file_path} ({lines} lines)"
        elif tool_name == "run_command":
            command = args.get("command", "unknown")
            exit_code = result.get("exit_code", -1)
            status = "success" if exit_code == 0 else f"failed (exit {exit_code})"
            return f"Ran command: {command} - {status}"
        elif tool_name == "search_files":
            pattern = args.get("regex", args.get("pattern", "unknown"))
            matches = result.get("matches", [])
            return f"Searched for '{pattern}' - found {len(matches)} matches"
        elif tool_name == "list_files":
            path = args.get("path", args.get("target_directory", "."))
            files = result.get("files", [])
            dirs = result.get("directories", [])
            return f"Listed {path} - {len(files)} files, {len(dirs)} directories"
        else:
            return f"Executed {tool_name}"

    async def store_result(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> ToolResultReference:
        self._ensure_db()
        if timestamp is None:
            timestamp = datetime.now(UTC)
        packed_args = json.dumps(args, ensure_ascii=False)
        packed_result = json.dumps(result, ensure_ascii=False)
        summary = self._generate_summary(tool_name, args, result)
        size_bytes = len(packed_result.encode("utf-8"))
        error_value = (
            result.get("error") if result.get("type") == "tool_error" else None
        )
        engine = self._get_engine()
        with get_session(engine) as session:
            session.merge(
                ToolResultORM(
                    tool_call_id=tool_call_id,
                    dialog_id=self.dialog_id,
                    tool_name=tool_name,
                    args_json=packed_args,
                    result_json=packed_result,
                    timestamp=timestamp.isoformat(),
                    size_bytes=size_bytes,
                    summary=summary,
                    error=error_value,
                )
            )
            session.commit()

        agent_logger.info(
            "Stored tool result",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            size_bytes=size_bytes,
            summary=summary,
        )

        return ToolResultReference(
            storage_type="tool_results",
            dialog_id=self.dialog_id,
            tool_call_id=tool_call_id,
        )

    async def get_result(self, tool_call_id: str) -> dict[str, Any] | None:
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = select(
                    ToolResultORM.tool_name,
                    ToolResultORM.args_json,
                    ToolResultORM.result_json,
                    ToolResultORM.timestamp,
                ).where(ToolResultORM.tool_call_id == tool_call_id)
                row = session.execute(stmt).first()
                if not row:
                    return None
                tool_name, args_json, result_json, ts = row
                return {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "args": json.loads(args_json or "{}"),
                    "result": json.loads(result_json or "{}"),
                    "timestamp": ts,
                }
        except Exception as e:
            agent_logger.error(
                "Failed to load tool result", tool_call_id=tool_call_id, error=str(e)
            )
            return None

    async def get_metadata(self, tool_call_id: str) -> ToolResultMetadata | None:
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = select(
                    ToolResultORM.tool_name,
                    ToolResultORM.timestamp,
                    ToolResultORM.size_bytes,
                    ToolResultORM.summary,
                    ToolResultORM.error,
                ).where(ToolResultORM.tool_call_id == tool_call_id)
                row = session.execute(stmt).first()
                if not row:
                    return None
                tool_name, ts, size_bytes, summary, error = row
                return ToolResultMetadata(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    timestamp=ts,
                    size_bytes=int(size_bytes or 0),
                    summary=summary,
                    error=error,
                )
        except Exception as e:
            agent_logger.error(
                "Failed to load tool metadata", tool_call_id=tool_call_id, error=str(e)
            )
            return None

    async def list_results(self) -> list[ToolResultMetadata]:
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = (
                    select(ToolResultORM.tool_call_id)
                    .where(ToolResultORM.dialog_id == self.dialog_id)
                    .order_by(ToolResultORM.timestamp.asc())
                )
                rows = session.execute(stmt).all()
            results: list[ToolResultMetadata] = []
            for (tcid,) in rows:
                md = await self.get_metadata(tcid)
                if md:
                    results.append(md)
            return results
        except Exception as e:
            agent_logger.error("Failed to list tool results", error=str(e))
            return []

    def get_truncated_preview(
        self, result: dict[str, Any], max_length: int = 500
    ) -> str:
        if result.get("type") == "tool_error":
            return f"Error: {result.get('error', 'Unknown error')}"
        if "content" in result and isinstance(result["content"], str):
            content = result["content"]
            if len(content) > max_length:
                lines = content.split("\n")
                preview_lines: list[str] = []
                current_length = 0
                for line in lines:
                    if current_length + len(line) + 1 > max_length and preview_lines:
                        break
                    preview_lines.append(line)
                    current_length += len(line) + 1
                if preview_lines:
                    preview = "\n".join(preview_lines)
                    if len(lines) > len(preview_lines):
                        preview += (
                            f"\n... ({len(lines) - len(preview_lines)} more lines)"
                        )
                    return preview
                return content[:max_length] + "... (truncated)"
            return content
        try:
            json_str = json.dumps(result, ensure_ascii=False, indent=2)
            if len(json_str) > max_length:
                return json_str[:max_length] + "... (truncated)"
            return json_str
        except Exception:
            return str(result)[:max_length]
