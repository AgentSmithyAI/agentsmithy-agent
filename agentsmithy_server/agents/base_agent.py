"""Base agent class for all specialized agents."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agentsmithy_server.core import LLMProvider
from agentsmithy_server.rag import ContextBuilder
from agentsmithy_server.utils.logger import agent_logger


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        context_builder: Optional[ContextBuilder] = None,
        system_prompt: Optional[str] = None,
    ):
        self.llm_provider = llm_provider
        self.context_builder = context_builder or ContextBuilder()
        self.system_prompt = system_prompt or self.get_default_system_prompt()

    @abstractmethod
    def get_default_system_prompt(self) -> str:
        """Get the default system prompt for this agent."""
        pass

    @abstractmethod
    def get_agent_name(self) -> str:
        """Get the name of this agent."""
        pass

    async def process(
        self, query: str, context: Optional[Dict[str, Any]] = None, stream: bool = False
    ) -> Dict[str, Any]:
        """Process a query with optional context."""
        agent_name = self.get_agent_name()
        agent_logger.debug(
            f"{agent_name} processing query", query_length=len(query), streaming=stream
        )

        # Build context
        full_context = await self.context_builder.build_context(query, context)
        agent_logger.debug(
            f"{agent_name} context built",
            has_current_file=bool(full_context.get("current_file")),
            open_files_count=len(full_context.get("open_files", [])),
            relevant_docs_count=len(full_context.get("relevant_documents", [])),
        )

        # Prepare messages
        messages = self._prepare_messages(query, full_context)
        agent_logger.debug(f"{agent_name} prepared {len(messages)} messages")

        # Generate response
        try:
            if stream:
                agent_logger.debug(f"{agent_name} returning streaming response")
                return {
                    "agent": self.get_agent_name(),
                    "response": self.llm_provider.agenerate(messages, stream=True),
                    "context": full_context,
                }
            else:
                agent_logger.debug(f"{agent_name} generating non-streaming response")
                response = await self.llm_provider.agenerate(messages, stream=False)
                agent_logger.info(
                    f"{agent_name} generated response",
                    response_length=len(response) if isinstance(response, str) else 0,
                )
                return {
                    "agent": self.get_agent_name(),
                    "response": response,
                    "context": full_context,
                }
        except Exception as e:
            agent_logger.error(f"{agent_name} failed to generate response", exception=e)
            raise

    def _prepare_messages(
        self, query: str, context: Dict[str, Any]
    ) -> List[BaseMessage]:
        """Prepare messages for LLM."""
        messages = [SystemMessage(content=self.system_prompt)]

        # Add context if available
        formatted_context = self.context_builder.format_context_for_prompt(context)
        if formatted_context:
            messages.append(SystemMessage(content=f"Context:\n{formatted_context}"))

        # Add user query
        messages.append(HumanMessage(content=query))

        return messages
