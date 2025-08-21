"""Context builder for RAG system."""

from typing import Any

from agentsmithy_server.config import settings
from agentsmithy_server.core.project import Project
from agentsmithy_server.rag.vector_store import VectorStoreManager


class ContextBuilder:
    """Build context from various sources for LLM."""

    def __init__(
        self,
        vector_store_manager: VectorStoreManager | None = None,
        project: Project | None = None,
        project_name: str | None = None,
    ):
        self.project: Project | None = None
        if vector_store_manager is not None:
            self.vector_store_manager = vector_store_manager
            # Try to capture project if manager exposes it
            self.project = getattr(vector_store_manager, "project", None)
        else:
            # Choose project by instance or by name from workspace
            if project is None:
                # If no explicit project provided, use workdir as current project
                from agentsmithy_server.core.project import get_current_project

                project = get_current_project()
                project.root.mkdir(parents=True, exist_ok=True)
            self.vector_store_manager = VectorStoreManager(project)
            self.project = project
        self.max_context_length = settings.max_context_length

    async def build_context(
        self,
        query: str,
        file_context: dict[str, Any] | None = None,
        k_documents: int = 4,
    ) -> dict[str, Any]:
        """Build context from query and file information."""
        context: dict[str, Any] = {
            "query": query,
            "current_file": None,
            "open_files": [],
            "relevant_documents": [],
            "total_context_length": 0,
        }

        # Inject project metadata if available
        if self.project is not None:
            metadata: dict[str, Any] = {}
            try:
                metadata = self.project.load_metadata()
            except Exception:
                metadata = {}
            context["project"] = {
                "name": self.project.name,
                "root": str(self.project.root),
                "metadata": metadata,
            }

        # Add dialog context (if supplied by caller)
        if file_context and file_context.get("dialog"):
            dialog_info = file_context["dialog"]
            # expect: {"id": str, "messages": list[{role, content, ts?}]}
            context["dialog"] = {
                "id": dialog_info.get("id"),
                "messages": dialog_info.get("messages", []),
            }

        # Add current file context
        if file_context and file_context.get("current_file"):
            current_file = file_context["current_file"]
            context["current_file"] = {
                "path": current_file.get("path", ""),
                "language": current_file.get("language", ""),
                "content": self._truncate_content(
                    current_file.get("content", ""), self.max_context_length // 3
                ),
                "selection": current_file.get("selection", ""),
            }
            context["total_context_length"] += len(context["current_file"]["content"])

        # Add open files context
        if file_context and file_context.get("open_files"):
            for i, file_info in enumerate(
                file_context["open_files"][: settings.max_open_files]
            ):
                if i >= settings.max_open_files:
                    break

                truncated_content = self._truncate_content(
                    file_info.get("content", ""),
                    self.max_context_length // (settings.max_open_files * 2),
                )

                context["open_files"].append(
                    {
                        "path": file_info.get("path", ""),
                        "language": file_info.get("language", ""),
                        "content": truncated_content,
                    }
                )
                context["total_context_length"] += len(truncated_content)

        # Search for relevant documents
        if query:
            # Keep RAG small during inspection to avoid token bloat
            relevant_docs = await self.vector_store_manager.similarity_search(
                query, k=min(k_documents, 2)
            )

            for doc in relevant_docs:
                remaining_space = (
                    self.max_context_length - context["total_context_length"]
                )
                if remaining_space <= 0:
                    break

                truncated_content = self._truncate_content(
                    doc.page_content, remaining_space
                )

                context["relevant_documents"].append(
                    {"content": truncated_content, "metadata": doc.metadata}
                )
                context["total_context_length"] += len(truncated_content)

        return context

    def _truncate_content(self, content: str, max_length: int) -> str:
        """Truncate content to maximum length."""
        if len(content) <= max_length:
            return content

        # Try to truncate at a reasonable boundary
        truncated = content[:max_length]

        # Find last complete line
        last_newline = truncated.rfind("\n")
        if last_newline > max_length * 0.8:  # If we're not losing too much
            truncated = truncated[:last_newline]

        return truncated + "\n... (truncated)"

    def format_context_for_prompt(self, context: dict[str, Any]) -> str:
        """Format context into a string for LLM prompt."""
        formatted_parts = []

        # Dialog history
        if context.get("dialog"):
            dlg = context["dialog"]
            formatted_parts.append(
                f"=== Dialog: {dlg.get('id','(none)')} (recent messages) ==="
            )
            messages = dlg.get("messages", [])
            # Print last N messages succinctly
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                formatted_parts.append(f"[{role}] {content}")
            formatted_parts.append("")

        # Project info
        if context.get("project"):
            pj = context["project"]
            formatted_parts.append(
                f"=== Project: {pj.get('name','')} ===\nRoot: {pj.get('root','')}"
            )
            analysis = (pj.get("metadata") or {}).get("analysis") or {}
            if analysis:
                dom_langs = analysis.get("dominant_languages") or []
                frameworks = analysis.get("frameworks") or []
                arch = analysis.get("architecture_hints") or []
                parts = []
                if dom_langs:
                    parts.append(f"Languages: {', '.join(dom_langs)}")
                if frameworks:
                    parts.append(f"Frameworks: {', '.join(frameworks)}")
                if arch:
                    parts.append(f"Architecture: {', '.join(arch)}")
                if parts:
                    formatted_parts.append("\n".join(parts))
            formatted_parts.append("")

        # Current file
        if context.get("current_file"):
            cf = context["current_file"]
            formatted_parts.append(
                f"=== Current File: {cf['path']} ({cf['language']}) ==="
            )
            if cf.get("selection"):
                formatted_parts.append(f"Selected Code:\n{cf['selection']}")
            formatted_parts.append(f"File Content:\n{cf['content']}")
            formatted_parts.append("")

        # Open files
        if context.get("open_files"):
            formatted_parts.append("=== Other Open Files ===")
            for file_info in context["open_files"]:
                formatted_parts.append(
                    f"\n--- {file_info['path']} ({file_info['language']}) ---"
                )
                formatted_parts.append(file_info["content"])
            formatted_parts.append("")

        # Relevant documents
        if context.get("relevant_documents"):
            formatted_parts.append("=== Relevant Context from Knowledge Base ===")
            for i, doc in enumerate(context["relevant_documents"], 1):
                formatted_parts.append(f"\n--- Document {i} ---")
                if doc.get("metadata", {}).get("source"):
                    formatted_parts.append(f"Source: {doc['metadata']['source']}")
                formatted_parts.append(doc["content"])
            formatted_parts.append("")

        return "\n".join(formatted_parts)
