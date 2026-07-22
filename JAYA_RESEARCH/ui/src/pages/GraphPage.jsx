import { useState, useCallback, useEffect } from 'react';
import ReactFlow, {
    Controls,
    Background,
    applyNodeChanges,
    applyEdgeChanges,
    MarkerType,
    MiniMap,
} from 'reactflow';
import 'reactflow/dist/style.css';
import api from '../services/api';

// ─── colour palette ──────────────────────────────────────────────────────────
const SOURCE_COLORS = {
    arxiv:                '#3b82f6',
    'semantic scholar':   '#8b5cf6',
    openalex:             '#10b981',
    'crossref indonesia': '#f59e0b',
    garuda:               '#22d3ee',
    reference:            '#374151',
    unknown:              '#6b7280',
};

function srcColor(source, nodeType) {
    if (nodeType === 'reference') return SOURCE_COLORS.reference;
    return SOURCE_COLORS[(source || '').toLowerCase()] || SOURCE_COLORS.unknown;
}

const LEGEND = [
    { label: 'ArXiv',                   color: SOURCE_COLORS.arxiv },
    { label: 'Semantic Scholar',         color: SOURCE_COLORS['semantic scholar'] },
    { label: 'OpenAlex',                 color: SOURCE_COLORS.openalex },
    { label: 'Crossref Indonesia',       color: SOURCE_COLORS['crossref indonesia'] },
    { label: 'GARUDA',                   color: SOURCE_COLORS.garuda },
    { label: 'Reference (unprocessed)',  color: SOURCE_COLORS.reference },
];

function autoLayout(rawNodes, rawEdges) {
    if (!rawNodes.length) return { nodes: [], edges: [] };
    const cx = 600, cy = 400;
    const r = Math.max(200, rawNodes.length * 28);
    const nodes = rawNodes.map((n, i) => ({
        ...n,
        position: {
            x: cx + r * Math.cos((2 * Math.PI * i) / rawNodes.length),
            y: cy + r * Math.sin((2 * Math.PI * i) / rawNodes.length),
        },
        style: {
            background: srcColor(n.data && n.data.source, n.data && n.data.node_type),
            color: '#f1f5f9',
            border: (n.data && n.data.node_type) === 'paper'
                ? '2px solid rgba(255,255,255,0.22)'
                : '1px solid rgba(255,255,255,0.08)',
            borderRadius: (n.data && n.data.node_type) === 'paper' ? '10px' : '6px',
            padding: '8px 14px',
            fontSize: (n.data && n.data.node_type) === 'paper' ? '12px' : '10px',
            fontWeight: (n.data && n.data.node_type) === 'paper' ? '600' : '400',
            maxWidth: '220px',
            boxShadow: (n.data && n.data.node_type) === 'paper'
                ? '0 4px 20px rgba(0,0,0,0.4)' : 'none',
            opacity: (n.data && n.data.node_type) === 'reference' ? 0.6 : 1,
        },
    }));
    const edges = rawEdges.map(e => ({
        ...e,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b' },
        style: { stroke: '#64748b', strokeWidth: 1.5, opacity: 0.7 },
        labelStyle: { fill: '#94a3b8', fontSize: 9 },
    }));
    return { nodes, edges };
}

const tagStyle = {
    fontSize: 10, padding: '2px 8px', borderRadius: 99,
    background: 'rgba(255,255,255,0.07)', color: '#94a3b8',
};

function NodeDetail({ node, onClose }) {
    if (!node) return null;
    const d = node.data || {};
    const langBadge = d.language === 'id' ? '🇮🇩 Indonesian'
        : d.language === 'en' ? '🌐 English' : '';
    const isCached = d.local_path && d.local_path.length > 0;
    return (
        <div style={{
            position: 'absolute', top: 16, right: 16, zIndex: 20,
            width: 320, background: 'rgba(15,17,23,0.96)',
            border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14,
            padding: 20, boxShadow: '0 8px 40px rgba(0,0,0,0.6)',
            backdropFilter: 'blur(12px)',
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <span style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: 1,
                    color: srcColor(d.source, d.node_type), textTransform: 'uppercase',
                }}>
                    {d.node_type === 'paper' ? (d.source || 'Paper') : 'Reference'}
                </span>
                <button onClick={onClose} style={{
                    background: 'none', border: 'none', color: '#64748b',
                    cursor: 'pointer', fontSize: 18, lineHeight: 1,
                }}>✕</button>
            </div>
            <p style={{ color: '#f1f5f9', fontSize: 13, fontWeight: 600, margin: '0 0 8px', lineHeight: 1.4 }}>
                {d.full_title || d.label}
            </p>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                {d.year && <span style={tagStyle}>{d.year}</span>}
                {langBadge && <span style={tagStyle}>{langBadge}</span>}
                {d.rank_score > 0 && <span style={tagStyle}>Score: {Number(d.rank_score).toFixed(2)}</span>}
                {isCached && <span style={{ ...tagStyle, background: 'rgba(16,185,129,0.15)', color: '#10b981' }}>✓ Cached</span>}
            </div>
            {d.insight_excerpt && (
                <p style={{ color: '#94a3b8', fontSize: 11, lineHeight: 1.6, margin: '0 0 12px' }}>
                    {d.insight_excerpt}
                </p>
            )}
            {d.pdf_link && (
                <a href={d.pdf_link} target="_blank" rel="noreferrer" style={{
                    display: 'block', color: '#60a5fa', fontSize: 11,
                    wordBreak: 'break-all', textDecoration: 'none',
                }}>🔗 Open PDF / Source</a>
            )}
        </div>
    );
}

