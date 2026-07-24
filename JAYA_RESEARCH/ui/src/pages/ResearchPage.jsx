import { useState, useEffect, useRef, useCallback } from 'react';
import {
    Play, RotateCw, CheckCircle2, FileText, FlaskConical,
    AlertCircle, Sparkles, Zap, Database, Square, Activity,
    Brain, ChevronRight, Clock, BarChart2, Shield, Cpu, RefreshCw
} from 'lucide-react';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import api from '../services/api';

const API_BASE = 'http://localhost:8000';

// Format unix timestamp to relative time
function formatRelTime(ts) {
    if (!ts) return '—';
    const diff = Math.floor(Date.now() / 1000 - ts);
    if (diff < 5)  return 'baru saja';
    if (diff < 60) return `${diff}d lalu`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m lalu`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}j lalu`;
    return new Date(ts * 1000).toLocaleDateString('id-ID');
}

function ConfidencePill({ value }) {
    const pct = Math.round((value || 0) * 100);
    const color = pct >= 70 ? 'text-emerald-400 bg-emerald-500/15 border-emerald-500/30'
        : pct >= 50 ? 'text-amber-400 bg-amber-500/15 border-amber-500/30'
        : 'text-red-400 bg-red-500/15 border-red-500/30';
    return (
        <span className={clsx('text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border', color)}>
            {pct}%
        </span>
    );
}

function PatchDetail({ patch, onClose }) {
    if (!patch) return null;
    const confidence = Math.round((patch.bayes_confidence || 0) * 100);
    const novelty = Math.round((patch.novelty_score || 0) * 100);

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="h-full overflow-y-auto space-y-4 pr-1"
        >
            {/* Header */}
            <div className="p-5 rounded-2xl bg-white/[0.03] border border-white/[0.08]">
                <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-xl bg-emerald-500/15 text-emerald-400 flex items-center justify-center">
                            <Brain size={16} />
                        </div>
                        <div>
                            <p className="text-[10px] font-mono text-slate-500">PATCH ID</p>
                            <p className="text-xs font-bold text-emerald-300 font-mono">{patch.patch_id}</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="text-slate-500 hover:text-white text-[11px] transition-colors">✕ Tutup</button>
                </div>
                <h3 className="text-sm font-bold text-slate-100 mb-1">{patch.topic}</h3>
                <p className="text-[11px] text-slate-400 leading-relaxed">{patch.statement}</p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                    <p className="text-[10px] text-slate-500 mb-1 flex items-center gap-1"><BarChart2 size={10} /> Bayesian Confidence</p>
                    <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                            <div
                                className={clsx('h-full rounded-full transition-all', confidence >= 70 ? 'bg-emerald-500' : confidence >= 50 ? 'bg-amber-500' : 'bg-red-500')}
                                style={{ width: `${confidence}%` }}
                            />
                        </div>
                        <span className="text-xs font-bold text-slate-200">{confidence}%</span>
                    </div>
                </div>
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                    <p className="text-[10px] text-slate-500 mb-1 flex items-center gap-1"><Sparkles size={10} /> Novelty Score</p>
                    <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                            <div className="h-full bg-sky-500 rounded-full" style={{ width: `${novelty}%` }} />
                        </div>
                        <span className="text-xs font-bold text-slate-200">{novelty}%</span>
                    </div>
                </div>
            </div>

            {/* Meta */}
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-2">
                <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-500 flex items-center gap-1"><Cpu size={10} /> Target System</span>
                    <span className="text-slate-200 font-mono">{patch.target_system || 'JAYA_CORE_BRAIN'}</span>
                </div>
                <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-500 flex items-center gap-1"><Database size={10} /> SQLite Status</span>
                    <span className="text-emerald-400 font-bold">✓ APPLIED</span>
                </div>
                <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-500 flex items-center gap-1"><Zap size={10} /> LLM Generated</span>
                    <span className={patch.llm_generated ? 'text-sky-400' : 'text-slate-400'}>
                        {patch.llm_generated ? '✓ Ya (NVIDIA NIM)' : 'Template Synthesis'}
                    </span>
                </div>
                <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-500 flex items-center gap-1"><Clock size={10} /> Diterapkan</span>
                    <span className="text-slate-300">{formatRelTime(patch.applied_at)}</span>
                </div>
            </div>

            {/* Falsifiability */}
            {patch.falsifiability && (
                <div className="p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
                    <p className="text-[10px] font-bold text-amber-400 mb-1 flex items-center gap-1">
                        <Shield size={10} /> Kriteria Falsifiabilitas
                    </p>
                    <p className="text-[11px] text-slate-300 leading-relaxed">{patch.falsifiability}</p>
                </div>
            )}

            {/* Full Markdown report */}
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] prose prose-invert max-w-none text-xs leading-relaxed">
                <ReactMarkdown>
                    {`# Laporan Penemuan Ilmiah\n\n**Patch ID**: \`${patch.patch_id}\`\n\n**Topik**: ${patch.topic}\n\n## Hipotesis\n\n${patch.statement}\n\n## Analisis\n\n- **Kepercayaan Bayesian**: ${confidence}% — ${confidence >= 70 ? 'Hipotesis diterima dengan keyakinan tinggi' : confidence >= 50 ? 'Hipotesis perlu validasi lanjutan' : 'Keyakinan rendah, butuh eksperimen ulang'}\n- **Skor Novelty**: ${novelty}% — ${novelty >= 80 ? 'Penemuan sangat baru, belum ada di literatur sebelumnya' : 'Penemuan baru dengan basis riset yang ada'}\n\n## Dampak ke JAYA_CORE\n\nPatch ini diinjeksi langsung ke database \`agentic_jarvis.db\` tabel \`jarvis_patches\` dan \`proactive_directives\`, memungkinkan JAYA merespons secara proaktif berdasarkan penemuan ini.`}
                </ReactMarkdown>
            </div>
        </motion.div>
    );
}

