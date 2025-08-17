"""Agent orchestration using LangGraph."""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agentsmithy_server.agents.universal_agent import UniversalAgent
from agentsmithy_server.core import LLMFactory
from agentsmithy_server.rag import ContextBuilder
from agentsmithy_server.utils.logger import agent_logger


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
        agent_logger.info("Creating AgentOrchestrator", provider=llm_provider_name)
        self.llm_provider = LLMFactory.create(llm_provider_name)

        # Initialize context builder
        self.context_builder = ContextBuilder()

        # Initialize single universal agent
        self.universal_agent = UniversalAgent(self.llm_provider, self.context_builder)
        
        # Store SSE callback for later use
        self._sse_callback = None

        # Build the simplified graph
        self.graph = self._build_graph()
    
    def set_sse_callback(self, callback):
        """Set SSE callback for streaming updates."""
        self._sse_callback = callback
        # Pass it to the agent
        if hasattr(self.universal_agent, 'set_sse_callback'):
            self.universal_agent.set_sse_callback(callback)

    def _build_graph(self) -> StateGraph:
        """Build the simplified agent orchestration graph."""
        graph = StateGraph(AgentState)

        # Add single universal agent node
        graph.add_node("universal_agent", self._run_universal_agent)

        # Direct entry to universal agent
        graph.set_entry_point("universal_agent")

        # Universal agent leads to END
        graph.add_edge("universal_agent", END)

        return graph.compile()

    async def _run_universal_agent(self, state: AgentState) -> AgentState:
        """Run the universal agent."""
        agent_logger.info("Running universal agent", streaming=state["streaming"])

        try:
            result = await self.universal_agent.process(
                query=state["query"],
                context=state["context"],
                stream=state["streaming"],
            )

            state["response"] = result["response"]
            state["metadata"]["agent_used"] = result["agent"]
            state["messages"].append(
                AIMessage(content=f"[{result['agent']}] Processing...")
            )

            agent_logger.info(
                "Universal agent completed",
                agent_used=result["agent"],
                response_type=type(result["response"]).__name__,
            )

        except Exception as e:
            agent_logger.error("Universal agent failed", exception=e)
            raise

        return state



    async def process_request(
        self, query: str, context: Optional[Dict[str, Any]] = None, stream: bool = False
    ) -> Dict[str, Any]:
        """Process a user request through the agent graph."""
        # Initialize state
        initial_state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "query": query,
            "context": context,
            "task_type": "universal",  # No longer needed but kept for compatibility
            "response": None,
            "streaming": stream,
            "metadata": {},
        }

        # Run the graph
        if stream:
            # For streaming, we need to handle it differently
            # Return the graph execution for streaming
            return {
                "graph_execution": self.graph.astream(initial_state),
                "initial_state": initial_state,
            }
        else:
            # For non-streaming, run to completion
            final_state = await self.graph.ainvoke(initial_state)
            return {
                "response": final_state["response"],
                "task_type": final_state["task_type"],
                "metadata": final_state["metadata"],
            }
