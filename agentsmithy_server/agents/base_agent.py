"""Base agent class for all specialized agents."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from agentsmithy_server.core import LLMProvider
from agentsmithy_server.rag import ContextBuilder


class BaseAgent(ABC):
    """Abstract base class for all agents."""
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        context_builder: Optional[ContextBuilder] = None,
        system_prompt: Optional[str] = None
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
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Process a query with optional context."""
        # Build context
        full_context = await self.context_builder.build_context(query, context)
        
        # Prepare messages
        messages = self._prepare_messages(query, full_context)
        
        # Generate response
        if stream:
            return {
                "agent": self.get_agent_name(),
                "response": self.llm_provider.agenerate(messages, stream=True),
                "context": full_context
            }
        else:
            response = await self.llm_provider.agenerate(messages, stream=False)
            return {
                "agent": self.get_agent_name(),
                "response": response,
                "context": full_context
            }
    
    def _prepare_messages(
        self,
        query: str,
        context: Dict[str, Any]
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