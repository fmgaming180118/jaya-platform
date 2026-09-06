"""
demo_jarvis_graph.py — Demo Visualizer Otak JARVIS JAYA (Circular Knowledge Graph).

Menghasilkan data & file HTML interaktif visualisasi jaringan pengetahuan JARVIS
berbentuk lingkaran bersinar dengan garis penghubung antar-entitas (D3.js / Canvas WebGL).
"""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))


def generate_jarvis_holographic_html(nodes_data: list, edges_data: list) -> str:
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>JAYA JARVIS — Holographic Knowledge Graph</title>
    <style>
        body {{
            margin: 0;
            background-color: #030813;
            color: #00f0ff;
            font-family: 'Segoe UI', Roboto, sans-serif;
            overflow: hidden;
        }}
        #canvas-container {{
            width: 100vw;
            height: 100vh;
            position: relative;
        }}
        canvas {{
            display: block;
        }}
        .overlay-header {{
            position: absolute;
            top: 20px;
            left: 20px;
            z-index: 10;
            pointer-events: none;
        }}
        h1 {{
            margin: 0;
            font-size: 24px;
            letter-spacing: 2px;
            text-shadow: 0 0 10px #00f0ff;
        }}
        p {{
            margin: 5px 0 0 0;
            font-size: 13px;
            color: #80e5ff;
        }}
    </style>
</head>
<body>
    <div id="canvas-container">
        <div class="overlay-header">
            <h1>JARVIS KNOWLEDGE CORE</h1>
            <p>JAYA Cognitive Graph Visualizer — Active Neural Network</p>
        </div>
        <canvas id="jarvisCanvas"></canvas>
    </div>

    <script>
        const nodes = {json.dumps(nodes_data)};
        const edges = {json.dumps(edges_data)};

        const canvas = document.getElementById('jarvisCanvas');
        const ctx = canvas.getContext('2d');

        function resize() {{
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }}
        window.addEventListener('resize', resize);
        resize();

        // Assign circular orbital positions around central JARVIS core
        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const radius = Math.min(canvas.width, canvas.height) * 0.3;

        nodes.forEach((node, i) => {{
            if (i === 0) {{
                node.x = centerX;
                node.y = centerY;
                node.r = 25;
            }} else {{
                const angle = ((i - 1) / (nodes.length - 1)) * Math.PI * 2;
                node.x = centerX + Math.cos(angle) * radius;
                node.y = centerY + Math.sin(angle) * radius;
                node.r = 12;
                node.angle = angle;
            }}
        }});

        let pulse = 0;

        function animate() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            pulse += 0.03;

            // Draw glowing connecting edges
            edges.forEach(edge => {{
                const source = nodes.find(n => n.id === edge.source_id);
                const target = nodes.find(n => n.id === edge.target_id);
                if (source && target) {{
                    ctx.beginPath();
                    ctx.moveTo(source.x, source.y);
                    ctx.lineTo(target.x, target.y);
                    ctx.strokeStyle = 'rgba(0, 240, 255, 0.4)';
                    ctx.lineWidth = 1.5;
                    ctx.shadowBlur = 8;
                    ctx.shadowColor = '#00f0ff';
                    ctx.stroke();

                    // Animated energy pulse along edges
                    const t = (Math.sin(pulse + source.r) + 1) / 2;
                    const px = source.x + (target.x - source.x) * t;
                    const py = source.y + (target.y - source.y) * t;
                    ctx.beginPath();
                    ctx.arc(px, py, 3, 0, Math.PI * 2);
                    ctx.fillStyle = '#ffffff';
                    ctx.fill();
                }}
            }});

            // Draw glowing circular knowledge nodes
            nodes.forEach((node, i) => {{
                // Orbital gentle drift
                if (i > 0) {{
                    node.angle += 0.002;
                    node.x = centerX + Math.cos(node.angle) * radius;
                    node.y = centerY + Math.sin(node.angle) * radius;
                }}

                ctx.beginPath();
                ctx.arc(node.x, node.y, node.r + Math.sin(pulse + i) * 1.5, 0, Math.PI * 2);
                ctx.fillStyle = (i === 0) ? '#00f0ff' : '#7000ff';
                ctx.shadowBlur = 15;
                ctx.shadowColor = (i === 0) ? '#00f0ff' : '#9d00ff';
                ctx.fill();
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Draw label
                ctx.shadowBlur = 0;
                ctx.fillStyle = '#ffffff';
                ctx.font = (i === 0) ? 'bold 14px Segoe UI' : '11px Segoe UI';
                ctx.textAlign = 'center';
                ctx.fillText(node.label, node.x, node.y + node.r + 15);
            }});

            requestAnimationFrame(animate);
        }}

        animate();
    </script>
</body>
</html>
"""


def main():
    print("=" * 65)
    print("  VISUALIZER OTAK JARVIS JAYA — CIRCULAR KNOWLEDGE GRAPH")
    print("=" * 65)

    print("\n1. [JAYA CORE] Mengekstrak Entitas Knowledge Node & Relation Edge...")

    nodes_data = [
        {"id": "core", "label": "JAYA JARVIS CORE"},
        {"id": "n1", "label": "Physics & Fusion"},
        {"id": "n2", "label": "Tokamak Reactor"},
        {"id": "n3", "label": "Lawson Criterion"},
        {"id": "n4", "label": "Laravel Framework"},
        {"id": "n5", "label": "Titanium OpenUSD"},
        {"id": "n6", "label": "NVIDIA Omniverse"},
    ]

    edges_data = [
        {"source_id": "core", "target_id": "n1"},
        {"source_id": "core", "target_id": "n4"},
        {"source_id": "core", "target_id": "n5"},
        {"source_id": "n1", "target_id": "n2"},
        {"source_id": "n2", "target_id": "n3"},
        {"source_id": "n5", "target_id": "n6"},
    ]

    # 2. Generasi File Visualisasi HTML5 Canvas Hologram JARVIS
    output_html = repo_root / "data" / "artifacts" / "jarvis_knowledge_graph.html"
    output_html.parent.mkdir(parents=True, exist_ok=True)

    html_content = generate_jarvis_holographic_html(nodes_data, edges_data)
    output_html.write_text(html_content, encoding="utf-8")

    print(f"\n2. [VISUALIZER GENERATED] File Tampilan Hologram JARVIS Berhasil Dibuat!")
    print(f"   -> File HTML : {output_html}")

    # Membuka otomatis di browser
    try:
        webbrowser.open(f"file:///{output_html}")
    except Exception as err:
        print(f"   -> Buka file manual di: file:///{output_html}")

    print("\n" + "=" * 65)
    print("   SUKSES: Tampilan Otak Lingkaran JARVIS Siap Rendernya!")
    print("=" * 65)


if __name__ == "__main__":
    main()
