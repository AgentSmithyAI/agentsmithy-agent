#!/usr/bin/env python3
"""Visualize the AgentSmithy agent graph."""

import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from agentsmithy_server.core.agent_graph import AgentOrchestrator
from agentsmithy_server.utils.graph_visualizer import visualize_graph, get_graph_structure
import json


def main():
    """Generate and display graph visualization."""
    print("🎨 AgentSmithy Graph Visualizer")
    print("==============================\n")
    
    try:
        # Create orchestrator instance
        print("📊 Building agent graph...")
        orchestrator = AgentOrchestrator()
        
        # Get graph structure
        print("🔍 Extracting graph structure...")
        structure = get_graph_structure(orchestrator.graph)
        
        # Save structure as JSON
        with open("agent_graph_structure.json", "w") as f:
            json.dump(structure, f, indent=2)
        print("✅ Graph structure saved to: agent_graph_structure.json")
        
        # Print structure
        print("\n📋 Graph Structure:")
        print(f"   Nodes: {len(structure.get('nodes', []))}")
        for node in structure.get('nodes', []):
            print(f"     - {node['id']} ({node['type']})")
        
        print(f"\n   Edges: {len(structure.get('edges', []))}")
        for edge in structure.get('edges', []):
            condition = f" [condition: {edge['condition']}]" if edge['condition'] else ""
            print(f"     - {edge['source']} → {edge['target']}{condition}")
        
        # Try to generate visual graph
        print("\n🎨 Generating visual graph...")
        output_path = visualize_graph(orchestrator.graph, "agent_graph.png")
        
        if output_path:
            print(f"\n✅ Visualization complete!")
            if output_path.endswith('.png'):
                print(f"   Open agent_graph.png to see the visual representation")
            elif output_path.endswith('.mermaid'):
                print(f"   Copy the content of {output_path} to https://mermaid.live to visualize")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 