import { useState } from 'react';
import { Play, RotateCw, CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import api from '../services/api';

export default function ResearchPage({ workspaceId }) {
    const [topic, setTopic] = useState('');
    const [status, setStatus] = useState('idle');
    const [tasks, setTasks] = useState([
        { id: 1, topic: "Neural JIT Compilation", status: "completed", progress: 100 },
        { id: 2, topic: "Self-Modifying Architectures", status: "running", progress: 45 },
    ]);

    const [activeReport, setActiveReport] = useState(null);

    const startResearch = async () => {
        if (!topic.trim()) return;
        setStatus('running');
        try {
            await api.startResearch(topic, "", workspaceId);
            setStatus('completed');
            // Add to task list mock
            setTasks(prev => [...prev, { id: Date.now(), topic, status: 'running', progress: 0 }]);
        } catch (err) {
            console.error(err);
            setStatus('error');
        }
    };

    return (
        <div className="p-8 h-full overflow-y-auto">
            <header className="mb-8 flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold mb-2">Autonomous Research</h1>
                    <p className="text-gray-400 text-sm">Manage long-running research tasks and view reports.</p>
                </div>
                <div className="flex gap-2">
                    <input
                        value={topic}
                        onChange={(e) => setTopic(e.target.value)}
                        placeholder="Research Topic..."
                        className="bg-gray-800 text-white px-3 py-2 rounded-lg border border-gray-700"
                    />
                    <button
                        onClick={startResearch}
                        disabled={status === 'running'}
                        className="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg flex items-center gap-2 font-medium shadow-lg shadow-primary/20 disabled:opacity-50"
                    >
                        <Play size={16} />
                        <span>{status === 'running' ? 'Researching...' : 'Start'}</span>
                    </button>
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Task List */}
                <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Active Tasks</h3>
                    {tasks.map(task => (
                        <motion.div
                            key={task.id}
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 cursor-pointer hover:border-primary/50 transition-colors"
                            onClick={() => setActiveReport(task.id)}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <h4 className="font-medium">{task.topic}</h4>
                                {task.status === 'running' ? (
                                    <RotateCw size={14} className="text-accent animate-spin" />
                                ) : (
                                    <CheckCircle2 size={14} className="text-green-500" />
                                )}
                            </div>
                            <div className="w-full bg-black/20 h-1.5 rounded-full overflow-hidden">
                                <div
                                    className={clsx("h-full rounded-full transition-all duration-500", task.status === 'completed' ? "bg-green-500" : "bg-accent")}
                                    style={{ width: `${task.progress}%` }}
                                />
                            </div>
                            <div className="mt-2 text-xs text-gray-500 flex justify-between">
                                <span className="capitalize">{task.status}</span>
                                <span>{task.progress}%</span>
                            </div>
                        </motion.div>
                    ))}
                </div>

                {/* Report Viewer */}
                <div className="lg:col-span-2 bg-[var(--bg-card)] border border-[var(--border)] rounded-xl min-h-[500px] p-8 relative">
                    {activeReport ? (
                        <div className="prose prose-invert max-w-none">
                            <h2>Research Report: {tasks.find(t => t.id === activeReport)?.topic}</h2>
                            <p className="lead">Executive summary of the latest findings...</p>
                            <hr className="border-[var(--border)]" />
                            <p>Loading real report content from {workspaceId} workspace...</p>
                        </div>
                    ) : (
                        <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-500">
                            <RotateCw size={48} className="mb-4 opacity-20" />
                            <p>Select a research task to view the report</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
