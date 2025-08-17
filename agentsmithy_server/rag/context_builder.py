"""Context builder for RAG system."""

from typing import Any

from agentsmithy_server.config import settings
from agentsmithy_server.rag.vector_store import VectorStoreManager


class ContextBuilder:
    """Build context from various sources for LLM."""

    def __init__(self, vector_store_manager: VectorStoreManager | None = None):
        self.vector_store_manager = vector_store_manager or VectorStoreManager()
        self.max_context_length = settings.max_context_length

    async def build_context(
        self,
        query: str,
        file_context: dict[str, Any] | None = None,
        k_documents: int = 4,
    ) -> dict[str, Any]:
        """Build context from query and file information."""
        context = {
            "query": query,
            "current_file": None,
            "open_files": [],
            "relevant_documents": [],
            "total_context_length": 0,
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
            relevant_docs = await self.vector_store_manager.similarity_search(
                query, k=k_documents
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
