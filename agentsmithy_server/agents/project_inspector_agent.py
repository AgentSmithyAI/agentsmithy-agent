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

    async def inspect_and_save(self, project: Project) -> dict[str, Any]:
        project.ensure_state_dir()

        system = SystemMessage(
            content=(
                "You are a software project inspector.\n"
                "Goal: Inspect the repository to infer primary languages, frameworks, build tooling, test setup, and architectural structure.\n"
                "Constraints:\n"
                "- Use available tools (list_files, read_file, search_files).\n"
                "- Prefer scanning top-level files (package manifests, build files) and representative source directories.\n"
                "- Return a compact JSON object with fields: language_stats, dominant_languages, frameworks, package_managers, build_tools, has_tests, test_frameworks, architecture_hints.\n"
                "- Keep file reads minimal and targeted.\n"
            )
        )
        human = HumanMessage(
            content=(
                f"The project root is: {project.root}. \n"
                "Begin by listing the top-level directory and inferring languages/frameworks from manifest files."
            )
        )

        result = await self.tool_executor.process_with_tools_async([system, human])
        if result.get("type") == "tool_response":
            content = result.get("content", "").strip() or "{}"
        else:
            content = result.get("content", "").strip() or "{}"

        # Persist into project metadata
        try:
            import json

            analysis = json.loads(content)
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
            # If JSON parsing fails, still save as raw note for later refinement
            metadata = project.load_metadata() or {}
            metadata.update(
                {
                    "name": project.name,
                    "root": str(project.root),
                    "analysis_note": content,
                }
            )
            project.save_metadata(metadata)

        return {"status": "ok", "saved": True}