function LegendPanel() {
    return (
        <div style={{
            position: 'absolute', bottom: 16, left: 16, zIndex: 20,
            background: 'rgba(15,17,23,0.9)', border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 10, padding: '10px 14px', backdropFilter: 'blur(8px)',
        }}>
            {LEGEND.map(l => (
                <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 3, background: l.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 10, color: '#94a3b8' }}>{l.label}</span>
                </div>
            ))}
        </div>
    );
}

function CachedSidebar({ papers, onSearch, query, setQuery, stats }) {
    return (
        <div style={{
            position: 'absolute', top: 70, left: 16, zIndex: 20,
            width: 280, maxHeight: 'calc(100vh - 200px)',
            background: 'rgba(15,17,23,0.93)', border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 12, backdropFilter: 'blur(10px)',
            display: 'flex', flexDirection: 'column',
        }}>
            <div style={{ padding: '12px 14px 8px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <p style={{ color: '#f1f5f9', fontSize: 12, fontWeight: 600, margin: '0 0 8px' }}>
                    📚 Cached Papers
                    <span style={{ color: '#64748b', fontWeight: 400, marginLeft: 6 }}>
                        ({stats ? stats.papers : 0} papers, {stats ? stats.references : 0} refs)
                    </span>
                </p>
                <div style={{ display: 'flex', gap: 6 }}>
                    <input
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && onSearch(query)}
                        placeholder="Search cached…"
                        style={{
                            flex: 1, background: 'rgba(255,255,255,0.05)',
                            border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
                            color: '#f1f5f9', fontSize: 11, padding: '5px 8px', outline: 'none',
                        }}
                    />
                    <button onClick={() => onSearch(query)} style={{
                        background: '#3b82f6', border: 'none', borderRadius: 6,
                        color: '#fff', fontSize: 11, padding: '5px 10px', cursor: 'pointer',
                    }}>Go</button>
                </div>
            </div>
            <div style={{ overflowY: 'auto', flex: 1, padding: '8px 0' }}>
                {papers.length === 0
                    ? <p style={{ color: '#64748b', fontSize: 11, padding: '8px 14px' }}>No cached papers yet.</p>
                    : papers.map((p, i) => (
                        <div key={i} style={{
                            padding: '8px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)',
                        }}>
                            <p style={{ color: '#e2e8f0', fontSize: 11, fontWeight: 600, margin: '0 0 3px', lineHeight: 1.3 }}>
                                {p.title}
                            </p>
                            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                                <span style={{ ...tagStyle, color: srcColor(p.source, 'paper'), fontSize: 9 }}>
                                    {p.source || 'Unknown'}
                                </span>
                                {p.year && <span style={{ ...tagStyle, fontSize: 9 }}>{p.year}</span>}
                                {p.language === 'id' && <span style={{ ...tagStyle, fontSize: 9 }}>🇮🇩</span>}
                            </div>
                        </div>
                    ))
                }
            </div>
        </div>
    );
}

const GraphPage = ({ workspaceId }) => {
    const [mode, setMode] = useState('knowledge');
    const [nodes, setNodes] = useState([]);
    const [edges, setEdges] = useState([]);
    const [loading, setLoading] = useState(false);
    const [selectedNode, setSelectedNode] = useState(null);
    const [cachedPapers, setCachedPapers] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [graphStats, setGraphStats] = useState(null);
    const [showSidebar, setShowSidebar] = useState(true);

    useEffect(() => { loadGraph(); }, [workspaceId, mode]);

    const loadGraph = async () => {
        setLoading(true);
        setSelectedNode(null);
        try {
            let data;
            if (mode === 'knowledge') {
                data = await api.getGraph(workspaceId);
            } else {
                data = await api.getCitationGraph();
                const cacheData = await api.getCachedJournals();
                setCachedPapers(cacheData.papers || []);
                setGraphStats(cacheData.graph_stats || null);
            }
            applyGraphData(data);
        } catch (err) {
            console.error('[GraphPage]', err);
        } finally {
            setLoading(false);
        }
    };

    const applyGraphData = (data) => {
        const raw = (data && data.nodes) || [];
        const rawEdges = (data && data.edges) || [];
        if (!raw.length) { setNodes([]); setEdges([]); return; }
        const { nodes: lNodes, edges: lEdges } = autoLayout(raw, rawEdges);
        setNodes(lNodes);
        setEdges(lEdges);
    };

    const handleSearch = async (q) => {
        if (!q.trim()) { loadGraph(); return; }
        try {
            const res = await api.findCachedJournal(q, 20);
            setCachedPapers(res.cache_hits || []);
            setNodes(prev => prev.map(n => ({
                ...n,
                style: {
                    ...n.style,
                    opacity: (res.cache_hits || []).some(
                        h => (h.title || '').toLowerCase().includes(q.toLowerCase())
                    ) ? 1 : 0.25,
                },
            })));
        } catch (e) { console.error(e); }
    };

    const onNodesChange = useCallback(
        (changes) => setNodes(nds => applyNodeChanges(changes, nds)), []
    );
    const onEdgesChange = useCallback(
        (changes) => setEdges(eds => applyEdgeChanges(changes, eds)), []
    );
    const onNodeClick = useCallback((_, node) => setSelectedNode(node), []);

    return (
        <div className="h-full w-full relative bg-notebook-bg">

            {/* Mode toggle */}
            <div style={{
                position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
                zIndex: 30, display: 'flex', gap: 0,
                background: 'rgba(15,17,23,0.92)', border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 40, padding: 4, backdropFilter: 'blur(10px)',
                boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            }}>
                {[['knowledge', '🧠 Knowledge Graph'], ['citation', '🕸️ Citation Graph']].map(([m, label]) => (
                    <button key={m} onClick={() => setMode(m)} style={{
                        padding: '6px 18px', borderRadius: 36, border: 'none',
                        background: mode === m ? '#3b82f6' : 'transparent',
                        color: mode === m ? '#fff' : '#64748b',
                        fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        transition: 'all 0.2s',
                    }}>{label}</button>
                ))}
            </div>

            {/* Sidebar toggle (citation mode) */}
            {mode === 'citation' && (
                <button onClick={() => setShowSidebar(v => !v)} style={{
                    position: 'absolute', top: 16, left: 16, zIndex: 40,
                    background: 'rgba(15,17,23,0.9)', border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8, color: '#94a3b8', fontSize: 11,
                    padding: '6px 12px', cursor: 'pointer',
                }}>
                    {showSidebar ? '◀ Hide' : '▶ Papers'}
                </button>
            )}

            {/* Cached papers sidebar */}
            {mode === 'citation' && showSidebar && (
                <CachedSidebar
                    papers={cachedPapers}
                    onSearch={handleSearch}
                    query={searchQuery}
                    setQuery={setSearchQuery}
                    stats={graphStats}
                />
            )}

            {/* Node detail */}
            {selectedNode && (
                <NodeDetail node={selectedNode} onClose={() => setSelectedNode(null)} />
            )}

            {/* Loading overlay */}
            {loading && (
                <div style={{
                    position: 'absolute', inset: 0, zIndex: 50,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)',
                }}>
                    <div style={{ color: '#60a5fa', fontSize: 14, fontWeight: 600 }}>
                        Loading graph…
                    </div>
                </div>
            )}

            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                fitView
                fitViewOptions={{ padding: 0.15 }}
            >
                <Background color="#1e2330" gap={24} size={1} />
                <Controls
                    className="bg-notebook-card border border-notebook-border fill-notebook-text-primary
                               text-notebook-text-primary rounded-lg overflow-hidden shadow-xl"
                    showInteractive={false}
                />
                <MiniMap
                    nodeColor={n => srcColor(n.data && n.data.source, n.data && n.data.node_type)}
                    style={{
                        background: 'rgba(15,17,23,0.85)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 8,
                    }}
                />
            </ReactFlow>

            {mode === 'citation' && <LegendPanel />}

            {/* Empty state */}
            {!loading && nodes.length === 0 && (
                <div style={{
                    position: 'absolute', inset: 0, zIndex: 10,
                    display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center',
                    pointerEvents: 'none',
                }}>
                    <p style={{ color: '#334155', fontSize: 40, marginBottom: 8 }}>
                        {mode === 'citation' ? '🕸️' : '🧠'}
                    </p>
                    <p style={{ color: '#475569', fontSize: 13 }}>
                        {mode === 'citation'
                            ? 'No journals processed yet. Search journals to populate this graph.'
                            : 'Start researching to build the knowledge graph.'}
                    </p>
                </div>
            )}
        </div>
    );
};

export default GraphPage;