from __future__ import annotations

import asyncio
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agentsmithy_server.agents.base_agent import BaseAgent
from agentsmithy_server.core.project import Project
from agentsmithy_server.core.project_runtime import set_scan_status
from agentsmithy_server.prompts import INSPECTOR_SYSTEM, build_inspector_human
from agentsmithy_server.tools import ToolExecutor
from agentsmithy_server.tools.build_registry import build_registry


class ProjectInspectorAgent(BaseAgent):
    """Agent that inspects a project using file tools and writes metadata via Project API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Build a minimal registry of builtin tools
        self.tool_manager = build_registry()
        self.executor = ToolExecutor(self.tool_manager, self.llm_provider)

    def get_default_system_prompt(self) -> str:
        return INSPECTOR_SYSTEM

    def get_agent_name(self) -> str:
        return "project_inspector"

    async def inspect_and_save(self, project: Project) -> dict[str, Any]:
        project.ensure_state_dir()
        # Mark scan started
        try:
            task = asyncio.current_task()
            task_id = str(id(task)) if task else None
            set_scan_status(
                project,
                "scanning",
                progress=0,
                pid=os.getpid(),
                task_id=task_id,
            )
        except Exception:
            pass
        system = SystemMessage(content=INSPECTOR_SYSTEM)
        human = HumanMessage(content=build_inspector_human(str(project.root)))

        result = await self.executor.process_with_tools_async([system, human])
        # Diagnostics for large tool traffic
        from agentsmithy_server.utils.logger import agent_logger as _alog

        tool_calls_diag = (
            result.get("tool_calls", []) if isinstance(result, dict) else []
        )
        _alog.info(
            "Inspector summary",
            tool_calls=len(tool_calls_diag),
            tools=[tc.get("name") for tc in tool_calls_diag if isinstance(tc, dict)],
        )
        if result.get("type") == "tool_response":
            # Expect a tool_result for return_inspection with validated JSON
            tool_results = result.get("tool_results", []) or []
            analysis = None
            for tr in tool_results:
                if tr.get("result", {}).get("type") == "inspection_result":
                    analysis = tr["result"].get("analysis")
                    break
            if analysis is None:
                raise ValueError(
                    "return_inspection tool was not called or returned invalid result"
                )
        else:
            raise ValueError("Inspector did not produce a tool_response")

        # Persist into project metadata
        try:

            # Already validated via tool schema
            analysis = analysis
            metadata = project.load_metadata() or {}
            metadata.update(
                {
                    "name": project.name,
                    "root": str(project.root),
                    "analysis": analysis,
                }
            )
            project.save_metadata(metadata)
            try:
                task = asyncio.current_task()
                task_id = str(id(task)) if task else None
                set_scan_status(
                    project,
                    "done",
                    progress=100,
                    pid=os.getpid(),
                    task_id=task_id,
                )
            except Exception:
                pass
        except Exception:
            # If parsing fails, store raw note (for debugging), but prefer strict analysis later
            metadata = project.load_metadata() or {}
            metadata.update(
                {
                    "name": project.name,
                    "root": str(project.root),
                    "analysis_note": "Inspector failed to return strict tool result",
                }
            )
            project.save_metadata(metadata)
            try:
                task = asyncio.current_task()
                task_id = str(id(task)) if task else None
                set_scan_status(
                    project,
                    "error",
                    error="strict tool result missing",
                    pid=os.getpid(),
                    task_id=task_id,
                )
            except Exception:
                pass

        return {"status": "ok", "saved": True}
