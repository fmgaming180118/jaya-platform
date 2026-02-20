import { useState } from 'react';
import { Play, RotateCw, CheckCircle2, FileText, FlaskConical, Layout } from 'lucide-react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import api from '../services/api';

export default function ResearchPage({ workspaceId }) {
    const [topic, setTopic] = useState('');
    const [status, setStatus] = useState('idle');
    const [tasks, setTasks] = useState([
        { id: 1, topic: "Neural JIT Compilation", status: "completed", progress: 100, date: '2h ago' },
        { id: 2, topic: "Self-Modifying Architectures", status: "running", progress: 45, date: 'Just now' },
    ]);

    const [activeReport, setActiveReport] = useState(null);

    const startResearch = async () => {
        if (!topic.trim()) return;
        setStatus('running');
        try {
            await api.startResearch(topic, "", workspaceId);
            setStatus('completed');
            // Add to task list mock
            setTasks(prev => [...prev, { id: Date.now(), topic, status: 'running', progress: 0, date: 'Just now' }]);
        } catch (err) {
            console.error(err);
            setStatus('error');
        }
    };

    return (
        <div className="p-8 h-full overflow-y-auto bg-notebook-bg text-notebook-text-primary">
            <header className="mb-10 flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-semibold mb-2 flex items-center gap-3">
                        <span className="p-2 bg-purple-500/10 rounded-lg text-purple-400">
                            <FlaskConical size={24} />
                        </span>
                        Deep Research
                    </h1>
                    <p className="text-notebook-text-secondary text-sm ml-1">Autonomous multi-step research agent</p>
                </div>
                <div className="flex gap-3 bg-notebook-card p-1.5 rounded-xl border border-notebook-border shadow-sm">
                    <input
                        value={topic}
                        onChange={(e) => setTopic(e.target.value)}
                        placeholder="Enter research topic..."
                        className="bg-transparent text-notebook-text-primary px-4 py-2 w-64 focus:outline-none placeholder:text-notebook-text-secondary/50"
                    />
                    <button
                        onClick={startResearch}
                        disabled={status === 'running'}
                        className="bg-notebook-text-primary hover:bg-white text-notebook-bg px-6 py-2 rounded-lg flex items-center gap-2 font-medium transition-colors disabled:opacity-50"
                    >
                        {status === 'running' ? <RotateCw size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
                        <span>Start</span>
                    </button>
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* Task List */}
                <div className="lg:col-span-4 space-y-6">
                    <div className="flex items-center justify-between">
                        <h3 className="text-xs font-semibold text-notebook-text-secondary uppercase tracking-wider">Research Operations</h3>
                        <span className="text-xs bg-notebook-card px-2 py-1 rounded text-notebook-text-secondary border border-notebook-border">3 Active</span>
                    </div>

                    <div className="space-y-3">
                        {tasks.map(task => (
                            <motion.div
                                key={task.id}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                className={clsx(
                                    "group bg-notebook-card border border-notebook-border rounded-xl p-5 cursor-pointer transition-all hover:shadow-md",
                                    activeReport === task.id ? "border-notebook-text-accent ring-1 ring-notebook-text-accent/20" : "hover:border-notebook-text-secondary/30"
                                )}
                                onClick={() => setActiveReport(task.id)}
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <h4 className="font-medium text-notebook-text-primary group-hover:text-notebook-text-accent transition-colors line-clamp-1">{task.topic}</h4>
                                    {task.status === 'running' ? (
                                        <div className="flex items-center gap-2 text-xs text-notebook-text-accent bg-notebook-text-accent/10 px-2 py-1 rounded-full">
                                            <RotateCw size={12} className="animate-spin" />
                                            RUNNING
                                        </div>
                                    ) : (
                                        <div className="flex items-center gap-2 text-xs text-notebook-text-success bg-notebook-text-success/10 px-2 py-1 rounded-full">
                                            <CheckCircle2 size={12} />
                                            DONE
                                        </div>
                                    )}
                                </div>

                                <div className="space-y-2">
                                    <div className="flex justify-between text-xs text-notebook-text-secondary">
                                        <span>Progress</span>
                                        <span>{task.progress}%</span>
                                    </div>
                                    <div className="w-full bg-black/40 h-1.5 rounded-full overflow-hidden">
                                        <div
                                            className={clsx("h-full rounded-full transition-all duration-500", task.status === 'completed' ? "bg-notebook-text-success" : "bg-notebook-text-accent")}
                                            style={{ width: `${task.progress}%` }}
                                        />
                                    </div>
                                </div>
                                <div className="mt-4 pt-3 border-t border-notebook-border/50 flex justify-between items-center text-xs text-notebook-text-secondary">
                                    <span>{task.date}</span>
                                    <span className="flex items-center gap-1 group-hover:text-notebook-text-primary transition-colors">
                                        View Report <FileText size={12} />
                                    </span>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>

                {/* Report Viewer */}
                <div className="lg:col-span-8 bg-notebook-card border border-notebook-border rounded-2xl min-h-[600px] p-8 relative shadow-sm">
                    {activeReport ? (
                        <div className="prose prose-invert prose-p:text-notebook-text-secondary prose-headings:text-notebook-text-primary max-w-none">
                            <div className="flex items-center gap-3 mb-6">
                                <span className="p-3 bg-blue-500/10 rounded-xl text-blue-400">
                                    <Layout size={24} />
                                </span>
                                <div>
                                    <h2 className="text-2xl font-bold m-0">{tasks.find(t => t.id === activeReport)?.topic}</h2>
                                    <p className="text-sm text-notebook-text-secondary m-0 mt-1">Generated Report • {workspaceId}</p>
                                </div>
                            </div>

                            <div className="bg-notebook-bg rounded-xl p-6 border border-notebook-border mb-8">
                                <h3 className="text-lg font-semibold mb-4 mt-0">Executive Summary</h3>
                                <p>
                                    Initial analysis suggests that neural compilation techniques can be optimized using a ternary-weight approach, reducing memory bandwidth by 60% while maintaining accuracy within 1% of the baseline FP32 models.
                                </p>
                            </div>

                            <h3>Key Findings</h3>
                            <ul>
                                <li>Architecture search revealed 3 potential candidates for JIT optimization.</li>
                                <li>Memory footprint reduced by significant factor using sparse gating.</li>
                                <li>Latency improved by 15ms on average inference calls.</li>
                            </ul>

                            <hr className="border-notebook-border my-8" />

                            <div className="flex items-center justify-center p-8 border border-dashed border-notebook-border rounded-xl bg-notebook-bg/50 text-notebook-text-secondary text-sm">
                                Full report content loading from {workspaceId}...
                            </div>
                        </div>
                    ) : (
                        <div className="absolute inset-0 flex flex-col items-center justify-center text-notebook-text-secondary">
                            <div className="w-20 h-20 bg-notebook-bg rounded-full flex items-center justify-center mb-6 border border-notebook-border shadow-inner">
                                <FileText size={32} className="opacity-50" />
                            </div>
                            <h3 className="text-lg font-medium text-notebook-text-primary mb-2">No Report Selected</h3>
                            <p className="max-w-md text-center">Select a research task from the sidebar to view its detailed analysis, findings, and generated artifacts.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
