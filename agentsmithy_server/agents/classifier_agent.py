"""Classifier agent for determining task type."""

from typing import Dict, Any, List
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from agentsmithy_server.agents.base_agent import BaseAgent


class ClassifierAgent(BaseAgent):
    """Agent that classifies user intent into task categories."""
    
    def get_default_system_prompt(self) -> str:
        return """You are a task classifier agent. Your job is to analyze the user's request and determine which type of task they are asking for.

Classify the request into ONE of these categories:
- "code": Writing new code, implementing features, creating functions or classes
- "refactor": Improving existing code structure, renaming, reorganizing
- "explain": Explaining code, concepts, or answering questions about how something works
- "fix": Fixing bugs, errors, or issues in code
- "test": Writing tests or test-related tasks
- "general": General conversation or tasks that don't fit other categories

Respond with ONLY the category name, nothing else."""
    
    def get_agent_name(self) -> str:
        return "classifier"
    
    async def classify(self, query: str, context: Dict[str, Any] = None) -> str:
        """Classify the user's query into a task category."""
        # Debug logging for context
        import json
        from agentsmithy_server.utils.logger import agent_logger
        
        agent_logger.debug(
            "Classifier received context",
            context_type=type(context).__name__,
            context_is_none=context is None,
            context_content=json.dumps(context, default=str) if context else "None"
        )
        
        # For classification, we use a simplified message format
        messages = [
            SystemMessage(content=self.get_default_system_prompt())
        ]
        
        # Add minimal context if there's selected code
        if context is not None:
            current_file = context.get("current_file")
            agent_logger.debug(
                "Checking current_file",
                current_file_type=type(current_file).__name__,
                current_file_is_none=current_file is None,
                current_file_content=json.dumps(current_file, default=str) if current_file else "None"
            )
            
            # Проверяем что current_file это словарь, а не None
            if current_file and isinstance(current_file, dict):
                selection = current_file.get("selection")
                if selection:
                    messages.append(SystemMessage(
                        content=f"User has selected this code:\n{selection}"
                    ))
        
        messages.append(HumanMessage(content=query))
        
        # Get classification
        response = await self.llm_provider.agenerate(messages, stream=False)
        
        # Normalize and validate response
        classification = response.strip().lower()
        valid_categories = ["code", "refactor", "explain", "fix", "test", "general"]
        
        if classification not in valid_categories:
            # Default to general if classification is unclear
            classification = "general"
        
        return classification 