from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agentsmithy_server.agents.base_agent import BaseAgent
from agentsmithy_server.core.project import Project
from agentsmithy_server.tools import ToolExecutor, ToolFactory


class ProjectInspectorAgent(BaseAgent):
    """Agent that inspects a project using file tools and writes metadata via Project API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool_manager = ToolFactory.create_tool_manager()
        self.tool_executor = ToolExecutor(self.tool_manager, self.llm_provider)

    def get_default_system_prompt(self) -> str:
        return "Project Inspector Agent"

    def get_agent_name(self) -> str:
        return "project_inspector"

    async def inspect_and_save(self, project: Project) -> dict[str, Any]:
        project.ensure_state_dir()
        system = SystemMessage(
            content=(
                "You are a software project inspector.\n"
                "Goal: Inspect the repository to infer primary languages, frameworks, build tooling, test setup, and architectural structure.\n"
                "Constraints:\n"
                "- Use available tools (list_files, read_file, search_files).\n"
                "- STRICT: When you are DONE, you MUST call the tool `return_inspection` with the final JSON object. Do not print JSON directly.\n"
                "- Prefer scanning top-level files (package manifests, build files) and representative source directories.\n"
                "- The `return_inspection` tool enforces the exact schema: language_stats, dominant_languages, frameworks, package_managers, build_tools, has_tests, test_frameworks, architecture_hints.\n"
                "- Keep file reads minimal and targeted.\n"
            )
        )
        human = HumanMessage(
            content=(
                f"The project root is: {project.root}.\n"
                "Step plan: (1) list_files at root (non-recursive); (2) read_file manifests like requirements.txt, pyproject.toml;"
                " (3) if needed, do targeted list_files on 'src' or 'app' only; (4) when ready, call return_inspection with final JSON."
            )
        )

        result = await self.tool_executor.process_with_tools_async([system, human])
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

        return {"status": "ok", "saved": True}
