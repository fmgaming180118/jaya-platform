import { useState, useEffect } from 'react';
import { BookOpen, Activity, ShieldCheck, FileText, BarChart2, ToggleLeft, ToggleRight, GraduationCap, PenTool } from 'lucide-react';
import clsx from 'clsx';

const ThesisPage = ({ workspaceId }) => {
    const [mode, setMode] = useState('exploration');
    const [experiments, setExperiments] = useState([]);
    const [selectedExp, setSelectedExp] = useState(null);
    const [gapReport, setGapReport] = useState(null);
    const [slides, setSlides] = useState(null);
    const [revision, setRevision] = useState(null);
    const [draft, setDraft] = useState('');
    const [critique, setCritique] = useState('');
    const [topic, setTopic] = useState('');
    const [loading, setLoading] = useState(false);
    const [defenseQ, setDefenseQ] = useState(null);

    useEffect(() => {
        fetchMode();
        fetchExperiments();
    }, [workspaceId]);

    const fetchMode = async () => {
        try {
            const res = await fetch(`http://localhost:8000/evolution/status?workspace_id=${workspaceId}`);
            const data = await res.json();
            setMode(data.mode);
        } catch (e) {
            console.error(e);
        }
    };

    const fetchExperiments = async () => {
        try {
            const res = await fetch(`http://localhost:8000/academic/experiments?workspace_id=${workspaceId}`);
            const data = await res.json();
            setExperiments(data.experiments || []);
        } catch (e) {
            console.error(e);
        }
    };

    const toggleMode = async () => {
        const newMode = mode === 'thesis' ? 'exploration' : 'thesis';
        try {
            await fetch(`http://localhost:8000/evolution/mode?mode=${newMode}&workspace_id=${workspaceId}`, { method: 'POST' });
            setMode(newMode);
        } catch (e) {
            console.error(e);
        }
    };

    const runDefense = async () => {
        if (!topic) return;
        setLoading(true);
        try {
            const res = await fetch(`http://localhost:8000/academic/defense?topic=${topic}&abstract=Automated+research+using+digital+twin&workspace_id=${workspaceId}`, { method: 'POST' });
            const data = await res.json();
            setDefenseQ(data.questions);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    return (
        <div className="h-full flex flex-col p-8 bg-notebook-bg text-notebook-text-primary overflow-y-auto">
            {/* Header & Mode Switch */}
            <header className="flex items-center justify-between mb-10">
                <div>
                    <h1 className="text-3xl font-semibold flex items-center gap-3 mb-1">
                        <span className="p-2 bg-yellow-500/10 rounded-lg text-yellow-500">
                            <GraduationCap size={28} />
                        </span>
                        Thesis & Research Control
                    </h1>
                    <p className="text-notebook-text-secondary text-sm ml-1">Manage academic mode, experiments, and defense simulations.</p>
                </div>

                <div className="flex items-center gap-4 bg-notebook-card p-1.5 rounded-full border border-notebook-border">
                    <button
                        onClick={() => mode !== 'exploration' && toggleMode()}
                        className={clsx(
                            "px-6 py-2 rounded-full text-sm font-medium transition-all",
                            mode === 'exploration' ? "bg-notebook-text-accent text-notebook-bg shadow-sm" : "text-notebook-text-secondary hover:text-notebook-text-primary"
                        )}
                    >
                        Exploration
                    </button>
                    <button
                        onClick={() => mode !== 'thesis' && toggleMode()}
                        className={clsx(
                            "px-6 py-2 rounded-full text-sm font-medium transition-all",
                            mode === 'thesis' ? "bg-yellow-500 text-notebook-bg shadow-sm" : "text-notebook-text-secondary hover:text-notebook-text-primary"
                        )}
                    >
                        Thesis Mode
                    </button>
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

                {/* 1. Experiment Tracker */}
                <div className="bg-notebook-card p-6 rounded-2xl border border-notebook-border shadow-sm">
                    <div className="flex justify-between items-center mb-6">
                        <h2 className="text-lg font-semibold flex items-center gap-2">
                            <Activity className="text-green-400" size={20} />
                            Experiment Logs
                        </h2>
                        <span className="text-xs bg-notebook-bg px-2 py-1 rounded text-notebook-text-secondary border border-notebook-border">{experiments.length} Records</span>
                    </div>

                    <div className="space-y-2 max-h-80 overflow-y-auto mb-4 pr-2">
                        {experiments.length === 0 && <div className="text-notebook-text-secondary text-sm italic py-4 text-center">No experiments recorded yet.</div>}
                        {experiments.map(exp => (
                            <div
                                key={exp}
                                onClick={() => setSelectedExp(exp)}
                                className={clsx(
                                    "p-3 rounded-lg cursor-pointer border transition-all flex items-center justify-between group",
                                    selectedExp === exp
                                        ? "border-green-500/50 bg-green-500/10"
                                        : "border-notebook-border bg-notebook-bg hover:border-notebook-text-secondary/30"
                                )}
                            >
                                <div className="text-sm font-mono text-notebook-text-primary">{exp}</div>
                                <Activity size={14} className={clsx("transition-opacity", selectedExp === exp ? "opacity-100 text-green-400" : "opacity-0 group-hover:opacity-50 text-notebook-text-secondary")} />
                            </div>
                        ))}
                    </div>

                    {selectedExp && (
                        <div className="mt-4 p-4 bg-notebook-bg rounded-xl border border-notebook-border">
                            <h3 className="text-xs font-bold text-notebook-text-secondary uppercase tracking-wider mb-3">Metrics Visualization</h3>
                            <div className="aspect-video bg-notebook-card rounded-lg flex items-center justify-center border border-notebook-border border-dashed text-notebook-text-secondary text-sm">
                                [Chart Visualization Placeholder for {selectedExp}]
                            </div>
                        </div>
                    )}
                </div>

                {/* 2. Thesis Defense Simulator */}
                <div className="bg-notebook-card p-6 rounded-2xl border border-notebook-border shadow-sm">
                    <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
                        <ShieldCheck className="text-red-400" size={20} />
                        Defense Simulator
                    </h2>

                    <div className="bg-notebook-bg p-1.5 rounded-xl border border-notebook-border flex items-center gap-2 mb-6 focus-within:ring-2 focus-within:ring-red-500/20 transition-shadow">
                        <input
                            type="text"
                            placeholder="Enter Thesis Topic for Simulation..."
                            value={topic}
                            onChange={(e) => setTopic(e.target.value)}
                            className="flex-1 bg-transparent border-none focus:ring-0 text-notebook-text-primary px-3 py-2 placeholder:text-notebook-text-secondary/50"
                        />
                        <button
                            onClick={runDefense}
                            disabled={loading}
                            className="bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg px-4 py-2 text-sm font-bold transition-colors disabled:opacity-50"
                        >
                            {loading ? "Simulating..." : "SIMULATE"}
                        </button>
                    </div>

                    {defenseQ ? (
                        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="p-5 bg-red-950/20 border border-red-500/20 rounded-xl">
                                <h3 className="font-bold text-red-300 mb-3 flex items-center gap-2">
                                    <span className="relative flex h-2 w-2">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                                        <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                                    </span>
                                    Supervisor Questions:
                                </h3>
                                <div className="prose prose-invert prose-sm max-w-none text-notebook-text-primary">
                                    <pre className="whitespace-pre-wrap font-sans text-sm bg-transparent border-none p-0 m-0">
                                        {defenseQ}
                                    </pre>
                                </div>
                            </div>

                            <div className="flex gap-2 justify-end">
                                <button className="text-xs text-notebook-text-secondary hover:text-notebook-text-primary flex items-center gap-1">
                                    <PenTool size={12} /> Respond to Questions
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-12 text-notebook-text-secondary border border-dashed border-notebook-border rounded-xl bg-notebook-bg/30">
                            <ShieldCheck size={32} className="opacity-20 mb-2" />
                            <p className="text-sm">Enter a topic to start defense simulation</p>
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
};

export default ThesisPage;
