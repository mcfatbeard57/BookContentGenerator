"""Graph Visualizer - Generate interactive HTML visualization of the knowledge graph"""
import json
import webbrowser
from pathlib import Path

from src.config import WORLD_GRAPH_PATH, CORPUS_DIR


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Knowledge Graph Visualization</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
        #graph { width: 100vw; height: 100vh; }
        #legend { position: absolute; top: 10px; left: 10px; background: rgba(255,255,255,0.9); padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .legend-item { display: flex; align-items: center; margin: 5px 0; }
        .legend-color { width: 20px; height: 20px; border-radius: 50%; margin-right: 10px; }
        h3 { margin: 0 0 10px 0; }
    </style>
</head>
<body>
    <div id="graph"></div>
    <div id="legend">
        <h3>Entity Types</h3>
        <div class="legend-item"><div class="legend-color" style="background:#4CAF50"></div> Character</div>
        <div class="legend-item"><div class="legend-color" style="background:#2196F3"></div> Location</div>
        <div class="legend-item"><div class="legend-color" style="background:#FF9800"></div> Faction</div>
        <div class="legend-item"><div class="legend-color" style="background:#9C27B0"></div> Timeline Event</div>
    </div>
    <script>
        const graphData = GRAPH_DATA_PLACEHOLDER;
        
        const colorMap = {
            'character': '#4CAF50',
            'location': '#2196F3',
            'faction': '#FF9800',
            'timeline_event': '#9C27B0'
        };
        
        const nodes = new vis.DataSet(
            Object.values(graphData.nodes).map(n => ({
                id: n.entity_id,
                label: n.name,
                color: colorMap[n.entity_type] || '#666',
                shape: 'dot',
                size: 20,
                font: { size: 14, color: '#333' }
            }))
        );
        
        const edges = new vis.DataSet(
            graphData.edges.map((e, i) => ({
                id: i,
                from: e.from_id,
                to: e.to_id,
                label: e.relation,
                arrows: 'to',
                font: { size: 10, color: '#666' },
                color: { color: '#999', highlight: '#333' }
            }))
        );
        
        const container = document.getElementById('graph');
        const data = { nodes, edges };
        const options = {
            physics: {
                stabilization: { iterations: 100 },
                barnesHut: { gravitationalConstant: -3000, springLength: 150 }
            },
            interaction: { hover: true, zoomView: true }
        };
        
        new vis.Network(container, data, options);
    </script>
</body>
</html>"""


def visualize_graph(graph_path: Path | None = None, output_path: Path | None = None, open_browser: bool = True):
    """
    Generate an interactive HTML visualization of the knowledge graph.
    
    Args:
        graph_path: Path to world_graph.json
        output_path: Where to save the HTML file
        open_browser: Whether to open in default browser
    """
    graph_path = graph_path or WORLD_GRAPH_PATH
    output_path = output_path or (CORPUS_DIR / "graph_visualization.html")
    
    if not graph_path.exists():
        print(f"Error: Graph file not found: {graph_path}")
        print("Run the pipeline first to generate the graph.")
        return
    
    # Load graph data
    with open(graph_path, "r") as f:
        graph_data = json.load(f)
    
    # Generate HTML
    html = HTML_TEMPLATE.replace(
        "GRAPH_DATA_PLACEHOLDER",
        json.dumps(graph_data)
    )
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    
    print(f"✅ Graph visualization saved to: {output_path}")
    print(f"   Nodes: {len(graph_data.get('nodes', {}))}")
    print(f"   Edges: {len(graph_data.get('edges', []))}")
    
    if open_browser:
        webbrowser.open(f"file://{output_path.absolute()}")


if __name__ == "__main__":
    visualize_graph()
