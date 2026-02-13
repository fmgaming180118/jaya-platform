import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Sparkles, Activity, Terminal } from 'lucide-react';
import api from '../services/api';

const EvolutionPage = () => {
    const [status, setStatus] = useState({
        state: 'idle',
        is_awake: false,
        latest_thought: null,
        recent_history: []
    });

    // Polling hook
    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch('http://localhost:8000/evolution/status');
                const data = await res.json();
                setStatus(data);
            } catch (e) {
                console.error("Twin offline", e);
            }
        };

        const interval = setInterval(fetchStatus, 2000);
        fetchStatus();
        return () => clearInterval(interval);
    }, []);

    const stateColors = {
        idle: "text-gray-400 border-gray-600",
        dreaming: "text-purple-400 border-purple-500 shadow-[0_0_15px_rgba(168,85,247,0.5)]",
        planning: "text-cyan-400 border-cyan-500",
        coding: "text-green-400 border-green-500",
        coding: "text-green-400 border-green-500",
        testing: "text-yellow-400 border-yellow-500",
        researching: "text-blue-400 border-blue-500"
    };

    return (
        <div className="h-full flex flex-col p-6 bg-black/40">
            {/* Header */}
            <header className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-3">
                        <Brain className={status.is_awake ? "text-cyan-400" : "text-gray-600"} />
                        Digital Twin Monitor
                    </h1>
                    <p className="text-gray-400 text-sm">Real-time visualization of JAYA's internal cognition.</p>
                </div>
                <div className={`px-4 py-2 rounded-full border ${stateColors[status.state] || stateColors.idle} font-mono uppercase text-sm font-bold transition-all duration-500`}>
                    {status.state}
                </div>
            </header>

            {/* Main Visual */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 flex-1 min-h-0">

                {/* Visualizer Column */}
                <div className="bg-gray-900/50 rounded-2xl border border-gray-800 p-8 flex flex-col items-center justify-center relative overflow-hidden">
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(56,189,248,0.1),transparent_70%)]" />

                    {/* Pulsing Brain */}
                    <motion.div
                        animate={{
                            scale: status.state === 'dreaming' ? [1, 1.1, 1] : 1,
                            opacity: status.is_awake ? 1 : 0.5
                        }}
                        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                        className="relative z-10 mb-8"
                    >
                        <Brain size={120} className={status.state === 'dreaming' ? "text-purple-500" : "text-gray-500"} />
                    </motion.div>

                    {/* DNA Helix Animation (CSS-based representation) */}
                    <div className="relative h-24 w-full max-w-xs flex justify-between items-center opacity-50">
                        {[...Array(10)].map((_, i) => (
                            <motion.div
                                key={i}
                                animate={{ y: [0, -20, 0, 20, 0] }}
                                transition={{ duration: 3, delay: i * 0.2, repeat: Infinity, ease: "linear" }}
                                className={`w-2 h-2 rounded-full ${status.state === 'coding' ? 'bg-green-500' : 'bg-blue-900'}`}
                            />
                        ))}
                        {[...Array(10)].map((_, i) => (
                            <motion.div
                                key={`b-${i}`}
                                animate={{ y: [0, 20, 0, -20, 0] }}
                                transition={{ duration: 3, delay: i * 0.2, repeat: Infinity, ease: "linear" }}
                                className={`w-2 h-2 rounded-full ${status.state === 'coding' ? 'bg-green-500' : 'bg-cyan-900'} absolute left-0 ml-[${i * 10}%]`}
                                style={{ left: `${i * 10}%` }}
                            />
                        ))}
                    </div>
                    <div className="text-xs text-gray-500 mt-2 font-mono">CODE EVOLUTION ENGINE</div>

                    {status.latest_thought && (
                        <motion.div
                            key={status.latest_thought.timestamp}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="mt-8 text-center max-w-md"
                        >
                            <p className="text-lg font-medium text-white italic">"{status.latest_thought.content}"</p>
                            <span className="text-xs text-gray-500 mt-2 block">Mood: {status.latest_thought.mood}</span>
                        </motion.div>
                    )}
                </div>

                {/* Stream Column */}
                <div className="bg-gray-900/50 rounded-2xl border border-gray-800 flex flex-col overflow-hidden">
                    <div className="p-4 border-b border-gray-800 flex items-center gap-2 bg-gray-900">
                        <Activity size={16} className="text-green-500" />
                        <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Cognition Stream</span>
                    </div>

                    <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-sm">
                        <AnimatePresence>
                            {status.recent_history.slice().reverse().map((thought) => (
                                <motion.div
                                    key={thought.timestamp}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="border-l-2 border-gray-700 pl-4 py-1"
                                >
                                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                                        <span>{new Date(thought.timestamp * 1000).toLocaleTimeString()}</span>
                                        <span className={thought.mood === 'error' ? 'text-red-400' : 'text-cyan-400'}>{thought.mood}</span>
                                    </div>
                                    <p className="text-gray-300">{thought.content}</p>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                        {status.recent_history.length === 0 && (
                            <div className="text-gray-600 text-center italic mt-10">No thoughts recorded yet...</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default EvolutionPage;
