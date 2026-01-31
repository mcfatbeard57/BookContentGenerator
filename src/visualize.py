"""3D Interactive Graph Visualization"""
import json
import webbrowser
from pathlib import Path

from src.config import CORPUS_DIR, WORLD_GRAPH_PATH


HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <title>Knowledge Graph - 3D Visualization</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #111;
            color: #fff;
            overflow: hidden;
        }
        #container { width: 100vw; height: 100vh; }
        
        #controls {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.8);
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #333;
            max-width: 280px;
            z-index: 100;
        }
        
        h2 { 
            font-size: 18px; 
            margin-bottom: 15px;
            color: #60a5fa;
        }
        
        .legend { margin-bottom: 15px; }
        .legend-item {
            display: flex;
            align-items: center;
            margin: 6px 0;
            font-size: 13px;
        }
        .legend-color {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            margin-right: 10px;
        }
        
        .stats {
            font-size: 12px;
            color: #888;
            border-top: 1px solid #333;
            padding-top: 12px;
        }
        .stats div { margin: 3px 0; }
        .stats span { color: #60a5fa; }
        
        #info {
            position: absolute;
            bottom: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.9);
            padding: 15px 20px;
            border-radius: 10px;
            border: 1px solid #333;
            display: none;
            z-index: 100;
        }
        #info h3 { color: #fff; margin: 5px 0; font-size: 16px; }
        #info .type { 
            font-size: 11px; 
            padding: 2px 8px; 
            border-radius: 4px; 
            display: inline-block;
        }
        
        #search {
            position: absolute;
            top: 20px;
            right: 20px;
            z-index: 100;
        }
        #search input {
            background: rgba(0, 0, 0, 0.8);
            border: 1px solid #333;
            padding: 10px 15px;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            width: 220px;
        }
        #search input:focus { outline: none; border-color: #60a5fa; }
        
        .hint {
            position: absolute;
            bottom: 15px;
            left: 20px;
            font-size: 11px;
            color: #555;
        }
    </style>
</head>
<body>
    <div id="container"></div>
    
    <div id="controls">
        <h2>🌐 Knowledge Graph</h2>
        <div class="legend">
            <div class="legend-item"><div class="legend-color" style="background:#4ade80"></div>Characters</div>
            <div class="legend-item"><div class="legend-color" style="background:#60a5fa"></div>Locations</div>
            <div class="legend-item"><div class="legend-color" style="background:#fb923c"></div>Factions</div>
            <div class="legend-item"><div class="legend-color" style="background:#c084fc"></div>Events</div>
        </div>
        <div class="stats">
            <div>Nodes: <span id="nodes">0</span></div>
            <div>Edges: <span id="edges">0</span></div>
        </div>
    </div>
    
    <div id="search"><input type="text" placeholder="Search..." id="q"></div>
    
    <div id="info">
        <div class="type" id="info-type">TYPE</div>
        <h3 id="info-name">Name</h3>
        <div id="info-conn" style="font-size:12px;color:#888;margin-top:5px"></div>
    </div>
    
    <div class="hint">Click node to highlight • Drag to rotate • Scroll to zoom</div>

    <script src="https://unpkg.com/3d-force-graph@1.73.0/dist/3d-force-graph.min.js"></script>
    <script>
        // Graph data
        const data = GRAPH_DATA_PLACEHOLDER;
        
        // Colors by type
        const COLORS = {
            character: '#4ade80',
            location: '#60a5fa', 
            faction: '#fb923c',
            timeline_event: '#c084fc'
        };
        
        // Build nodes array
        const nodes = Object.values(data.nodes).map(n => ({
            id: n.entity_id,
            name: n.name,
            type: n.entity_type
        }));
        
        // Build links array (only between existing nodes)
        const nodeSet = new Set(nodes.map(n => n.id));
        const links = data.edges
            .filter(e => nodeSet.has(e.from_id) && nodeSet.has(e.to_id))
            .map(e => ({ source: e.from_id, target: e.to_id }));
        
        // Count connections
        const connCount = {};
        links.forEach(l => {
            connCount[l.source] = (connCount[l.source] || 0) + 1;
            connCount[l.target] = (connCount[l.target] || 0) + 1;
        });
        
        // Update UI
        document.getElementById('nodes').textContent = nodes.length;
        document.getElementById('edges').textContent = links.length;
        
        // State
        let selected = null;
        const highlighted = new Set();
        
        // Create graph
        const Graph = ForceGraph3D()(document.getElementById('container'))
            .graphData({ nodes, links })
            .backgroundColor('#111')
            .nodeRelSize(6)
            .nodeVal(n => Math.max(1, (connCount[n.id] || 0) * 0.5 + 1))
            .nodeColor(n => highlighted.size === 0 || highlighted.has(n.id) ? COLORS[n.type] || '#888' : '#222')
            .nodeOpacity(1)
            .linkColor(() => 'rgba(100,150,255,0.4)')
            .linkWidth(1)
            .linkOpacity(0.6)
            .onNodeHover(n => {
                document.body.style.cursor = n ? 'pointer' : 'default';
            })
            .onNodeClick(n => {
                const info = document.getElementById('info');
                if (selected === n) {
                    selected = null;
                    highlighted.clear();
                    info.style.display = 'none';
                } else {
                    selected = n;
                    highlighted.clear();
                    highlighted.add(n.id);
                    links.forEach(l => {
                        const src = typeof l.source === 'object' ? l.source.id : l.source;
                        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
                        if (src === n.id) highlighted.add(tgt);
                        if (tgt === n.id) highlighted.add(src);
                    });
                    document.getElementById('info-name').textContent = n.name;
                    const typeEl = document.getElementById('info-type');
                    typeEl.textContent = n.type.replace('_', ' ').toUpperCase();
                    typeEl.style.background = COLORS[n.type];
                    document.getElementById('info-conn').textContent = (connCount[n.id] || 0) + ' connections';
                    info.style.display = 'block';
                }
                Graph.nodeColor(Graph.nodeColor());
            });
        
        // Search
        document.getElementById('q').addEventListener('input', e => {
            const q = e.target.value.toLowerCase();
            highlighted.clear();
            if (q) {
                nodes.forEach(n => {
                    if (n.name.toLowerCase().includes(q)) highlighted.add(n.id);
                });
            }
            Graph.nodeColor(Graph.nodeColor());
        });
        
        // Physics
        Graph.d3Force('charge').strength(-50);
        Graph.d3Force('link').distance(80);
        
        // Start zoomed out
        Graph.cameraPosition({ z: 600 });
    </script>
</body>
</html>'''


def visualize_graph_3d(
    graph_path: Path | None = None,
    output_path: Path | None = None,
    open_browser: bool = True,
) -> Path:
    """Generate interactive 3D graph visualization."""
    graph_path = graph_path or WORLD_GRAPH_PATH
    output_path = output_path or (CORPUS_DIR / "graph_3d.html")
    
    if not graph_path.exists():
        print(f"Error: Graph not found: {graph_path}")
        return None
    
    with open(graph_path, "r") as f:
        graph_data = json.load(f)
    
    html = HTML_TEMPLATE.replace("GRAPH_DATA_PLACEHOLDER", json.dumps(graph_data))
    output_path.write_text(html)
    
    print(f"✅ 3D Graph: {output_path}")
    print(f"   Nodes: {len(graph_data.get('nodes', {}))}, Edges: {len(graph_data.get('edges', []))}")
    
    if open_browser:
        webbrowser.open(f"file://{output_path.absolute()}")
    
    return output_path


if __name__ == "__main__":
    visualize_graph_3d()
