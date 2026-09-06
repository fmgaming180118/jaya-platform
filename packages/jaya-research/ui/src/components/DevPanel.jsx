import { useEffect, useRef } from 'react';
import { X, Terminal, Settings2, Trash2, CheckCircle, XCircle, Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useApp } from '../context/AppContext';
import { getPublicEnvVars } from '../config/env';

/**
 * DevPanel — Slideout panel dari kanan, HANYA tersedia di mode DEV
 * Menampilkan: API Logs, Env Variables, Quick Actions
 */
export default function DevPanel() {
    const { isDevPanelOpen, toggleDevPanel, apiLogs, clearApiLogs } = useApp();
    const panelRef = useRef(null);

    // Close on Escape
    useEffect(() => {
        const handleKey = (e) => { if (e.key === 'Escape') toggleDevPanel(); };
        if (isDevPanelOpen) document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [isDevPanelOpen, toggleDevPanel]);

    const envVars = getPublicEnvVars();

    return (
        <AnimatePresence>
            {isDevPanelOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={toggleDevPanel}
                        className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
                    />

                    {/* Panel */}
                    <motion.div
                        ref={panelRef}
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                        className="fixed right-0 top-0 bottom-0 w-[460px] bg-[#0d0f14] border-l border-amber-500/20 z-50 flex flex-col shadow-2xl"
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between px-5 py-4 border-b border-amber-500/20 shrink-0">
                            <div className="flex items-center gap-3">
                                <div className="w-7 h-7 rounded-lg bg-amber-500/20 flex items-center justify-center">
                                    <Terminal size={14} className="text-amber-400" />
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-amber-400">Developer Panel</h2>
                                    <p className="text-xs text-gray-500">Hanya tersedia di mode DEV</p>
                                </div>
                            </div>
                            <button
                                onClick={toggleDevPanel}
                                className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-colors"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        {/* Body — Scrollable */}
                        <div className="flex-1 overflow-y-auto p-5 space-y-6">

                            {/* === SECTION: API Logs === */}
                            <section>
                                <div className="flex items-center justify-between mb-3">
                                    <h3 className="text-xs font-semibold text-amber-400/70 uppercase tracking-widest">
                                        API Logs
                                    </h3>
                                    {apiLogs.length > 0 && (
                                        <button
                                            onClick={clearApiLogs}
                                            className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-400 transition-colors"
                                        >
                                            <Trash2 size={11} /> Clear
                                        </button>
                                    )}
                                </div>

                                {apiLogs.length === 0 ? (
                                    <div className="text-xs text-gray-600 italic px-3 py-4 border border-dashed border-gray-800 rounded-lg text-center">
                                        Belum ada API request. Coba kirim pesan ke JAYA.
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        {apiLogs.map((log, i) => (
                                            <div
                                                key={i}
                                                className="bg-[#13161d] border border-gray-800 rounded-lg px-3 py-2.5 text-xs font-mono"
                                            >
                                                <div className="flex items-center gap-2 mb-1">
                                                    {log.ok ? (
                                                        <CheckCircle size={11} className="text-green-400 shrink-0" />
                                                    ) : (
                                                        <XCircle size={11} className="text-red-400 shrink-0" />
                                                    )}
                                                    <span className={`font-bold text-[10px] ${log.method === 'POST' ? 'text-blue-400' : 'text-gray-400'}`}>
                                                        {log.method}
                                                    </span>
                                                    <span className="text-gray-300 truncate flex-1">{log.url}</span>
                                                    <span className={`shrink-0 ${log.ok ? 'text-green-400' : 'text-red-400'}`}>
                                                        {log.status}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1 text-gray-600 text-[10px]">
                                                    <Clock size={9} />
                                                    <span>{log.duration}ms</span>
                                                    <span className="ml-auto">{new Date(log.timestamp).toLocaleTimeString()}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </section>

                            {/* === SECTION: Environment Variables === */}
                            <section>
                                <h3 className="text-xs font-semibold text-amber-400/70 uppercase tracking-widest mb-3">
                                    <span className="flex items-center gap-2">
                                        <Settings2 size={12} /> Environment Variables
                                    </span>
                                </h3>
                                <div className="bg-[#13161d] border border-gray-800 rounded-lg overflow-hidden">
                                    {Object.entries(envVars).map(([key, value], i) => (
                                        <div
                                            key={key}
                                            className={`flex gap-2 px-3 py-2 text-xs font-mono ${i % 2 === 0 ? 'bg-white/[0.02]' : ''}`}
                                        >
                                            <span className="text-amber-400/70 shrink-0 w-52 truncate">{key}</span>
                                            <span className="text-gray-400 truncate">=</span>
                                            <span className={`text-gray-300 truncate flex-1 ${value === 'true' ? 'text-green-400' : value === 'false' ? 'text-red-400' : ''}`}>
                                                {value || <span className="text-gray-600 italic">empty</span>}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </section>

                            {/* === SECTION: Quick Actions === */}
                            <section>
                                <h3 className="text-xs font-semibold text-amber-400/70 uppercase tracking-widest mb-3">
                                    Quick Actions
                                </h3>
                                <div className="space-y-2">
                                    <button
                                        onClick={() => { localStorage.clear(); window.location.reload(); }}
                                        className="w-full text-left px-3 py-2.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-xs text-red-400 hover:text-red-300 transition-colors flex items-center gap-2"
                                    >
                                        <Trash2 size={12} /> Clear All Local Storage & Reload
                                    </button>
                                    <button
                                        onClick={() => window.location.reload()}
                                        className="w-full text-left px-3 py-2.5 rounded-lg bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20 text-xs text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-2"
                                    >
                                        <Terminal size={12} /> Hard Reload Page
                                    </button>
                                </div>
                            </section>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}
