import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Sparkles, Activity, Terminal, Cpu } from 'lucide-react';
import clsx from 'clsx';
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
        idle: "text-notebook-text-secondary border-notebook-text-secondary",
        dreaming: "text-purple-400 border-purple-500 shadow-[0_0_15px_rgba(168,85,247,0.3)] bg-purple-500/10",
        planning: "text-cyan-400 border-cyan-500 bg-cyan-500/10",
        coding: "text-green-400 border-green-500 bg-green-500/10",
        testing: "text-yellow-400 border-yellow-500 bg-yellow-500/10",
        researching: "text-blue-400 border-blue-500 bg-blue-500/10"
    };

    return (
        <div className="h-full flex flex-col p-8 bg-notebook-bg text-notebook-text-primary overflow-hidden">
            {/* Header */}
            <header className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-semibold mb-2 flex items-center gap-3">
                        <span className="p-2 bg-notebook-card rounded-lg border border-notebook-border text-notebook-text-accent shadow-sm">
                            <Cpu size={24} />
                        </span>
                        Digital Twin Monitor
                    </h1>
                    <p className="text-notebook-text-secondary text-sm ml-1">Real-time visualization of JAYA's internal cognition.</p>
                </div>
                <div className={clsx("px-6 py-2 rounded-full border font-mono uppercase text-xs font-bold transition-all duration-500 tracking-wider", stateColors[status.state] || stateColors.idle)}>
                    {status.state}
                </div>
            </header>

            {/* Main Visual */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 flex-1 min-h-0">

                {/* Visualizer Column */}
                <div className="bg-notebook-card rounded-2xl border border-notebook-border p-8 flex flex-col items-center justify-center relative overflow-hidden shadow-sm">
                    {/* Background Effect */}
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(138,180,248,0.03),transparent_70%)]" />

                    {/* Pulsing Brain */}
                    <motion.div
                        animate={{
                            scale: status.state === 'dreaming' ? [1, 1.05, 1] : 1,
                            opacity: status.is_awake ? 1 : 0.6
                        }}
                        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                        className="relative z-10 mb-10"
                    >
                        <div className="relative">
                            <Brain size={120} className={status.state === 'dreaming' ? "text-purple-400 drop-shadow-[0_0_15px_rgba(168,85,247,0.4)]" : "text-notebook-text-secondary"} />
                            {status.is_awake && <Sparkles size={40} className="text-yellow-400 absolute -top-2 -right-2 animate-pulse" />}
                        </div>
                    </motion.div>

                    {/* DNA Helix Animation (CSS-based representation) */}
                    <div className="relative h-24 w-full max-w-xs flex justify-between items-center opacity-30">
                        {[...Array(8)].map((_, i) => (
                            <motion.div
                                key={i}
                                animate={{ y: [0, -15, 0, 15, 0] }}
                                transition={{ duration: 4, delay: i * 0.3, repeat: Infinity, ease: "linear" }}
                                className={`w-1.5 h-1.5 rounded-full ${status.state === 'coding' ? 'bg-green-500' : 'bg-notebook-text-accent'}`}
                            />
                        ))}
                        {[...Array(8)].map((_, i) => (
                            <motion.div
                                key={`b-${i}`}
                                animate={{ y: [0, 15, 0, -15, 0] }}
                                transition={{ duration: 4, delay: i * 0.3, repeat: Infinity, ease: "linear" }}
                                className={`w-1.5 h-1.5 rounded-full ${status.state === 'coding' ? 'bg-green-500' : 'bg-notebook-text-primary'}`}
                                style={{ position: 'absolute', left: `${i * 14}%` }}
                            />
                        ))}
                    </div>
                    <div className="text-[10px] text-notebook-text-secondary mt-4 font-mono tracking-[0.2em] opacity-60">CODE EVOLUTION ENGINE v15.0</div>

                    {status.latest_thought && (
                        <motion.div
                            key={status.latest_thought.timestamp}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="mt-8 text-center max-w-md bg-notebook-bg/50 px-6 py-4 rounded-xl border border-notebook-border mx-4"
                        >
                            <p className="text-base font-medium text-notebook-text-primary italic">"{status.latest_thought.content}"</p>
                            <span className="text-xs text-notebook-text-secondary mt-2 block uppercase tracking-wide">Mood: {status.latest_thought.mood}</span>
                        </motion.div>
                    )}
                </div>

                {/* Stream Column */}
                <div className="bg-notebook-card rounded-2xl border border-notebook-border flex flex-col overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-notebook-border flex items-center justify-between bg-notebook-bg/30">
                        <div className="flex items-center gap-2">
                            <Activity size={16} className="text-notebook-text-accent" />
                            <span className="text-xs font-bold uppercase tracking-wider text-notebook-text-secondary">Cognition Stream</span>
                        </div>
                        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_5px_rgba(34,197,94,0.5)]"></div>
                    </div>

                    <div className="flex-1 overflow-y-auto p-5 space-y-4 font-mono text-sm custom-scrollbar">
                        <AnimatePresence>
                            {status.recent_history.slice().reverse().map((thought) => (
                                <motion.div
                                    key={thought.timestamp}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="border-l-2 border-notebook-border pl-4 py-1 hover:border-notebook-text-accent transition-colors group"
                                >
                                    <div className="flex justify-between text-[10px] text-notebook-text-secondary mb-1">
                                        <span>{new Date(thought.timestamp * 1000).toLocaleTimeString()}</span>
                                        <span className={clsx("uppercase tracking-wide font-semibold", thought.mood === 'error' ? 'text-notebook-text-error' : 'text-notebook-text-accent group-hover:text-notebook-text-primary transition-colors')}>{thought.mood}</span>
                                    </div>
                                    <p className="text-notebook-text-secondary group-hover:text-notebook-text-primary transition-colors leading-relaxed">{thought.content}</p>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                        {status.recent_history.length === 0 && (
                            <div className="text-notebook-text-secondary text-center italic mt-20 opacity-50">Waiting for cognitive signals...</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default EvolutionPage;
