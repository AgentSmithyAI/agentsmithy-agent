import pytest
from unittest.mock import Mock, AsyncMock
from types import SimpleNamespace

from agentsmithy_server.core import agent_graph
from langchain_core.messages import HumanMessage, SystemMessage


@pytest.mark.asyncio
async def test_no_previous_summary_stores_total_message_count(monkeypatch):
    # Arrange: mock storage and summarizer
    mock_storage = Mock()
    mock_storage.load.return_value = None
    mock_storage.upsert = Mock()

    monkeypatch.setattr(agent_graph, "DialogSummaryStorage", lambda project, dialog_id: mock_storage)
    monkeypatch.setattr(agent_graph, "maybe_compact_dialog", AsyncMock(return_value=[SystemMessage(content="Fake summary of history.")]))

    total_msgs = 7
    dialog_messages = [HumanMessage(content=f"msg{i}") for i in range(total_msgs)]

    # Create AgentOrchestrator instance without running __init__ to avoid workspace/global setup
    orchestrator = agent_graph.AgentOrchestrator.__new__(agent_graph.AgentOrchestrator)
    orchestrator.llm_provider = None
    orchestrator._sse_callback = None
    orchestrator.universal_agent = None

    state = {
        "messages": [],
        "query": "test",
        "context": {
            "project": "proj",
            "dialog": {"id": "d1", "messages": dialog_messages},
        },
        "task_type": "universal",
        "response": None,
        "streaming": False,
        "metadata": {},
    }

    # Act
    await orchestrator._maybe_compact_node(state)

    # Assert
    mock_storage.upsert.assert_called_once()
    _, summarized_count, _ = mock_storage.upsert.call_args[0]
    assert summarized_count == len(dialog_messages)


@pytest.mark.asyncio
async def test_with_previous_summary_stores_total_message_count(monkeypatch):
    # Arrange
    mock_storage = Mock()
    # previous stored summary indicates 5 messages were summarized earlier
    mock_storage.load.return_value = SimpleNamespace(summary_text="prev", summarized_count=5)
    mock_storage.upsert = Mock()

    monkeypatch.setattr(agent_graph, "DialogSummaryStorage", lambda project, dialog_id: mock_storage)
    monkeypatch.setattr(agent_graph, "maybe_compact_dialog", AsyncMock(return_value=[SystemMessage(content="Fake summary of history.")]))

    total_msgs = 12
    dialog_messages = [HumanMessage(content=f"msg{i}") for i in range(total_msgs)]

    orchestrator = agent_graph.AgentOrchestrator.__new__(agent_graph.AgentOrchestrator)
    orchestrator.llm_provider = None
    orchestrator._sse_callback = None
    orchestrator.universal_agent = None

    state = {
        "messages": [],
        "query": "test",
        "context": {
            "project": "proj",
            "dialog": {"id": "d2", "messages": dialog_messages},
        },
        "task_type": "universal",
        "response": None,
        "streaming": False,
        "metadata": {},
    }

    # Act
    await orchestrator._maybe_compact_node(state)

    # Assert
    mock_storage.upsert.assert_called_once()
    _, summarized_count, _ = mock_storage.upsert.call_args[0]
    assert summarized_count == len(dialog_messages)


@pytest.mark.asyncio
async def test_tail_shorter_than_keep_last_still_stores_total(monkeypatch):
    # Arrange
    mock_storage = Mock()
    mock_storage.load.return_value = SimpleNamespace(summary_text="prev", summarized_count=10)
    mock_storage.upsert = Mock()

    monkeypatch.setattr(agent_graph, "DialogSummaryStorage", lambda project, dialog_id: mock_storage)
    monkeypatch.setattr(agent_graph, "maybe_compact_dialog", AsyncMock(return_value=[SystemMessage(content="Fake summary of history.")]))

    total_msgs = 12
    dialog_messages = [HumanMessage(content=f"msg{i}") for i in range(total_msgs)]

    orchestrator = agent_graph.AgentOrchestrator.__new__(agent_graph.AgentOrchestrator)
    orchestrator.llm_provider = None
    orchestrator._sse_callback = None
    orchestrator.universal_agent = None

    state = {
        "messages": [],
        "query": "test",
        "context": {
            "project": "proj",
            "dialog": {"id": "d3", "messages": dialog_messages},
        },
        "task_type": "universal",
        "response": None,
        "streaming": False,
        "metadata": {},
    }

    # Act
    await orchestrator._maybe_compact_node(state)

    # Assert
    mock_storage.upsert.assert_called_once()
    _, summarized_count, _ = mock_storage.upsert.call_args[0]
    assert summarized_count == len(dialog_messages)
