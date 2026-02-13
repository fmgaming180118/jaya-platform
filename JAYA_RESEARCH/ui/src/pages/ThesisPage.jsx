import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { BookOpen, Activity, Shield_Check, FileText, BarChart2, ToggleLeft, ToggleRight } from 'lucide-react';

const ThesisPage = () => {
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

    useEffect(() => {
        fetchMode();
        fetchExperiments();
    }, []);

    const fetchMode = async () => {
        try {
            const res = await fetch('http://localhost:8000/evolution/status');
            const data = await res.json();
            setMode(data.mode);
        } catch (e) {
            console.error(e);
        }
    };

    const fetchExperiments = async () => {
        try {
            const res = await fetch('http://localhost:8000/academic/experiments');
            const data = await res.json();
            setExperiments(data.experiments);
        } catch (e) {
            console.error(e);
        }
    };

    const toggleMode = async () => {
        const newMode = mode === 'thesis' ? 'exploration' : 'thesis';
        try {
            await fetch(`http://localhost:8000/evolution/mode?mode=${newMode}`, { method: 'POST' });
            setMode(newMode);
        } catch (e) {
            console.error(e);
        }
    };

    const runDefense = async () => {
        if (!topic) return;
        setLoading(true);
        try {
            const res = await fetch(`http://localhost:8000/academic/defense?topic=${topic}&abstract=Automated+research+using+digital+twin`, { method: 'POST' });
            const data = await res.json();
            setDefenseQ(data.questions);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    const findGaps = async () => {
        if (!topic) return;
        setLoading(true);
        try {
            const res = await fetch(`http://localhost:8000/academic/gaps?topic=${topic}`, { method: 'POST' });
            const data = await res.json();
            setGapReport(data.report);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    const generateSlides = async () => {
        if (!topic) return;
        setLoading(true);
        try {
            const res = await fetch(`http://localhost:8000/academic/slides?topic=${topic}`, { method: 'POST' });
            const data = await res.json();
            setSlides(data.slides);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    const reviseDraft = async () => {
        if (!draft || !critique) return;
        setLoading(true);
        try {
            const res = await fetch(`http://localhost:8000/academic/revise?draft=${encodeURIComponent(draft)}&critique=${encodeURIComponent(critique)}`, { method: 'POST' });
            const data = await res.json();
            setRevision(data.revised_draft);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    return (
        <div className="h-full flex flex-col p-6 bg-black/40 text-gray-100 overflow-y-auto">
            {/* Header & Mode Switch */}
            <header className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-3">
                        <BookOpen className="text-yellow-400" />
                        Thesis & Research Control
                    </h1>
                    <p className="text-gray-400 text-sm">Manage academic mode, experiments, and defense.</p>
                </div>

                <button
                    onClick={toggleMode}
                    className={`flex items-center gap-3 px-6 py-3 rounded-full border transition-all ${mode === 'thesis'
                        ? 'bg-yellow-500/10 border-yellow-500 text-yellow-400'
                        : 'bg-blue-500/10 border-blue-500 text-blue-400'
                        }`}
                >
                    <span className="font-bold uppercase tracking-wider">{mode} MODE</span>
                    {mode === 'thesis' ? <ToggleRight size={28} /> : <ToggleLeft size={28} />}
                </button>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

                {/* 1. Experiment Tracker */}
                <div className="bg-gray-900/50 p-6 rounded-2xl border border-gray-800">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                        <Activity className="text-green-400" /> Experiment Logs
                    </h2>
                    <div className="space-y-2 max-h-60 overflow-y-auto mb-4">
                        {experiments.map(exp => (
                            <div
                                key={exp}
                                onClick={() => setSelectedExp(exp)}
                                className={`p-3 rounded-lg cursor-pointer border ${selectedExp === exp ? 'border-green-500 bg-green-500/10' : 'border-gray-800 hover:border-gray-600'}`}
                            >
                                <div className="text-sm font-mono">{exp}</div>
                            </div>
                        ))}
                    </div>

                    {selectedExp && (
                        <div className="mt-4 p-4 bg-black/30 rounded-lg">
                            <h3 className="text-sm font-bold text-gray-400 mb-2">Metrics Visualization</h3>
                            <img
                                src={`http://localhost:8000/academic/experiments/${selectedExp}/chart?metric=success`}
                                alt="Chart"
                                className="w-full rounded border border-gray-700"
                                onError={(e) => e.target.style.display = 'none'}
                            />
                            <p className="text-xs text-gray-500 mt-2 text-center">Showing success/fail rate over time</p>
                        </div>
                    )}
                </div>

                {/* 2. Thesis Defense Simulator */}
                <div className="bg-gray-900/50 p-6 rounded-2xl border border-gray-800">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                        <Shield_Check className="text-red-400" /> Defense Simulator
                    </h2>
                    <div className="flex gap-2 mb-4">
                        <input
                            type="text"
                            placeholder="Enter Thesis Topic..."
                            value={topic}
                            onChange={(e) => setTopic(e.target.value)}
                            className="flex-1 bg-black/50 border border-gray-700 rounded px-4 py-2 text-white"
                        />
                        <button
                            onClick={runDefense}
                            className="bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500 rounded px-4 py-2 font-bold"
                        >
                            SIMULATE
                        </button>
                    </div>

                    {defenseQ && (
                        <div className="space-y-4">
                            <div className="p-4 bg-red-900/10 border border-red-500/30 rounded-lg">
                                <h3 className="font-bold text-red-300 mb-2">⚠️ Supervisor Questions:</h3>
                                <pre className="whitespace-pre-wrap font-sans text-sm text-gray-300">
                                    {defenseQ}
                                </pre>
                            </div>
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
};

export default ThesisPage;
