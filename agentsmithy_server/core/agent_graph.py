"""Agent orchestration using LangGraph."""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agentsmithy_server.agents.universal_agent import UniversalAgent
from agentsmithy_server.core import LLMFactory
from agentsmithy_server.core.context_compactor import maybe_compact_dialog
from agentsmithy_server.core.dialog_summary_storage import DialogSummaryStorage
from agentsmithy_server.core.summarization.strategy import KEEP_LAST_MESSAGES
from agentsmithy_server.rag import ContextBuilder
from agentsmithy_server.utils.logger import agent_logger


class AgentState(TypedDict):
    """State for the agent graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    context: dict[str, Any] | None
    task_type: str | None
    response: str | None
    streaming: bool
    metadata: dict[str, Any]


class AgentOrchestrator:
    """Orchestrates multiple agents using LangGraph."""

    def __init__(self, llm_provider_name: str = "openai"):
        # Initialize LLM provider
        agent_logger.info("Creating AgentOrchestrator", provider=llm_provider_name)
        # No agent-specific overrides; rely on global settings/defaults
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
        if hasattr(self.universal_agent, "set_sse_callback"):
            self.universal_agent.set_sse_callback(callback)

    def _build_graph(self) -> Any:
        """Build the simplified agent orchestration graph."""
        graph = StateGraph(AgentState)

        # Add context compaction followed by universal agent
        graph.add_node("context_compaction", self._maybe_compact_node)
        graph.add_node("universal_agent", self._run_universal_agent)

        # Entry point compacts dialog first, then agent
        graph.set_entry_point("context_compaction")
        graph.add_edge("context_compaction", "universal_agent")
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

    async def _maybe_compact_node(self, state: AgentState) -> AgentState:
        """Insert a summary SystemMessage when dialog is large."""
        try:
            context = state.get("context") or {}
            dialog = context.get("dialog") or {}
            messages = list(dialog.get("messages") or [])
            dialog_id = dialog.get("id")

            # Try persisted summary first
            if context.get("project") and dialog_id:
                storage = DialogSummaryStorage(context["project"], dialog_id)
                stored = storage.load()
                total_msgs = len(messages)
                if (
                    stored
                    and stored.keep_last == KEEP_LAST_MESSAGES
                    and stored.summarized_count
                    >= max(0, total_msgs - KEEP_LAST_MESSAGES)
                ):
                    from langchain_core.messages import SystemMessage

                    state["messages"] = [
                        SystemMessage(
                            content=f"Dialog Summary (earlier turns):\n{stored.summary_text}"
                        )
                    ] + state.get("messages", [])
                    agent_logger.info(
                        "Using persisted dialog summary",
                        dialog_id=dialog_id,
                        summarized_count=stored.summarized_count,
                    )
                    return state

            # Generate or refresh if needed
            extra_msgs = await maybe_compact_dialog(
                self.llm_provider, messages, context.get("project"), dialog_id
            )
            if extra_msgs:
                from langchain_core.messages import SystemMessage

                state["messages"] = extra_msgs + state.get("messages", [])

                # Persist generated summary
                if context.get("project") and dialog_id:
                    summary_msg = next(
                        (m for m in extra_msgs if isinstance(m, SystemMessage)), None
                    )
                    if summary_msg:
                        summary_text = str(getattr(summary_msg, "content", "") or "")
                        summarized_count = max(0, len(messages) - KEEP_LAST_MESSAGES)
                        try:
                            storage = DialogSummaryStorage(
                                context["project"], dialog_id
                            )
                            storage.upsert(
                                summary_text, summarized_count, KEEP_LAST_MESSAGES
                            )
                        except Exception:
                            pass
        except Exception as e:
            agent_logger.error("Compaction node failed", exception=e)
        return state

    async def process_request(
        self, query: str, context: dict[str, Any] | None = None, stream: bool = False
    ) -> dict[str, Any]:
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
            return {
                "graph_execution": self.graph.astream(initial_state),
                "initial_state": initial_state,
            }
        else:
            final_state = await self.graph.ainvoke(initial_state)
            return {
                "response": final_state["response"],
                "task_type": final_state["task_type"],
                "metadata": final_state["metadata"],
            }
