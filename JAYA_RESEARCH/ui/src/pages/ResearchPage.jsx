import { useState, useEffect, useRef } from 'react';
import { Play, RotateCw, CheckCircle2, FileText, FlaskConical, Layout, AlertCircle } from 'lucide-react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import api from '../services/api';

const MOCK_REPORTS = {
    1: `# Neural JIT Compilation

## Executive Summary
Initial analysis suggests that neural compilation techniques can be optimized using a ternary-weight approach, reducing memory bandwidth by 60% while maintaining accuracy within 1% of the baseline FP32 models.

## Key Findings
- **Architecture search** revealed 3 potential candidates for JIT optimization.
- **Memory footprint** reduced by a significant factor using sparse gating.
- **Latency** improved by 15ms on average inference calls.

## Methodology
We employ a JIT compiler sandbox using a custom mutator. This sandbox compiles the active subnetworks on-the-fly and caches their execution paths.`,
    2: `# Self-Modifying Architectures

## Executive Summary
Exploration of self-modifying neural topologies has demonstrated that dynamic edge rewriting during the forward pass is viable. This reduces the parameters required for context switching by up to 40%.

## Key Findings
- **Adaptive Routing:** Gating functions can dynamically rewrite pathway weights based on input class.
- **Hardware Efficiency:** Direct mapping of ternary weights to binary kernels shows a 2.3x speedup on edge CPUs.
- **Memory Optimization:** Pruning inactive paths on-demand prevents RAM bloating.

## Future Outlook
Hardware acceleration targeting AVX-512 and ARM Neon registers will yield the highest gains.`
};

