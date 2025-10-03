"""Agent orchestration using LangGraph."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agentsmithy_server.agents.universal_agent import UniversalAgent
from agentsmithy_server.core import OpenAIProvider
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

    def __init__(self, llm_provider: Any | None = None):
        # Initialize LLM provider (allow dependency injection)
        if llm_provider is not None:
            self.llm_provider = llm_provider
            provider_label = getattr(
                llm_provider, "__class__", type(llm_provider)
            ).__name__
        else:
            # Fallback to default provider if none injected
            self.llm_provider = OpenAIProvider()
            provider_label = "OpenAIProvider"

        agent_logger.info(
            "Creating AgentOrchestrator",
            provider=provider_label,
        )

        # Initialize context builder
        self.context_builder = ContextBuilder()

        # Initialize single universal agent
        self.universal_agent = UniversalAgent(self.llm_provider, self.context_builder)

        # Store SSE callback for later use
        self._sse_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None

        # Build the simplified graph
        self.graph = self._build_graph()

    def set_sse_callback(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
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
            agent_logger.error("Universal agent failed", exc_info=True, error=str(e))
            raise

        return state

    async def _maybe_compact_node(self, state: AgentState) -> AgentState:
        """Insert a summary SystemMessage when dialog is large."""
        from agentsmithy_server.api.sse_protocol import EventFactory as SSEEventFactory

        emitted_summary_start = False
        try:
            context = state.get("context") or {}
            dialog = context.get("dialog") or {}
            messages = list(dialog.get("messages") or [])
            dialog_id = dialog.get("id")

            # Load existing summary (if any) to chain with tail for re-summarization
            stored = None
            if context.get("project") and dialog_id:
                _storage_obj = DialogSummaryStorage(context["project"], dialog_id)
                if hasattr(_storage_obj, "__enter__") and hasattr(
                    _storage_obj, "__exit__"
                ):
                    with _storage_obj as storage:
                        stored = storage.load()
                else:
                    # Fallback for tests that monkeypatch storage with a plain Mock
                    storage = _storage_obj
                    stored = storage.load()

            # Build compaction source: previous summary (if any) + current tail
            compaction_source = list(messages)
            if stored:
                from langchain_core.messages import SystemMessage

                compaction_source = [
                    SystemMessage(
                        content=f"Dialog Summary (earlier turns):\n{stored.summary_text}"
                    )
                ] + compaction_source

            # Generate or refresh if needed
            # Emit SSE summary_start before running summarization
            if self._sse_callback and state.get("streaming"):
                try:
                    await self._sse_callback(
                        SSEEventFactory.summary_start(dialog_id=dialog_id).to_sse()
                    )
                    emitted_summary_start = True
                except Exception:
                    pass

            extra_msgs = await maybe_compact_dialog(
                self.llm_provider, compaction_source, context.get("project"), dialog_id
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
                        # summarized_count must represent the full number of messages in the dialog history
                        # (including messages that were previously summarized).
                        try:
                            summarized_count = max(
                                0, len(messages) if messages is not None else 0
                            )
                        except Exception:
                            # Fallback to stored value if available, otherwise 0
                            summarized_count = (
                                int(stored.summarized_count or 0) if stored else 0
                            )

                        try:
                            _storage_obj2 = DialogSummaryStorage(
                                context["project"], dialog_id
                            )
                            if hasattr(_storage_obj2, "__enter__") and hasattr(
                                _storage_obj2, "__exit__"
                            ):
                                with _storage_obj2 as storage:
                                    # Store legacy single-row and one versioned record
                                    storage.upsert(
                                        summary_text,
                                        summarized_count,
                                        KEEP_LAST_MESSAGES,
                                    )
                            else:
                                storage = _storage_obj2
                                storage.upsert(
                                    summary_text, summarized_count, KEEP_LAST_MESSAGES
                                )
                        except Exception:
                            pass
        except Exception as e:
            agent_logger.error("Compaction node failed", exc_info=True, error=str(e))
        finally:
            # Guarantee that summary_end is sent if summary_start was emitted
            if emitted_summary_start and self._sse_callback and state.get("streaming"):
                try:
                    dialog = (state.get("context") or {}).get("dialog") or {}
                    dialog_id = dialog.get("id")
                    await self._sse_callback(
                        SSEEventFactory.summary_end(dialog_id=dialog_id).to_sse()
                    )
                except Exception:
                    pass
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
