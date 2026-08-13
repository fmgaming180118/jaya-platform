"""
demo_jarvis_3d_graph.py — Advanced 3D WebGL Sci-Fi Holographic JARVIS Knowledge Graph.

Uses Three.js & 3D-Force-Graph (WebGL) to render glowing particle nodes, bloom shaders,
and dynamic 3D neural connections matching Iron Man JARVIS HUD standards.
"""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))


def generate_jarvis_3d_webgl_html(graph_data: dict) -> str:
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>JAYA JARVIS — 3D Holographic Knowledge Graph</title>
    <style>
        body {{
            margin: 0;
            background-color: #020610;
            color: #00f0ff;
            font-family: 'Segoe UI', Roboto, sans-serif;
            overflow: hidden;
        }}
        #3d-graph {{
            width: 100vw;
            height: 100vh;
        }}
        .hud-overlay {{
            position: absolute;
            top: 20px;
            left: 20px;
            pointer-events: none;
            z-index: 10;
        }}
        h1 {{
            margin: 0;
            font-size: 26px;
            letter-spacing: 3px;
            color: #00f0ff;
            text-shadow: 0 0 15px #00f0ff, 0 0 30px #00f0ff;
        }}
        p {{
            margin: 5px 0 0 0;
            font-size: 13px;
            color: #80e5ff;
            text-shadow: 0 0 8px #00f0ff;
        }}
        .hud-stats {{
            position: absolute;
            bottom: 20px;
            right: 20px;
            background: rgba(3, 12, 30, 0.85);
            border: 1px solid #00f0ff;
            padding: 12px 20px;
            border-radius: 8px;
            font-family: monospace;
            box-shadow: 0 0 15px rgba(0, 240, 255, 0.4);
            z-index: 10;
        }}
    </style>
    <!-- Three.js and 3D Force Graph WebGL Engine -->
    <script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
    <script src="https://unpkg.com/3d-force-graph@1.73.1/dist/3d-force-graph.min.js"></script>
</head>
<body>
    <div class="hud-overlay">
        <h1>JAYA JARVIS 3D KNOWLEDGE CORE</h1>
        <p>WebGL 3D Force-Directed Neural Network — Powered by Three.js</p>
    </div>

    <div class="hud-stats">
        <div>CORE STATUS: ACTIVE</div>
        <div>NODES LOADED: <span id="node-count">0</span></div>
        <div>RENDER ENGINE: WebGL 3D</div>
    </div>

    <div id="3d-graph"></div>

    <script>
        const initData = {json.dumps(graph_data)};
        document.getElementById('node-count').innerText = initData.nodes.length;

        const Graph = ForceGraph3D()
            (document.getElementById('3d-graph'))
            .graphData(initData)
            .backgroundColor('#020610')
            .nodeLabel('label')
            .nodeColor(node => node.color || '#00f0ff')
            .nodeVal(node => node.val || 10)
            .nodeResolution(32)
            .linkColor(() => '#00f0ff')
            .linkWidth(2)
            .linkDirectionalParticles(4)
            .linkDirectionalParticleSpeed(0.006)
            .linkDirectionalParticleWidth(3)
            .linkDirectionalParticleColor(() => '#ffffff')
            .onNodeClick(node => {{
                // Center camera on clicked node
                const distance = 40;
                const distRatio = 1 + distance/Math.hypot(node.x, node.y, node.z);
                Graph.cameraPosition(
                    {{ x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio }},
                    node,
                    2000
                );
            }});

        // Auto rotate camera around JARVIS 3D core
        let angle = 0;
        setInterval(() => {{
            angle += 0.003;
            Graph.cameraPosition({{
                x: 250 * Math.sin(angle),
                z: 250 * Math.cos(angle)
            }});
        }}, 30);
    </script>
</body>
</html>
"""


def main():
    print("=" * 65)
    print("  JARVIS 3D WEBGL HOLOGRAPHIC KNOWLEDGE GRAPH (THREE.JS)")
    print("=" * 65)

    graph_data = {
        "nodes": [
            {"id": "core", "label": "JARVIS CENTRAL CORE", "color": "#00ffff", "val": 25},
            {"id": "n1", "label": "Physics & Fusion", "color": "#ff00ff", "val": 15},
            {"id": "n2", "label": "Tokamak Reactor", "color": "#7000ff", "val": 12},
            {"id": "n3", "label": "Lawson Criterion n*tau", "color": "#00ffaa", "val": 10},
            {"id": "n4", "label": "Laravel Full-Stack Engine", "color": "#ff3300", "val": 15},
            {"id": "n5", "label": "Titanium OpenUSD 3D", "color": "#0099ff", "val": 14},
            {"id": "n6", "label": "NVIDIA Omniverse RTX", "color": "#76b900", "val": 16},
            {"id": "n7", "label": "JAYA Agent Sandbox", "color": "#ffaa00", "val": 12},
        ],
        "links": [
            {"source": "core", "target": "n1"},
            {"source": "core", "target": "n4"},
            {"source": "core", "target": "n5"},
            {"source": "core", "target": "n7"},
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            {"source": "n5", "target": "n6"},
            {"source": "n7", "target": "n4"},
        ],
    }

    output_html = repo_root / "data" / "artifacts" / "jarvis_3d_knowledge_graph.html"
    output_html.parent.mkdir(parents=True, exist_ok=True)

    html_content = generate_jarvis_3d_webgl_html(graph_data)
    output_html.write_text(html_content, encoding="utf-8")

    print(f"\n1. [3D WEBGL GENERATED] File Tampilan 3D Hologram JARVIS Berhasil Dibuat!")
    print(f"   -> File HTML : {output_html}")

    try:
        webbrowser.open(f"file:///{output_html}")
    except Exception as err:
        print(f"   -> Buka file manual di: file:///{output_html}")

    print("\n" + "=" * 65)
    print("   SUKSES: Tampilan 3D Force-Directed JARVIS Siap Digunakan!")
    print("=" * 65)


if __name__ == "__main__":
    main()
