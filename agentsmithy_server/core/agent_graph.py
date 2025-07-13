"""Agent orchestration using LangGraph."""

from typing import Dict, Any, List, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from agentsmithy_server.core import LLMFactory
from agentsmithy_server.agents import (
    ClassifierAgent,
    CodeAgent,
    RefactorAgent,
    ExplainAgent,
    FixAgent
)
from agentsmithy_server.rag import ContextBuilder


class AgentState(TypedDict):
    """State for the agent graph."""
    messages: Annotated[List[BaseMessage], add_messages]
    query: str
    context: Optional[Dict[str, Any]]
    task_type: Optional[str]
    response: Optional[str]
    streaming: bool
    metadata: Dict[str, Any]


class AgentOrchestrator:
    """Orchestrates multiple agents using LangGraph."""
    
    def __init__(self, llm_provider_name: str = "openai"):
        # Initialize LLM provider
        self.llm_provider = LLMFactory.create(llm_provider_name)
        
        # Initialize context builder
        self.context_builder = ContextBuilder()
        
        # Initialize agents
        self.classifier = ClassifierAgent(self.llm_provider, self.context_builder)
        self.agents = {
            "code": CodeAgent(self.llm_provider, self.context_builder),
            "refactor": RefactorAgent(self.llm_provider, self.context_builder),
            "explain": ExplainAgent(self.llm_provider, self.context_builder),
            "fix": FixAgent(self.llm_provider, self.context_builder),
        }
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the agent orchestration graph."""
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("classifier", self._classify_task)
        graph.add_node("code_agent", self._run_code_agent)
        graph.add_node("refactor_agent", self._run_refactor_agent)
        graph.add_node("explain_agent", self._run_explain_agent)
        graph.add_node("fix_agent", self._run_fix_agent)
        graph.add_node("general_agent", self._run_general_agent)
        
        # Add edges
        graph.set_entry_point("classifier")
        
        # Conditional routing based on classification
        graph.add_conditional_edges(
            "classifier",
            self._route_to_agent,
            {
                "code": "code_agent",
                "refactor": "refactor_agent",
                "explain": "explain_agent",
                "fix": "fix_agent",
                "general": "general_agent",
                "test": "code_agent",  # Route test to code agent
            }
        )
        
        # All agents lead to END
        for agent_name in ["code_agent", "refactor_agent", "explain_agent", "fix_agent", "general_agent"]:
            graph.add_edge(agent_name, END)
        
        return graph.compile()
    
    async def _classify_task(self, state: AgentState) -> AgentState:
        """Classify the task type."""
        task_type = await self.classifier.classify(state["query"], state["context"])
        state["task_type"] = task_type
        state["metadata"]["classification"] = task_type
        return state
    
    def _route_to_agent(self, state: AgentState) -> str:
        """Route to the appropriate agent based on classification."""
        task_type = state.get("task_type", "general")
        if task_type == "test":
            return "code"  # Route test tasks to code agent
        return task_type
    
    async def _run_agent(self, agent_key: str, state: AgentState) -> AgentState:
        """Run a specific agent."""
        agent = self.agents.get(agent_key)
        if not agent:
            # Fall back to explain agent for general queries
            agent = self.agents["explain"]
        
        result = await agent.process(
            query=state["query"],
            context=state["context"],
            stream=state["streaming"]
        )
        
        state["response"] = result["response"]
        state["metadata"]["agent_used"] = result["agent"]
        state["messages"].append(AIMessage(content=f"[{result['agent']}] Processing..."))
        
        return state
    
    async def _run_code_agent(self, state: AgentState) -> AgentState:
        """Run the code generation agent."""
        return await self._run_agent("code", state)
    
    async def _run_refactor_agent(self, state: AgentState) -> AgentState:
        """Run the refactoring agent."""
        return await self._run_agent("refactor", state)
    
    async def _run_explain_agent(self, state: AgentState) -> AgentState:
        """Run the explanation agent."""
        return await self._run_agent("explain", state)
    
    async def _run_fix_agent(self, state: AgentState) -> AgentState:
        """Run the bug fixing agent."""
        return await self._run_agent("fix", state)
    
    async def _run_general_agent(self, state: AgentState) -> AgentState:
        """Run a general purpose agent (defaults to explain)."""
        return await self._run_agent("explain", state)
    
    async def process_request(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Process a user request through the agent graph."""
        # Initialize state
        initial_state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "query": query,
            "context": context,
            "task_type": None,
            "response": None,
            "streaming": stream,
            "metadata": {}
        }
        
        # Run the graph
        if stream:
            # For streaming, we need to handle it differently
            # Return the graph execution for streaming
            return {
                "graph_execution": self.graph.astream(initial_state),
                "initial_state": initial_state
            }
        else:
            # For non-streaming, run to completion
            final_state = await self.graph.ainvoke(initial_state)
            return {
                "response": final_state["response"],
                "task_type": final_state["task_type"],
                "metadata": final_state["metadata"]
            } 