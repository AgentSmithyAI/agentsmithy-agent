"""Graph visualization utilities for LangGraph."""

from typing import Any

from langgraph.graph import StateGraph


def visualize_graph(graph: StateGraph, output_path: str = "agent_graph.png") -> str:
    """
    Visualize the agent graph and save it as an image.

    Args:
        graph: The compiled LangGraph instance
        output_path: Path to save the visualization

    Returns:
        Path to the saved image
    """
    # Disable heavy visualization by default to avoid dependency/version issues
    print("⚠️  Graph visualization is disabled in this build.")
    return ""


def get_graph_structure(graph: Any) -> dict:
    """
    Get the structure of the graph as a dictionary.

    Args:
        graph: The compiled LangGraph instance

    Returns:
        Dictionary representation of the graph structure
    """
    try:
        nodes = []
        edges = []

        # Extract nodes and edges from the graph
        try:
            graph_obj = graph.get_graph()
        except Exception:
            graph_obj = graph

        # Get nodes
        for node in graph_obj.nodes:
            nodes.append(
                {
                    "id": str(node),
                    "type": "agent" if "agent" in str(node).lower() else "system",
                }
            )

        # Get edges
        for edge in graph_obj.edges:
            edges.append(
                {
                    "source": str(edge[0]),
                    "target": str(edge[1]),
                    "condition": edge[2] if len(edge) > 2 else None,
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "entry_point": (
                str(graph_obj.entry_point)
                if hasattr(graph_obj, "entry_point")
                else None
            ),
        }

    except Exception as e:
        print(f"⚠️  Could not extract graph structure: {e}")
        return {"error": str(e)}
