"""Storage system for tool execution results.

Stores tool results separately from dialog history to enable lazy loading
and reduce LLM context usage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    """Manages storage of tool execution results.

    Results are stored as JSON files under:
    .agentsmithy/dialogs/{dialog_id}/tool_results/{tool_call_id}.json
    """

    def __init__(self, project: Project, dialog_id: str):
        self.project = project
        self.dialog_id = dialog_id
        self.storage_dir = project.dialogs_dir / dialog_id / "tool_results"

    def ensure_storage_dir(self) -> None:
        """Ensure the storage directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_result_path(self, tool_call_id: str) -> Path:
        """Get the file path for a tool result."""
        return self.storage_dir / f"{tool_call_id}.json"

    def _get_metadata_path(self, tool_call_id: str) -> Path:
        """Get the file path for tool result metadata."""
        return self.storage_dir / f"{tool_call_id}.meta.json"

    def _generate_summary(
        self, tool_name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> str:
        """Generate a human-readable summary of the tool execution."""
        # Tool-specific summary generation
        if tool_name == "read_file":
            file_path = args.get("target_file", "unknown")
            content = result.get("content", "")
            lines = content.count("\n") + 1 if content else 0
            return f"Read file: {file_path} ({lines} lines)"

        elif tool_name == "write_file":
            file_path = args.get("file_path", "unknown")
            content = args.get("contents", "")
            lines = content.count("\n") + 1 if content else 0
            return f"Wrote file: {file_path} ({lines} lines)"

        elif tool_name == "run_command":
            command = args.get("command", "unknown")
            exit_code = result.get("exit_code", -1)
            status = "success" if exit_code == 0 else f"failed (exit {exit_code})"
            return f"Ran command: {command} - {status}"

        elif tool_name == "search_files":
            pattern = args.get("pattern", "unknown")
            matches = result.get("matches", [])
            return f"Searched for '{pattern}' - found {len(matches)} matches"

        elif tool_name == "list_files":
            path = args.get("target_directory", ".")
            files = result.get("files", [])
            dirs = result.get("directories", [])
            return f"Listed {path} - {len(files)} files, {len(dirs)} directories"

        else:
            # Generic summary for unknown tools
            return f"Executed {tool_name}"

    async def store_result(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> ToolResultReference:
        """Store tool result and return reference.

        Args:
            tool_call_id: Unique identifier for this tool call
            tool_name: Name of the tool that was executed
            args: Arguments passed to the tool
            result: The tool execution result
            timestamp: When the tool was executed (defaults to now)

        Returns:
            Reference to the stored result
        """
        self.ensure_storage_dir()

        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Store the full result
        result_data = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "args": args,
            "result": result,
            "timestamp": timestamp.isoformat(),
        }

        result_path = self._get_result_path(tool_call_id)
        result_json = json.dumps(result_data, ensure_ascii=False, indent=2)
        result_path.write_text(result_json, encoding="utf-8")

        # Store metadata separately for quick access
        summary = self._generate_summary(tool_name, args, result)
        metadata = ToolResultMetadata(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            timestamp=timestamp.isoformat(),
            size_bytes=len(result_json.encode("utf-8")),
            summary=summary,
            error=result.get("error") if result.get("type") == "tool_error" else None,
        )

        metadata_path = self._get_metadata_path(tool_call_id)
        metadata_json = json.dumps(
            {
                "tool_call_id": metadata.tool_call_id,
                "tool_name": metadata.tool_name,
                "timestamp": metadata.timestamp,
                "size_bytes": metadata.size_bytes,
                "summary": metadata.summary,
                "error": metadata.error,
            },
            ensure_ascii=False,
            indent=2,
        )
        metadata_path.write_text(metadata_json, encoding="utf-8")

        agent_logger.info(
            "Stored tool result",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            size_bytes=metadata.size_bytes,
            summary=summary,
        )

        return ToolResultReference(
            storage_type="tool_results",
            dialog_id=self.dialog_id,
            tool_call_id=tool_call_id,
        )

    async def get_result(self, tool_call_id: str) -> dict[str, Any] | None:
        """Retrieve full tool result by ID.

        Returns:
            The complete tool result data, or None if not found
        """
        result_path = self._get_result_path(tool_call_id)
        if not result_path.exists():
            return None

        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            agent_logger.debug(
                "Retrieved tool result",
                tool_call_id=tool_call_id,
                tool_name=data.get("tool_name"),
            )
            return data
        except Exception as e:
            agent_logger.error(
                "Failed to load tool result",
                tool_call_id=tool_call_id,
                error=str(e),
            )
            return None

    async def get_metadata(self, tool_call_id: str) -> ToolResultMetadata | None:
        """Get only metadata without full result.

        This is much faster than loading the full result for large outputs.

        Returns:
            Tool result metadata, or None if not found
        """
        metadata_path = self._get_metadata_path(tool_call_id)
        if not metadata_path.exists():
            return None

        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            return ToolResultMetadata(**data)
        except Exception as e:
            agent_logger.error(
                "Failed to load tool metadata",
                tool_call_id=tool_call_id,
                error=str(e),
            )
            return None

    async def list_results(self) -> list[ToolResultMetadata]:
        """List all stored results for this dialog.

        Returns:
            List of metadata for all stored results
        """
        if not self.storage_dir.exists():
            return []

        results = []
        for meta_file in sorted(self.storage_dir.glob("*.meta.json")):
            tool_call_id = meta_file.stem.replace(".meta", "")
            metadata = await self.get_metadata(tool_call_id)
            if metadata:
                results.append(metadata)

        return results

    def get_truncated_preview(
        self, result: dict[str, Any], max_length: int = 200
    ) -> str:
        """Generate a truncated preview of the result for inline display.

        Args:
            result: The tool execution result
            max_length: Maximum length of the preview

        Returns:
            Truncated string representation of the result
        """
        # Handle specific result types
        if result.get("type") == "tool_error":
            return f"Error: {result.get('error', 'Unknown error')}"

        # For file content, show first few lines
        if "content" in result and isinstance(result["content"], str):
            content = result["content"]
            if len(content) > max_length:
                # Try to break at a newline
                newline_pos = content.find("\n", max_length // 2)
                if newline_pos > 0 and newline_pos < max_length:
                    return content[:newline_pos] + "\n... (truncated)"
                return content[:max_length] + "... (truncated)"
            return content

        # For other results, convert to JSON and truncate
        try:
            json_str = json.dumps(result, ensure_ascii=False, indent=2)
            if len(json_str) > max_length:
                return json_str[:max_length] + "... (truncated)"
            return json_str
        except Exception:
            return str(result)[:max_length]
