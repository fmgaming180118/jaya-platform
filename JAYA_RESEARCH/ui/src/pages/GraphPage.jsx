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
    {
        id: '1',
        position: { x: 250, y: 0 },
        data: { label: 'Start Researching' },
        type: 'input',
        style: {
            background: '#1e2025', // notebook-card
            color: '#e3e3e3', // notebook-text-primary
            border: '1px solid #8ab4f8', // notebook-text-accent
            borderRadius: '12px',
            padding: '12px 20px',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3)'
        }
    },
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
                const mappedNodes = graphData.nodes.map((n, i) => ({
                    id: String(n.id),
                    position: { x: 100 + (i * 100), y: 100 + (i * 80) },
                    data: { label: n.label || n.id },
                    style: {
                        background: '#1e2025',
                        color: '#e3e3e3',
                        border: '1px solid #2e3138',
                        borderRadius: '8px',
                        fontSize: '12px'
                    }
                }));
                const mappedEdges = graphData.edges.map(e => ({
                    id: `${e.source}-${e.target}`,
                    source: e.source,
                    target: e.target,
                    style: { stroke: '#5f6368' }
                }));
                setNodes(mappedNodes);
                setEdges(mappedEdges);
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
        <div className="h-full w-full relative bg-notebook-bg">
            <div className="absolute top-6 left-6 z-10 bg-notebook-card/80 backdrop-blur p-5 rounded-2xl border border-notebook-border shadow-lg">
                <h1 className="font-semibold text-notebook-text-primary text-lg">Knowledge Graph</h1>
                <p className="text-xs text-notebook-text-secondary mt-1">Workspace: {workspaceId}</p>
            </div>

            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
            >
                <Background color="#2e3138" gap={20} size={1} />
                <Controls
                    className="bg-notebook-card border border-notebook-border fill-notebook-text-primary text-notebook-text-primary rounded-lg overflow-hidden shadow-xl"
                    showInteractive={false}
                />
            </ReactFlow>
        </div>
    );
}

export default GraphPage;