export default function ResearchPage({ workspaceId }) {
    const [patches, setPatches] = useState([]);
    const [totalPatches, setTotalPatches] = useState(0);
    const [selectedPatch, setSelectedPatch] = useState(null);
    // null = belum tahu (sedang sync dengan backend), true/false = sudah tahu
    const [isLoopRunning, setIsLoopRunning] = useState(null);
    const [isTogglingLoop, setIsTogglingLoop] = useState(false);
    const [loopIteration, setLoopIteration] = useState(0);
    const [latestResult, setLatestResult] = useState(null);
    const [dbExists, setDbExists] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [topic, setTopic] = useState('');
    const [isRunningManual, setIsRunningManual] = useState(false);
    // true saat pertama kali sync backend (UI baru dibuka/reload)
    const [isInitialSync, setIsInitialSync] = useState(true);

    const loopPollRef = useRef(null);
    const patchesPollRef = useRef(null);

    // Fetch patches from SQLite via API
    const fetchPatches = useCallback(async (showRefresh = false) => {
        if (showRefresh) setIsRefreshing(true);
        try {
            const res = await fetch(`${API_BASE}/evolution/patches?limit=100`);
            const data = await res.json();
            if (data.patches) {
                setPatches(data.patches);
                setTotalPatches(data.total || data.patches.length);
                setDbExists(data.db_exists || false);
            }
        } catch (e) {
            console.error('[ResearchPage] Failed to fetch patches:', e);
        } finally {
            if (showRefresh) setIsRefreshing(false);
        }
    }, []);

    // Fetch loop status — on first call, mark sync done
    const fetchLoopStatus = useCallback(async (isFirst = false) => {
        try {
            const res = await fetch(`${API_BASE}/evolution/loop-status`);
            const data = await res.json();
            setIsLoopRunning(data.is_running || false);
            setLoopIteration(data.loop_iteration_count || 0);
            if (data.latest_upgrade) setLatestResult(data.latest_upgrade);
        } catch (e) {
            console.error('[ResearchPage] Loop status error:', e);
            // Jika backend tidak bisa dijangkau, anggap tidak running
            if (isFirst) setIsLoopRunning(false);
        } finally {
            if (isFirst) setIsInitialSync(false);
        }
    }, []);

    // Initial sync dengan backend — inilah yang membuat UI tahu status real
    useEffect(() => {
        fetchPatches();
        fetchLoopStatus(true);  // isFirst=true, akan set isInitialSync=false saat selesai
    }, []);

    // Polling: patches every 5s, loop status every 3s
    useEffect(() => {
        patchesPollRef.current = setInterval(() => fetchPatches(), 5000);
        loopPollRef.current = setInterval(() => fetchLoopStatus(false), 3000);
        return () => {
            clearInterval(patchesPollRef.current);
            clearInterval(loopPollRef.current);
        };
    }, []);

    // Toggle loop
    const toggleLoop = async () => {
        setIsTogglingLoop(true);
        try {
            const endpoint = isLoopRunning
                ? `${API_BASE}/evolution/stop-autonomous-loop`
                : `${API_BASE}/evolution/start-autonomous-loop`;
            const res = await fetch(endpoint, { method: 'POST' });
            const data = await res.json();
            setIsLoopRunning(data.is_running || false);
        } catch (e) {
            console.error('[ResearchPage] Toggle loop error:', e);
        } finally {
            setIsTogglingLoop(false);
        }
    };

    // Manual single research trigger
    const runManualUpgrade = async () => {
        setIsRunningManual(true);
        try {
            const url = topic.trim()
                ? `${API_BASE}/evolution/auto-upgrade?custom_topic=${encodeURIComponent(topic.trim())}`
                : `${API_BASE}/evolution/auto-upgrade`;
            const res = await fetch(url, { method: 'POST' });
            const data = await res.json();
            if (data.result) {
                setLatestResult(data.result);
                setTopic('');
                // Immediately refresh patches
                setTimeout(() => fetchPatches(), 1000);
            }
        } catch (e) {
            console.error('[ResearchPage] Manual upgrade error:', e);
        } finally {
            setIsRunningManual(false);
        }
    };

    return (
        <div className="p-6 h-full overflow-y-auto bg-[#0b0c10] text-slate-100 font-sans flex flex-col gap-6">
            {/* ─── Header ─── */}
            <header className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 pb-5 border-b border-white/[0.06]">
                <div>
                    <h1 className="text-xl font-bold mb-1 flex items-center gap-3">
                        <span className="p-2 bg-white/[0.05] border border-white/[0.08] rounded-xl text-slate-200">
                            <FlaskConical size={20} />
                        </span>
                        Autonomous Discovery Engine
                    </h1>
                    <p className="text-slate-400 text-[11px] ml-1">
                        Riset otonom JAYA — setiap penemuan diinjeksi langsung ke <code className="text-slate-300">agentic_jarvis.db</code>
                    </p>
                </div>

                <div className="flex items-center gap-3 flex-wrap">
                    {/* DB Status Badge */}
                    <div className={clsx(
                        'px-3 py-1.5 rounded-lg text-[10px] font-bold border flex items-center gap-1.5',
                        dbExists
                            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                            : 'bg-red-500/10 border-red-500/30 text-red-400'
                    )}>
                        <Database size={10} />
                        <span>{dbExists ? `DB Aktif · ${totalPatches} patch` : 'DB belum dibuat'}</span>
                    </div>

                    {/* Refresh */}
                    <button
                        onClick={() => fetchPatches(true)}
                        disabled={isRefreshing}
                        className="p-2 rounded-lg bg-white/[0.04] border border-white/[0.08] hover:bg-white/[0.08] text-slate-400 hover:text-white transition-all"
                        title="Refresh daftar penemuan"
                    >
                        <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
                    </button>

                    {/* START / STOP — disabled & shows spinner saat initial sync */}
                    <button
                        onClick={toggleLoop}
                        disabled={isTogglingLoop || isInitialSync || isLoopRunning === null}
                        className={clsx(
                            'px-4 py-2 text-xs font-bold rounded-xl transition-all flex items-center gap-2 border disabled:opacity-50 disabled:cursor-not-allowed',
                            isInitialSync || isLoopRunning === null
                                ? 'bg-white/[0.05] border-white/[0.1] text-slate-400'
                                : isLoopRunning
                                    ? 'bg-amber-500/15 hover:bg-amber-500/25 border-amber-500/40 text-amber-300'
                                    : 'bg-emerald-600/20 hover:bg-emerald-600/35 border-emerald-500/40 text-emerald-300'
                        )}
                        title={
                            isInitialSync ? 'Menyinkronkan status dengan backend...'
                            : isLoopRunning ? 'Klik untuk menghentikan loop'
                            : 'Klik untuk memulai loop otonom'
                        }
                    >
                        {/* Loading saat sync awal */}
                        {(isInitialSync || isLoopRunning === null) ? (
                            <><RotateCw size={13} className="animate-spin" /><span>Menyinkronkan...</span></>
                        ) : isTogglingLoop ? (
                            <><RotateCw size={13} className="animate-spin" /><span>Memproses...</span></>
                        ) : isLoopRunning ? (
                            <><Square size={12} className="fill-amber-400 text-amber-400" /><span>Hentikan Loop</span></>
                        ) : (
                            <><Play size={12} className="fill-emerald-400 text-emerald-400" /><span>Mulai Loop Otonom</span></>
                        )}
                        {isLoopRunning && !isInitialSync && (
                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                        )}
                    </button>

                    {/* Manual topic */}
                    <div className="flex gap-1.5 bg-white/[0.03] p-1 rounded-xl border border-white/[0.07]">
                        <input
                            value={topic}
                            onChange={e => setTopic(e.target.value)}
                            placeholder="Topik spesifik (opsional)..."
                            className="bg-transparent text-slate-100 px-3 py-1 text-[11px] w-44 focus:outline-none placeholder:text-slate-600"
                            onKeyDown={e => e.key === 'Enter' && runManualUpgrade()}
                        />
                        <button
                            onClick={runManualUpgrade}
                            disabled={isRunningManual}
                            className="bg-slate-200 hover:bg-white text-slate-900 px-3 py-1 rounded-lg flex items-center gap-1 text-[11px] font-bold transition-all disabled:opacity-50"
                        >
                            {isRunningManual
                                ? <RotateCw size={12} className="animate-spin" />
                                : <Zap size={12} />
                            }
                            <span>Run</span>
                        </button>
                    </div>
                </div>
            </header>

            {/* ─── Initial Sync Banner ─── */}
            <AnimatePresence>
                {isInitialSync && (
                    <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        className="px-4 py-3 rounded-xl bg-slate-500/8 border border-slate-500/20 flex items-center gap-3"
                    >
                        <RotateCw size={14} className="text-slate-400 animate-spin shrink-0" />
                        <p className="text-[11px] text-slate-400">
                            Menyinkronkan status dengan backend… tombol akan aktif setelah koneksi terkonfirmasi.
                        </p>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ─── Loop Active Banner ─── */}
            <AnimatePresence>
                {isLoopRunning && !isInitialSync && (
                    <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        className="px-4 py-3 rounded-xl bg-emerald-500/8 border border-emerald-500/25 flex items-center justify-between gap-4"
                    >
                        <div className="flex items-center gap-3">
                            <Activity size={16} className="text-emerald-400 animate-pulse shrink-0" />
                            <div>
                                <p className="text-xs font-bold text-emerald-300">Loop Riset Otonom Aktif</p>
                                <p className="text-[10px] text-slate-400">
                                    Iterasi #{loopIteration} · State disimpan ke SQLite — aman meski UI di-reload atau backend restart
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={toggleLoop}
                            className="px-3 py-1 bg-amber-500/15 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 text-[10px] font-bold rounded-lg transition-all shrink-0"
                        >
                            Stop
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>


            {/* ─── Latest Discovery Toast ─── */}
            <AnimatePresence>
                {latestResult && (
                    <motion.div
                        key={latestResult.patch_id}
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        className="px-4 py-3 rounded-xl bg-sky-500/8 border border-sky-500/20 flex items-start justify-between gap-4"
                    >
                        <div className="flex items-start gap-3">
                            <CheckCircle2 size={16} className="text-sky-400 shrink-0 mt-0.5" />
                            <div className="min-w-0">
                                <p className="text-[10px] font-bold text-sky-300 flex items-center gap-2 flex-wrap">
                                    <span>Penemuan Baru Berhasil Diinjeksi ke JAYA_CORE!</span>
                                    <code className="bg-sky-500/15 px-1.5 py-0.5 rounded font-mono text-sky-200">{latestResult.patch_id}</code>
                                </p>
                                <p className="text-[10px] text-slate-400 mt-0.5 line-clamp-2">{latestResult.statement}</p>
                            </div>
                        </div>
                        <button onClick={() => setLatestResult(null)} className="text-slate-500 hover:text-white text-[10px] shrink-0">✕</button>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ─── Main Content: List + Detail ─── */}
            <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0">
                {/* ─ Patch List ─ */}
                <div className="lg:col-span-4 flex flex-col gap-3 min-h-0">
                    <div className="flex items-center justify-between">
                        <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                            <Brain size={11} /> Daftar Penemuan &amp; Patch
                        </h3>
                        <span className="text-[10px] font-bold text-slate-400 bg-white/[0.05] px-2 py-0.5 rounded-full">
                            {totalPatches}
                        </span>
                    </div>

                    <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                        <AnimatePresence initial={false}>
                            {patches.length === 0 ? (
                                <div className="h-48 rounded-xl border border-dashed border-white/10 flex flex-col items-center justify-center text-slate-600 gap-2">
                                    <Database size={24} />
                                    <p className="text-xs text-center">
                                        {dbExists
                                            ? 'Belum ada patch. Mulai Loop Otonom!'
                                            : 'Database belum ada. Mulai Loop Otonom untuk membuatnya.'}
                                    </p>
                                </div>
                            ) : patches.map((patch, idx) => (
                                <motion.div
                                    key={patch.patch_id}
                                    initial={{ opacity: 0, y: -8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: idx * 0.02 }}
                                    onClick={() => setSelectedPatch(patch)}
                                    className={clsx(
                                        'p-3.5 rounded-xl border cursor-pointer transition-all group relative overflow-hidden',
                                        selectedPatch?.patch_id === patch.patch_id
                                            ? 'bg-white/[0.06] border-white/20 shadow-md'
                                            : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.12]'
                                    )}
                                >
                                    <div className="flex items-start justify-between gap-2 mb-1.5">
                                        <h4 className="text-[11px] font-bold text-slate-200 line-clamp-1 flex-1">{patch.topic}</h4>
                                        <ConfidencePill value={patch.bayes_confidence} />
                                    </div>
                                    <p className="text-[10px] text-slate-500 line-clamp-2 mb-2 leading-relaxed">{patch.statement}</p>
                                    <div className="flex items-center justify-between text-[10px] text-slate-600">
                                        <span className="font-mono">{patch.patch_id?.slice(-14)}</span>
                                        <div className="flex items-center gap-2">
                                            <span className="text-emerald-600 flex items-center gap-0.5"><CheckCircle2 size={9} /> Applied</span>
                                            <span>{formatRelTime(patch.applied_at)}</span>
                                        </div>
                                    </div>
                                    {selectedPatch?.patch_id === patch.patch_id && (
                                        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
                                            <ChevronRight size={14} />
                                        </div>
                                    )}
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    </div>
                </div>

                {/* ─ Detail Viewer ─ */}
                <div className="lg:col-span-8 min-h-0">
                    <AnimatePresence mode="wait">
                        {selectedPatch ? (
                            <PatchDetail
                                key={selectedPatch.patch_id}
                                patch={selectedPatch}
                                onClose={() => setSelectedPatch(null)}
                            />
                        ) : (
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                className="h-full min-h-64 rounded-2xl border border-dashed border-white/10 flex flex-col items-center justify-center text-slate-600 gap-3"
                            >
                                <FileText size={32} className="opacity-30" />
                                <p className="text-xs">Pilih penemuan untuk melihat laporan lengkap</p>
                                {!isLoopRunning && patches.length === 0 && (
                                    <button
                                        onClick={toggleLoop}
                                        className="mt-2 px-4 py-2 bg-emerald-600/20 hover:bg-emerald-600/35 border border-emerald-500/40 text-emerald-300 text-xs font-bold rounded-xl transition-all flex items-center gap-2"
                                    >
                                        <Play size={12} className="fill-emerald-400" />
                                        Mulai Loop Otonom Sekarang
                                    </button>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </div>
    );
}