export default function ResearchPage({ workspaceId }) {
    const [topic, setTopic] = useState('');
    const [status, setStatus] = useState('idle');
    const [activeReport, setActiveReport] = useState(1);
    const pollingRef = useRef(null);

    // Initializer to load tasks from localStorage
    const getInitialTasks = () => {
        const saved = localStorage.getItem(`jaya_tasks_${workspaceId}`);
        if (saved) {
            try {
                return JSON.parse(saved);
            } catch (e) {
                console.error("Failed to parse saved tasks:", e);
            }
        }
        return [
            { id: 1, topic: "Neural JIT Compilation", status: "completed", progress: 100, date: '2h ago', report: MOCK_REPORTS[1] },
            { id: 2, topic: "Self-Modifying Architectures", status: "running", progress: 45, date: 'Just now', report: null },
        ];
    };

    const [tasks, setTasks] = useState(getInitialTasks);

    // Persist tasks to localStorage whenever they change
    useEffect(() => {
        localStorage.setItem(`jaya_tasks_${workspaceId}`, JSON.stringify(tasks));
    }, [tasks, workspaceId]);

    // Time ago formatter helper
    const formatTime = (ts) => {
        const diff = Math.floor(Date.now() / 1000 - ts);
        if (diff < 10) return "Just now";
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return new Date(ts * 1000).toLocaleDateString();
    };

    // Fetch reports history from backend
    const fetchHistory = async () => {
        try {
            const history = await api.getHistory();
            if (Array.isArray(history)) {
                // Map database entries to task format
                const dbTasks = history.map(entry => ({
                    id: entry.timestamp,
                    topic: entry.metadata?.topic || "Unknown Research",
                    status: "completed",
                    progress: 100,
                    date: formatTime(entry.timestamp),
                    report: entry.code
                }));

                setTasks(prev => {
                    // Update any existing tasks matching by topic if found in history
                    const updated = prev.map(task => {
                        const dbMatch = dbTasks.find(db => db.topic.toLowerCase() === task.topic.toLowerCase());
                        if (dbMatch) {
                            return {
                                ...task,
                                status: "completed",
                                progress: 100,
                                report: dbMatch.report,
                                date: dbMatch.date
                            };
                        }
                        return task;
                    });

                    // Add new database reports not currently in the task list
                    const newDbTasks = dbTasks.filter(db => 
                        !updated.some(task => task.topic.toLowerCase() === db.topic.toLowerCase())
                    );

                    return [...newDbTasks, ...updated];
                });
            }
        } catch (err) {
            console.error("Failed to fetch history:", err);
        }
    };

    // Load history on mount and start polling
    useEffect(() => {
        fetchHistory();
        pollingRef.current = setInterval(fetchHistory, 4000);
        
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, [workspaceId]);

    // Simulate progress of running tasks in UI
    useEffect(() => {
        const progressInterval = setInterval(() => {
            setTasks(prev => 
                prev.map(task => {
                    if (task.status === 'running') {
                        const increment = Math.floor(Math.random() * 4) + 1;
                        const nextProgress = Math.min(task.progress + increment, 98);
                        
                        // If it is the mock running task (ID 2), auto-complete it around 95%
                        if (task.id === 2 && nextProgress >= 90) {
                            return { 
                                ...task, 
                                progress: 100, 
                                status: 'completed', 
                                report: MOCK_REPORTS[2], 
                                date: 'Just now' 
                            };
                        }
                        
                        return { ...task, progress: nextProgress };
                    }
                    return task;
                })
            );
        }, 2000);

        return () => clearInterval(progressInterval);
    }, []);

    const startResearch = async () => {
        if (!topic.trim()) return;
        setStatus('running');
        const newTaskId = Date.now();
        const currentTopic = topic;
        
        try {
            // Add task to running list
            setTasks(prev => [
                { id: newTaskId, topic: currentTopic, status: 'running', progress: 0, date: 'Just now', report: null },
                ...prev
            ]);
            setActiveReport(newTaskId);
            setTopic('');

            await api.startResearch(currentTopic, "", workspaceId);
            setStatus('idle');
        } catch (err) {
            console.error(err);
            setStatus('error');
            setTasks(prev => 
                prev.map(t => t.id === newTaskId ? { ...t, status: 'error', progress: 0 } : t)
            );
        }
    };

    const activeTask = tasks.find(t => t.id === activeReport);

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
                        onKeyDown={(e) => e.key === 'Enter' && startResearch()}
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
                        <span className="text-xs bg-notebook-card px-2 py-1 rounded text-notebook-text-secondary border border-notebook-border">
                            {tasks.length} Total
                        </span>
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
                                    <h4 className="font-medium text-notebook-text-primary group-hover:text-notebook-text-accent transition-colors line-clamp-1">
                                        {task.topic}
                                    </h4>
                                    {task.status === 'running' ? (
                                        <div className="flex items-center gap-2 text-xs text-notebook-text-accent bg-notebook-text-accent/10 px-2 py-1 rounded-full">
                                            <RotateCw size={12} className="animate-spin" />
                                            RUNNING
                                        </div>
                                    ) : task.status === 'error' ? (
                                        <div className="flex items-center gap-2 text-xs text-red-400 bg-red-400/10 px-2 py-1 rounded-full">
                                            <AlertCircle size={12} />
                                            ERROR
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
                                            className={clsx(
                                                "h-full rounded-full transition-all duration-500", 
                                                task.status === 'completed' ? "bg-notebook-text-success" : 
                                                task.status === 'error' ? "bg-red-400" : "bg-notebook-text-accent"
                                            )}
                                            style={{ width: `${task.progress}%` }}
                                        />
                                    </div>
                                </div>
                                <div className="mt-4 pt-3 border-t border-notebook-border/50 flex justify-between items-center text-xs text-notebook-text-secondary">
                                    <span>{task.date}</span>
                                    <span className="flex items-center gap-1 group-hover:text-notebook-text-primary transition-colors">
                                        {task.status === 'completed' ? "View Report" : "Checking Status"} <FileText size={12} />
                                    </span>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>

                {/* Report Viewer */}
                <div className="lg:col-span-8 bg-notebook-card border border-notebook-border rounded-2xl min-h-[600px] p-8 relative shadow-sm">
                    {activeTask ? (
                        <div className="prose prose-invert prose-p:text-notebook-text-secondary prose-headings:text-notebook-text-primary max-w-none">
                            <div className="flex items-center gap-3 mb-6">
                                <span className="p-3 bg-blue-500/10 rounded-xl text-blue-400">
                                    <Layout size={24} />
                                </span>
                                <div>
                                    <h2 className="text-2xl font-bold m-0">{activeTask.topic}</h2>
                                    <p className="text-sm text-notebook-text-secondary m-0 mt-1">Generated Report • {workspaceId}</p>
                                </div>
                            </div>

                            {activeTask.status === 'completed' && activeTask.report ? (
                                <div className="markdown-content">
                                    <ReactMarkdown>{activeTask.report}</ReactMarkdown>
                                </div>
                            ) : activeTask.status === 'running' ? (
                                <div className="flex flex-col items-center justify-center py-20 text-notebook-text-secondary">
                                    <RotateCw size={48} className="animate-spin mb-4 text-notebook-text-accent" />
                                    <h3 className="text-lg font-medium text-notebook-text-primary mb-2">Researching: {activeTask.topic}</h3>
                                    <p className="max-w-md text-center text-sm mb-4">
                                        JAYA is scraping relevant papers, analyzing research graphs, and drafting the final scientific report in the background.
                                    </p>
                                    <div className="w-64 bg-black/40 h-2 rounded-full overflow-hidden mb-2">
                                        <div 
                                            className="h-full bg-notebook-text-accent rounded-full transition-all duration-300" 
                                            style={{ width: `${activeTask.progress}%` }} 
                                        />
                                    </div>
                                    <span className="text-xs">{activeTask.progress}% Complete</span>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center py-20 text-red-400">
                                    <AlertCircle size={48} className="mb-4" />
                                    <h3 className="text-lg font-medium mb-2">Research Failed</h3>
                                    <p className="max-w-md text-center text-sm">
                                        An error occurred while compiling findings. Please check the backend logs for details.
                                    </p>
                                </div>
                            )}
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
