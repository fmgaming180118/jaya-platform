import { useState, useCallback, useEffect } from 'react';
import ReactFlow, {
    Controls,
    Background,
    applyNodeChanges,
    applyEdgeChanges
} from 'reactflow';
import 'reactflow/dist/style.css';
import api from '../services/api';

const initialNodes = [
    { id: '1', position: { x: 250, y: 0 }, data: { label: 'Start Researching' }, type: 'input', style: { background: '#6366f1', color: '#fff', border: 'none' } },
];

const GraphPage = ({ workspaceId }) => {
    const [nodes, setNodes] = useState(initialNodes);
    const [edges, setEdges] = useState([]);

    useEffect(() => {
        loadGraph();
    }, [workspaceId]);

    const loadGraph = async () => {
        try {
            const graphData = await api.getGraph(workspaceId);
            if (graphData && graphData.nodes && graphData.nodes.length > 0) {
                // Convert NetworkX format to ReactFlow
                // Assumes nodes have {id, ...} and edges {source, target, ...}
                // Logic to map NetworkX positions to ReactFlow or use AutoLayout
                const mappedNodes = graphData.nodes.map((n, i) => ({
                    id: str(n.id),
                    position: { x: 100 + (i * 50), y: 100 + (i * 50) }, // Naive layout
                    data: { label: n.id }
                }));
                const mappedEdges = graphData.edges.map(e => ({
                    id: `${e.source}-${e.target}`,
                    source: e.source,
                    target: e.target
                }));
                // Use basic graph data for now
                // setNodes(mappedNodes);
                // setEdges(mappedEdges);
                console.log("Graph loaded:", graphData);
            }
        } catch (err) {
            console.error(err);
        }
    };

    const onNodesChange = useCallback(
        (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
        []
    );
    const onEdgesChange = useCallback(
        (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
        []
    );

    return (
        <div className="h-full w-full relative">
            <div className="absolute top-4 left-4 z-10 bg-black/50 backdrop-blur p-4 rounded-xl border border-[var(--border)]">
                <h1 className="font-bold text-white">Knowledge Graph</h1>
                <p className="text-xs text-gray-400">Workspace: {workspaceId}</p>
            </div>

            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
            >
                <Background color="#334155" gap={16} />
                <Controls className="bg-[var(--bg-card)] border border-[var(--border)] fill-white text-white" />
            </ReactFlow>
        </div>
    );
}

export default GraphPage;
