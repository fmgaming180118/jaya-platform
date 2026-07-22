import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Sparkles, Activity, Cpu, Play, CheckCircle, ShieldCheck } from 'lucide-react';
import clsx from 'clsx';

const EvolutionPage = () => {
    const [status, setStatus] = useState({
        state: 'idle',
        is_awake: false,
        latest_thought: null,
        latest_upgrade_result: null,
        recent_history: []
    });
    const [isUpgrading, setIsUpgrading] = useState(false);
    const [upgradeResult, setUpgradeResult] = useState(null);

    // Polling hook for status
    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch('http://localhost:8000/evolution/status');
                const data = await res.json();
                setStatus(data);
                if (data.latest_upgrade_result) {
                    setUpgradeResult(data.latest_upgrade_result);
                }
            } catch (e) {
                console.error("Evolution Bridge API offline", e);
            }
        };

        const interval = setInterval(fetchStatus, 2000);
        fetchStatus();
        return () => clearInterval(interval);
    }, []);

    // Trigger Autonomous Upgrade Button Handler
    const handleTriggerAutoUpgrade = async () => {
        setIsUpgrading(true);
        try {
            const res = await fetch('http://localhost:8000/evolution/auto-upgrade', { method: 'POST' });
            const data = await res.json();
            if (data.ok && data.result) {
                setUpgradeResult(data.result);
            }
        } catch (e) {
            console.error("Auto upgrade trigger failed", e);
        } finally {
            setIsUpgrading(false);
        }
    };

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
                        Ecosystem Auto-Upgrade & Digital Twin Monitor
                    </h1>
                    <p className="text-notebook-text-secondary text-sm ml-1">Real-time autonomous research & JAYA_CORE EvolutionGate monitoring.</p>
                </div>
                
                <div className="flex items-center gap-4">
                    {/* Interactive Autonomous Upgrade Trigger Button */}
                    <button
                        onClick={handleTriggerAutoUpgrade}
                        disabled={isUpgrading}
                        className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium text-xs tracking-wider uppercase flex items-center gap-2 shadow-lg hover:shadow-blue-500/25 transition-all disabled:opacity-50 cursor-pointer"
                    >
                        {isUpgrading ? (
                            <>
                                <Sparkles size={16} className="animate-spin text-yellow-300" />
                                <span>Menjalankan Riset Otonom...</span>
                            </>
                        ) : (
                            <>
                                <Play size={16} fill="currentColor" />
                                <span>Jalankan Auto-Upgrade Otonom</span>
                            </>
                        )}
                    </button>

                    <div className={clsx("px-6 py-2 rounded-full border font-mono uppercase text-xs font-bold transition-all duration-500 tracking-wider", stateColors[status.state] || stateColors.idle)}>
                        {status.state}
                    </div>
                </div>
            </header>

            {/* Main Visual */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 flex-1 min-h-0">

                {/* Visualizer & Upgrade Status Column */}
                <div className="bg-notebook-card rounded-2xl border border-notebook-border p-8 flex flex-col items-center justify-center relative overflow-hidden shadow-sm">
                    {/* Background Effect */}
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(138,180,248,0.03),transparent_70%)]" />

                    {/* Pulsing Brain */}
                    <motion.div
                        animate={{
                            scale: isUpgrading || status.state === 'dreaming' ? [1, 1.05, 1] : 1,
                            opacity: status.is_awake ? 1 : 0.6
                        }}
                        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                        className="relative z-10 mb-8"
                    >
                        <div className="relative">
                            <Brain size={110} className={isUpgrading ? "text-cyan-400 drop-shadow-[0_0_15px_rgba(6,182,212,0.4)]" : "text-notebook-text-accent"} />
                            {status.is_awake && <Sparkles size={36} className="text-yellow-400 absolute -top-2 -right-2 animate-pulse" />}
                        </div>
                    </motion.div>

                    {/* Live Upgrade Result Box */}
                    {upgradeResult ? (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="w-full bg-notebook-bg/80 border border-green-500/30 rounded-xl p-5 shadow-lg backdrop-blur-sm"
                        >
                            <div className="flex items-center justify-between mb-3 border-b border-notebook-border/50 pb-2">
                                <div className="flex items-center gap-2 text-green-400 font-semibold text-xs uppercase tracking-wider">
                                    <CheckCircle size={16} />
                                    <span>Pembaruan JAYA_CORE Berhasil Terpasang (ACCEPT)</span>
                                </div>
                                <span className="text-[10px] font-mono bg-green-500/20 text-green-300 px-2 py-0.5 rounded border border-green-500/30">
                                    HMAC-SHA256 Signed
                                </span>
                            </div>

                            <div className="space-y-1.5 text-xs font-mono text-notebook-text-secondary">
                                <p><span className="text-notebook-text-primary font-medium">Finding ID:</span> {upgradeResult.finding_id}</p>
                                <p><span className="text-notebook-text-primary font-medium">Candidate ID:</span> {upgradeResult.candidate_id}</p>
                                <p><span className="text-notebook-text-primary font-medium">Target Patch:</span> <code className="text-cyan-300 bg-black/40 px-1 py-0.5 rounded">auto_research_patch.py</code></p>
                                <p><span className="text-notebook-text-primary font-medium">Auto-Deployed by RESEARCH:</span> <span className="text-green-400 font-bold">TRUE</span></p>
                            </div>
                        </motion.div>
                    ) : (
                        <div className="text-xs text-notebook-text-secondary font-mono tracking-wider opacity-70">
                            Pencet tombol "Jalankan Auto-Upgrade Otonom" di atas untuk memperbarui JAYA_CORE tanpa mengetik.
                        </div>
                    )}
                </div>

                {/* Cognition Stream Column */}
                <div className="bg-notebook-card rounded-2xl border border-notebook-border flex flex-col overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-notebook-border flex items-center justify-between bg-notebook-bg/30">
                        <div className="flex items-center gap-2">
                            <ShieldCheck size={16} className="text-notebook-text-accent" />
                            <span className="text-xs font-bold uppercase tracking-wider text-notebook-text-secondary">EvolutionGate Audit Log</span>
                        </div>
                        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_5px_rgba(34,197,94,0.5)]"></div>
                    </div>

                    <div className="flex-1 overflow-y-auto p-5 space-y-4 font-mono text-sm custom-scrollbar">
                        <AnimatePresence>
                            {status.recent_history.slice().reverse().map((thought, idx) => (
                                <motion.div
                                    key={idx}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="border-l-2 border-notebook-border pl-4 py-1 hover:border-notebook-text-accent transition-colors group"
                                >
                                    <div className="flex justify-between text-[10px] text-notebook-text-secondary mb-1">
                                        <span>{new Date(thought.timestamp * 1000).toLocaleTimeString()}</span>
                                        <span className="uppercase tracking-wide font-semibold text-notebook-text-accent">{thought.mood}</span>
                                    </div>
                                    <p className="text-notebook-text-secondary group-hover:text-notebook-text-primary transition-colors leading-relaxed">{thought.content}</p>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                        {status.recent_history.length === 0 && upgradeResult && (
                            <div className="text-xs text-notebook-text-secondary font-mono p-4 bg-notebook-bg/40 rounded-lg border border-notebook-border">
                                <div className="text-green-400 font-bold mb-1">✓ EvolutionGate Decision Audit</div>
                                <div>Candidate ID: {upgradeResult.candidate_id}</div>
                                <div>Status: ACCEPT (Zero-Trust Verified)</div>
                                <div>Target: JAYA_CORE/src/brain_v2/engine/auto_research_patch.py</div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default EvolutionPage;
