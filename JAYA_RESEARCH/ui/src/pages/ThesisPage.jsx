import { useState, useRef, useEffect, useCallback } from 'react';
import {
    GraduationCap, Upload, FileText, CheckCircle2, AlertCircle,
    RotateCw, Sparkles, Shield, MessageSquare, BookOpen, Target,
    ChevronRight, Send, X, Microscope, TrendingUp, Brain, Swords,
    PenTool, Search, Download, ExternalLink, RefreshCw, Copy, Check,
    ChevronDown, Layers
} from 'lucide-react';
import clsx from 'clsx';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../services/api';

// ─── Constants ────────────────────────────────────────────────────────────────

const ANALYSIS_STEPS = [
    { id: 'meta',    icon: FileText,   label: 'Ekstraksi Metadata',       color: 'blue'   },
    { id: 'novelty', icon: Microscope, label: 'Cek Novelty vs Literatur', color: 'purple' },
    { id: 'gap',     icon: TrendingUp, label: 'Identifikasi Research Gap', color: 'green' },
    { id: 'critique',icon: Swords,     label: 'Kritik Akademis',          color: 'orange' },
    { id: 'defense', icon: Shield,     label: 'Pertanyaan Sidang',        color: 'red'    },
];

const TABS = [
    { id: 'analysis', icon: Layers,       label: 'Analisis'  },
    { id: 'revise',   icon: PenTool,      label: 'Revisi'    },
    { id: 'journals', icon: BookOpen,     label: 'Jurnal'    },
    { id: 'chat',     icon: MessageSquare,label: 'Chat'      },
    { id: 'export',   icon: Download,     label: 'Ekspor'    },
];

const REVISION_TYPES = [
    { value: 'general',     label: 'Umum',         desc: 'Perbaiki kejelasan & alur' },
    { value: 'formal',      label: 'Formalitas',   desc: 'Bahasa lebih akademis'     },
    { value: 'citation',    label: 'Sitasi',       desc: 'Tandai klaim yg butuh referensi' },
    { value: 'methodology', label: 'Metodologi',   desc: 'Perkuat bagian metode'     },
];

// ─── Shared Helpers ───────────────────────────────────────────────────────────

const colorMap = {
    blue:   { bg: 'bg-blue-500/10',   text: 'text-blue-400',   border: 'border-blue-500/30'   },
    purple: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
    green:  { bg: 'bg-green-500/10',  text: 'text-green-400',  border: 'border-green-500/30'  },
    orange: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30' },
    red:    { bg: 'bg-red-500/10',    text: 'text-red-400',    border: 'border-red-500/30'    },
    yellow: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
};

function useCopy() {
    const [copied, setCopied] = useState(false);
    const copy = (text) => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };
    return { copied, copy };
}

// ─── DropZone ─────────────────────────────────────────────────────────────────

function DropZone({ onFile, disabled }) {
    const [dragging, setDragging] = useState(false);
    const inputRef = useRef(null);

    const handleDrop = useCallback((e) => {
        e.preventDefault(); setDragging(false);
        if (disabled) return;
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
    }, [onFile, disabled]);

    return (
        <div
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onClick={() => !disabled && inputRef.current?.click()}
            className={clsx(
                'relative border-2 border-dashed rounded-2xl p-10 flex flex-col items-center gap-4 cursor-pointer transition-all duration-300 group',
                dragging ? 'border-yellow-400 bg-yellow-400/10 scale-[1.01]' :
                disabled ? 'border-notebook-border/30 opacity-50 cursor-not-allowed' :
                'border-notebook-border hover:border-yellow-500/60 hover:bg-yellow-500/5'
            )}
        >
            <input ref={inputRef} type="file" accept=".pdf" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }} disabled={disabled} />
            <div className={clsx('w-16 h-16 rounded-2xl flex items-center justify-center transition-all', dragging ? 'bg-yellow-400/20 scale-110' : 'bg-notebook-bg group-hover:bg-yellow-500/10')}>
                <Upload size={28} className={clsx('transition-colors', dragging ? 'text-yellow-400' : 'text-notebook-text-secondary group-hover:text-yellow-400')} />
            </div>
            <div className="text-center">
                <p className="font-semibold text-notebook-text-primary mb-1">{dragging ? 'Lepas file di sini' : 'Drag & Drop PDF Tugas Akhir'}</p>
                <p className="text-sm text-notebook-text-secondary">atau <span className="text-yellow-400 underline underline-offset-2">klik untuk memilih</span></p>
                <p className="text-xs text-notebook-text-secondary/40 mt-2">Hanya .pdf • Max 50MB</p>
            </div>
        </div>
    );
}

// ─── StepIndicator ────────────────────────────────────────────────────────────

function StepIndicator({ backendSteps, progress }) {
    const getStatus = (id) => backendSteps?.find(s => s.step === id)?.status ?? 'pending';
    return (
        <div className="space-y-2 mt-4">
            {ANALYSIS_STEPS.map((step, i) => {
                const status = getStatus(step.id);
                const Icon = step.icon;
                const c = colorMap[step.color];
                return (
                    <motion.div key={step.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}
                        className={clsx('flex items-center gap-3 px-3 py-2.5 rounded-xl border transition-all',
                            status === 'done'    ? `${c.bg} ${c.border}` :
                            status === 'running' ? 'bg-notebook-card border-notebook-border' :
                            'border-transparent opacity-40'
                        )}>
                        <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0', c.bg)}>
                            {status === 'running' ? <RotateCw size={13} className={clsx('animate-spin', c.text)} /> :
                             status === 'done'    ? <CheckCircle2 size={13} className={c.text} /> :
                             <Icon size={13} className="text-notebook-text-secondary" />}
                        </div>
                        <span className={clsx('text-xs font-medium flex-1', status === 'done' ? c.text : status === 'running' ? 'text-notebook-text-primary' : 'text-notebook-text-secondary')}>
                            {step.label}
                        </span>
                        {status === 'running' && <span className="text-xs text-notebook-text-secondary/70 animate-pulse">berjalan...</span>}
                        {status === 'done' && <CheckCircle2 size={12} className={c.text} />}
                    </motion.div>
                );
            })}
            <div className="mt-3">
                <div className="flex justify-between text-xs text-notebook-text-secondary mb-1.5">
                    <span>Progres</span><span>{progress}%</span>
                </div>
                <div className="h-1.5 bg-black/30 rounded-full overflow-hidden">
                    <motion.div className="h-full rounded-full bg-gradient-to-r from-yellow-500 to-orange-400" style={{ width: `${progress}%` }} transition={{ duration: 0.5 }} />
                </div>
            </div>
        </div>
    );
}

// ─── Collapsible Section ──────────────────────────────────────────────────────

function Section({ title, icon: Icon, color = 'yellow', children, defaultOpen = false, badge }) {
    const [open, setOpen] = useState(defaultOpen);
    const c = colorMap[color];
    return (
        <div className="bg-notebook-card border border-notebook-border rounded-2xl overflow-hidden">
            <button onClick={() => setOpen(v => !v)} className="w-full flex items-center gap-3 p-4 hover:bg-notebook-bg/40 transition-colors text-left">
                <span className={clsx('p-1.5 rounded-lg', c.bg)}><Icon size={16} className={c.text} /></span>
                <span className="font-semibold text-notebook-text-primary flex-1 text-sm">{title}</span>
                {badge && <span className={clsx('text-xs px-2 py-0.5 rounded-full border', c.bg, c.text, c.border)}>{badge}</span>}
                <ChevronDown size={15} className={clsx('text-notebook-text-secondary transition-transform', open && 'rotate-180')} />
            </button>
            <AnimatePresence>
                {open && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
                        <div className="px-5 pb-5 pt-1 border-t border-notebook-border/50">{children}</div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

// ─── Tab: Analisis ────────────────────────────────────────────────────────────

function AnalysisTab({ analysis, sessionId }) {
    if (!analysis) return (
        <div className="flex flex-col items-center justify-center py-20 text-notebook-text-secondary">
            <Layers size={40} className="opacity-20 mb-3" />
            <p className="text-sm">Hasil analisis akan muncul di sini setelah proses selesai.</p>
        </div>
    );

    const { meta, novelty, gap_report, critique, defense_questions } = analysis;
    const isNovel = novelty?.is_novel;
    const pct = Math.round((novelty?.confidence ?? 0) * 100);

    return (
        <div className="space-y-4">
            {/* Meta */}
            {meta && (
                <div className="bg-notebook-card border border-notebook-border rounded-2xl p-5">
                    <div className="flex items-center gap-2 mb-4">
                        <FileText size={16} className="text-blue-400" />
                        <h3 className="font-semibold text-sm text-notebook-text-primary">Informasi Dokumen</h3>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                        {[['Judul', meta.judul], ['Penulis', meta.penulis], ['Topik', meta.topik_utama], ['Metode', meta.metode]].filter(([, v]) => v).map(([k, v]) => (
                            <div key={k} className="bg-notebook-bg rounded-xl p-3">
                                <p className="text-notebook-text-secondary mb-1">{k}</p>
                                <p className="text-notebook-text-primary font-medium line-clamp-2">{v}</p>
                            </div>
                        ))}
                    </div>
                    {meta.keywords?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-3">
                            {meta.keywords.map(k => <span key={k} className="px-2 py-0.5 bg-blue-500/10 border border-blue-500/20 rounded-full text-xs text-blue-400">{k}</span>)}
                        </div>
                    )}
                    {meta.abstrak && <p className="mt-3 text-xs text-notebook-text-secondary leading-relaxed border-t border-notebook-border pt-3">{meta.abstrak.slice(0, 400)}{meta.abstrak.length > 400 ? '...' : ''}</p>}
                </div>
            )}

            {/* Novelty Badge */}
            {novelty && (
                <div className={clsx('flex items-center gap-4 p-4 rounded-2xl border', isNovel ? 'bg-green-500/10 border-green-500/30' : isNovel === false ? 'bg-red-500/10 border-red-500/30' : 'bg-notebook-card border-notebook-border')}>
                    <div className={clsx('w-14 h-14 rounded-full flex items-center justify-center text-2xl font-bold flex-shrink-0', isNovel ? 'bg-green-500/20 text-green-400' : isNovel === false ? 'bg-red-500/20 text-red-400' : 'bg-notebook-bg text-notebook-text-secondary')}>
                        {isNovel ? '✓' : isNovel === false ? '✗' : '?'}
                    </div>
                    <div>
                        <p className={clsx('font-bold text-base', isNovel ? 'text-green-400' : isNovel === false ? 'text-red-400' : 'text-notebook-text-secondary')}>
                            {isNovel ? 'Penelitian Dianggap NOVEL' : isNovel === false ? 'Penelitian Kurang Novel' : 'Novelty Tidak Terdeteksi'}
                        </p>
                        <p className="text-notebook-text-secondary text-xs">Confidence: {pct}%</p>
                    </div>
                </div>
            )}

            {novelty?.reasoning && (
                <Section title="Detail Analisis Novelty" icon={Microscope} color="purple" defaultOpen>
                    <p className="text-sm text-notebook-text-secondary leading-relaxed">{novelty.reasoning}</p>
                </Section>
            )}
            {gap_report && (
                <Section title="Research Gap & Peluang Penelitian" icon={TrendingUp} color="green">
                    <div className="prose prose-invert prose-sm max-w-none text-notebook-text-secondary"><ReactMarkdown>{gap_report}</ReactMarkdown></div>
                </Section>
            )}
            {critique && (
                <Section title="Kritik Akademis (Peer Review)" icon={Swords} color="orange">
                    <div className="prose prose-invert prose-sm max-w-none text-notebook-text-secondary"><ReactMarkdown>{critique}</ReactMarkdown></div>
                </Section>
            )}
            {defense_questions && (
                <Section title="Pertanyaan Sidang yang Mungkin Muncul" icon={Shield} color="red" defaultOpen>
                    <div className="prose prose-invert prose-sm max-w-none text-notebook-text-secondary"><ReactMarkdown>{defense_questions}</ReactMarkdown></div>
                </Section>
            )}
        </div>
    );
}

// ─── Tab: Revisi ──────────────────────────────────────────────────────────────

function ReviseTab({ sessionId, analysis }) {
    const [sectionText, setSectionText] = useState('');
    const [instruction, setInstruction] = useState('');
    const [revisionType, setRevisionType] = useState('general');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const { copied, copy } = useCopy();

    const handleRevise = async () => {
        if (!sectionText.trim() || !instruction.trim()) return;
        setLoading(true); setError(null); setResult(null);
        try {
            const res = await api.reviseThesisSection(sessionId, sectionText, instruction, revisionType);
            setResult(res.revised_text);
        } catch (e) {
            setError(e.message);
        }
        setLoading(false);
    };

    const critique = analysis?.critique || '';

    return (
        <div className="space-y-5">
            {/* Hint dari critique */}
            {critique && (
                <div className="flex items-start gap-3 p-4 bg-orange-500/10 border border-orange-500/20 rounded-2xl text-sm">
                    <Swords size={16} className="text-orange-400 flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-orange-300 font-semibold mb-1">Saran dari Analisis Sebelumnya</p>
                        <p className="text-notebook-text-secondary text-xs leading-relaxed line-clamp-3">{critique.slice(0, 300)}...</p>
                    </div>
                </div>
            )}

            {/* Input */}
            <div className="space-y-3">
                <div>
                    <label className="text-xs font-semibold text-notebook-text-secondary uppercase tracking-wider mb-2 block">
                        Tipe Revisi
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                        {REVISION_TYPES.map(t => (
                            <button key={t.value} onClick={() => setRevisionType(t.value)}
                                className={clsx('p-3 rounded-xl border text-left transition-all text-xs',
                                    revisionType === t.value
                                        ? 'border-yellow-500/50 bg-yellow-500/10 text-yellow-400'
                                        : 'border-notebook-border bg-notebook-card text-notebook-text-secondary hover:border-notebook-text-secondary/40'
                                )}>
                                <p className="font-semibold">{t.label}</p>
                                <p className="opacity-70 mt-0.5">{t.desc}</p>
                            </button>
                        ))}
                    </div>
                </div>

                <div>
                    <label className="text-xs font-semibold text-notebook-text-secondary uppercase tracking-wider mb-2 block">
                        Tempel Bagian Teks TA yang Ingin Direvisi
                    </label>
                    <textarea
                        value={sectionText}
                        onChange={e => setSectionText(e.target.value)}
                        placeholder="Copy-paste bagian dari Tugas Akhir kamu di sini (bab, paragraf, dll.)..."
                        rows={6}
                        className="w-full bg-notebook-bg border border-notebook-border rounded-xl px-4 py-3 text-sm text-notebook-text-primary placeholder:text-notebook-text-secondary/40 focus:outline-none focus:border-yellow-500/50 resize-none font-mono"
                    />
                </div>

                <div>
                    <label className="text-xs font-semibold text-notebook-text-secondary uppercase tracking-wider mb-2 block">
                        Instruksi Revisi
                    </label>
                    <textarea
                        value={instruction}
                        onChange={e => setInstruction(e.target.value)}
                        placeholder="Contoh: 'Perbaiki alur paragraf kedua', 'Tambah transisi antar bagian', 'Formalkan kalimat pembuka'..."
                        rows={3}
                        className="w-full bg-notebook-bg border border-notebook-border rounded-xl px-4 py-3 text-sm text-notebook-text-primary placeholder:text-notebook-text-secondary/40 focus:outline-none focus:border-yellow-500/50 resize-none"
                    />
                </div>

                <button onClick={handleRevise} disabled={loading || !sectionText.trim() || !instruction.trim()}
                    className="w-full py-3 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-notebook-bg font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-40 transition-all active:scale-[.98]">
                    {loading ? <><RotateCw size={15} className="animate-spin" /> Merevisi...</> : <><PenTool size={15} /> Revisi dengan JAYA</>}
                </button>

                {error && (
                    <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
                        <AlertCircle size={14} />{error}
                    </div>
                )}
            </div>

            {/* Result */}
            <AnimatePresence>
                {result && (
                    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                        <div className="flex items-center justify-between">
                            <p className="text-xs font-semibold text-green-400 uppercase tracking-wider flex items-center gap-1.5">
                                <CheckCircle2 size={13} /> Hasil Revisi
                            </p>
                            <button onClick={() => copy(result)} className="flex items-center gap-1.5 text-xs text-notebook-text-secondary hover:text-notebook-text-primary transition-colors">
                                {copied ? <><Check size={12} className="text-green-400" /> Disalin</> : <><Copy size={12} /> Salin</>}
                            </button>
                        </div>
                        <div className="bg-notebook-bg border border-green-500/20 rounded-xl p-4 max-h-80 overflow-y-auto">
                            <div className="prose prose-invert prose-sm max-w-none text-notebook-text-primary">
                                <ReactMarkdown>{result}</ReactMarkdown>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

// ─── Tab: Jurnal ──────────────────────────────────────────────────────────────

function JournalsTab({ sessionId, analysis }) {
    const [papers, setPapers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState('');
    const [fetched, setFetched] = useState(false);

    const fetchJournals = async () => {
        setLoading(true); setError(null);
        try {
            const res = await api.findRelevantJournals(sessionId, 15);
            setPapers(res.papers || []);
            setFetched(true);
        } catch (e) {
            setError(e.message);
        }
        setLoading(false);
    };

    const topic = analysis?.meta?.topik_utama || '';
    const filtered = papers.filter(p =>
        !filter || p.title?.toLowerCase().includes(filter.toLowerCase()) ||
        p.abstract?.toLowerCase().includes(filter.toLowerCase())
    );

    const sourceColors = {
        'ArXiv': colorMap.purple,
        'Semantic Scholar': colorMap.blue,
    };

    return (
        <div className="space-y-4">
            {!fetched ? (
                <div className="flex flex-col items-center justify-center py-12 gap-4 text-notebook-text-secondary">
                    <BookOpen size={36} className="opacity-20" />
                    {topic && <p className="text-sm text-center">Cari jurnal relevan untuk topik:<br /><span className="text-yellow-400 font-medium">"{topic}"</span></p>}
                    {!topic && <p className="text-sm text-center opacity-70">Selesaikan analisis terlebih dahulu untuk mendapatkan rekomendasi jurnal yang akurat.</p>}
                    <button onClick={fetchJournals} disabled={loading || !analysis}
                        className="px-6 py-2.5 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-notebook-bg font-bold text-sm flex items-center gap-2 disabled:opacity-40 transition-all">
                        {loading ? <><RotateCw size={14} className="animate-spin" /> Mencari...</> : <><Search size={14} /> Cari Jurnal Relevan</>}
                    </button>
                    {error && <p className="text-red-400 text-xs">{error}</p>}
                </div>
            ) : (
                <>
                    <div className="flex items-center gap-3">
                        <div className="flex-1 bg-notebook-bg border border-notebook-border rounded-xl px-3 py-2 flex items-center gap-2">
                            <Search size={14} className="text-notebook-text-secondary" />
                            <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter judul atau abstrak..." className="flex-1 bg-transparent text-sm text-notebook-text-primary focus:outline-none placeholder:text-notebook-text-secondary/40" />
                        </div>
                        <button onClick={fetchJournals} disabled={loading} className="p-2.5 rounded-xl bg-notebook-card border border-notebook-border text-notebook-text-secondary hover:text-notebook-text-primary transition-colors">
                            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                        </button>
                    </div>
                    <p className="text-xs text-notebook-text-secondary">{filtered.length} jurnal ditemukan • ArXiv + Semantic Scholar</p>

                    <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
                        {filtered.length === 0 && <p className="text-sm text-notebook-text-secondary/60 text-center py-8">Tidak ada hasil untuk filter ini.</p>}
                        {filtered.map((paper, i) => {
                            const sc = sourceColors[paper.source] || colorMap.yellow;
                            return (
                                <motion.div key={paper.id || i} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                                    className="bg-notebook-card border border-notebook-border rounded-xl p-4 hover:border-notebook-text-secondary/30 transition-all group">
                                    <div className="flex items-start justify-between gap-3 mb-2">
                                        <h4 className="text-sm font-semibold text-notebook-text-primary leading-snug flex-1 group-hover:text-yellow-400 transition-colors">
                                            {paper.title || 'Untitled'}
                                        </h4>
                                        {paper.url && (
                                            <a href={paper.url} target="_blank" rel="noopener noreferrer" className="text-notebook-text-secondary hover:text-yellow-400 flex-shrink-0 mt-0.5 transition-colors">
                                                <ExternalLink size={14} />
                                            </a>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className={clsx('text-xs px-2 py-0.5 rounded-full border', sc.bg, sc.text, sc.border)}>{paper.source}</span>
                                        {paper.year && <span className="text-xs text-notebook-text-secondary">{paper.year}</span>}
                                        {paper.relevance_query && <span className="text-xs text-notebook-text-secondary/50">via: {paper.relevance_query}</span>}
                                    </div>
                                    {paper.abstract && <p className="text-xs text-notebook-text-secondary leading-relaxed line-clamp-3">{paper.abstract}</p>}
                                </motion.div>
                            );
                        })}
                    </div>
                </>
            )}
        </div>
    );
}

// ─── Tab: Chat ────────────────────────────────────────────────────────────────

function ChatTab({ sessionId, workspaceId }) {
    const [messages, setMessages] = useState([
        { role: 'assistant', text: 'Halo! Dokumen TA kamu sudah saya baca. Tanyakan apa saja — metodologi, temuan, literatur, atau minta penjelasan bagian tertentu.' }
    ]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const bottomRef = useRef(null);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

    const send = async () => {
        if (!input.trim() || loading) return;
        const q = input.trim(); setInput('');
        setMessages(prev => [...prev, { role: 'user', text: q }]);
        setLoading(true);
        try {
            const res = await api.chatWithThesis(sessionId, q, workspaceId);
            setMessages(prev => [...prev, { role: 'assistant', text: res.answer }]);
        } catch (e) {
            setMessages(prev => [...prev, { role: 'assistant', text: `❌ Error: ${e.message}` }]);
        }
        setLoading(false);
    };

    const SUGGESTIONS = ['Apa temuan utama penelitian ini?', 'Apa kelemahan metodologi yang digunakan?', 'Bagaimana cara memperkuat bab pembahasan?', 'Referensi apa yang paling penting?'];

    return (
        <div className="flex flex-col h-[500px]">
            <div className="flex-1 overflow-y-auto space-y-3 mb-3 pr-1">
                {messages.map((m, i) => (
                    <div key={i} className={clsx('flex gap-2', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                        {m.role === 'assistant' && (
                            <div className="w-7 h-7 rounded-full bg-yellow-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                <Brain size={12} className="text-yellow-400" />
                            </div>
                        )}
                        <div className={clsx('max-w-[82%] px-4 py-2.5 rounded-2xl text-sm',
                            m.role === 'user' ? 'bg-yellow-500/20 text-yellow-100 rounded-br-sm' : 'bg-notebook-bg border border-notebook-border text-notebook-text-primary rounded-bl-sm')}>
                            {m.role === 'assistant'
                                ? <div className="prose prose-invert prose-sm max-w-none"><ReactMarkdown>{m.text}</ReactMarkdown></div>
                                : m.text}
                        </div>
                    </div>
                ))}
                {loading && (
                    <div className="flex gap-2">
                        <div className="w-7 h-7 rounded-full bg-yellow-500/20 flex items-center justify-center flex-shrink-0">
                            <Brain size={12} className="text-yellow-400 animate-pulse" />
                        </div>
                        <div className="bg-notebook-bg border border-notebook-border px-4 py-3 rounded-2xl rounded-bl-sm flex gap-1 items-center">
                            {[0, 150, 300].map(d => <span key={d} className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />)}
                        </div>
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            {/* Suggestions */}
            {messages.length === 1 && (
                <div className="flex flex-wrap gap-2 mb-3">
                    {SUGGESTIONS.map(s => (
                        <button key={s} onClick={() => { setInput(s); }} className="text-xs px-3 py-1.5 bg-notebook-card border border-notebook-border rounded-full text-notebook-text-secondary hover:text-yellow-400 hover:border-yellow-500/40 transition-all">
                            {s}
                        </button>
                    ))}
                </div>
            )}

            <div className="flex gap-2 bg-notebook-bg border border-notebook-border rounded-xl p-1.5">
                <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
                    placeholder="Tanya tentang TA kamu..." disabled={loading}
                    className="flex-1 bg-transparent text-sm text-notebook-text-primary px-3 py-1.5 focus:outline-none placeholder:text-notebook-text-secondary/40" />
                <button onClick={send} disabled={!input.trim() || loading} className="bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 rounded-lg px-3 py-1.5 disabled:opacity-40 transition-colors">
                    <Send size={14} />
                </button>
            </div>
        </div>
    );
}

// ─── Tab: Ekspor ──────────────────────────────────────────────────────────────

function ExportTab({ sessionId, uploadInfo, analysis }) {
    const [loading, setLoading] = useState(false);
    const [done, setDone] = useState(false);
    const [error, setError] = useState(null);

    const handleExport = async () => {
        setLoading(true); setError(null); setDone(false);
        try {
            const safeName = (uploadInfo?.file_name || 'thesis').replace('.pdf', '');
            await api.exportThesisReport(sessionId, `jaya_laporan_${safeName}.md`);
            setDone(true);
        } catch (e) {
            setError(e.message);
        }
        setLoading(false);
    };

    const hasAnalysis = !!analysis;

    const features = [
        { icon: FileText, label: 'Metadata dokumen', ready: !!analysis?.meta?.judul },
        { icon: Microscope, label: 'Analisis novelty + reasoning', ready: !!analysis?.novelty },
        { icon: TrendingUp, label: 'Research gap & peluang', ready: !!analysis?.gap_report },
        { icon: Swords, label: 'Kritik peer review', ready: !!analysis?.critique },
        { icon: Shield, label: 'Pertanyaan sidang', ready: !!analysis?.defense_questions },
        { icon: BookOpen, label: 'Daftar jurnal relevan', ready: true },
        { icon: PenTool, label: 'Riwayat revisi', ready: true },
    ];

    return (
        <div className="space-y-6">
            <div className="bg-gradient-to-br from-yellow-500/10 to-orange-500/10 border border-yellow-500/20 rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-yellow-500/20 rounded-xl"><Download size={20} className="text-yellow-400" /></div>
                    <div>
                        <h3 className="font-bold text-notebook-text-primary">Laporan Analisis Lengkap</h3>
                        <p className="text-xs text-notebook-text-secondary">Format Markdown (.md) — bisa dibuka di Obsidian, VS Code, atau dikonversi ke PDF</p>
                    </div>
                </div>

                <div className="space-y-2 mb-5">
                    {features.map(({ icon: Icon, label, ready }) => (
                        <div key={label} className={clsx('flex items-center gap-3 text-sm', ready ? 'text-notebook-text-secondary' : 'text-notebook-text-secondary/30')}>
                            <CheckCircle2 size={14} className={ready ? 'text-green-400' : 'text-notebook-text-secondary/20'} />
                            <Icon size={13} />
                            {label}
                        </div>
                    ))}
                </div>

                <button onClick={handleExport} disabled={loading || !hasAnalysis}
                    className="w-full py-3 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-notebook-bg font-bold flex items-center justify-center gap-2 disabled:opacity-40 transition-all active:scale-[.98]">
                    {loading ? <><RotateCw size={15} className="animate-spin" />Menggenerate laporan...</> : <><Download size={15} />Download Laporan (.md)</>}
                </button>

                {!hasAnalysis && <p className="text-center text-xs text-notebook-text-secondary/60 mt-2">Selesaikan analisis terlebih dahulu</p>}
                {done && <p className="text-center text-xs text-green-400 mt-2 flex items-center justify-center gap-1"><CheckCircle2 size={12} />File berhasil didownload!</p>}
                {error && <p className="text-center text-xs text-red-400 mt-2">{error}</p>}
            </div>

            <div className="bg-notebook-card border border-notebook-border rounded-2xl p-5">
                <h4 className="font-semibold text-sm text-notebook-text-primary mb-3">Tips Menggunakan Laporan</h4>
                <ul className="space-y-2 text-xs text-notebook-text-secondary">
                    <li className="flex gap-2"><span className="text-yellow-400 flex-shrink-0">→</span>Buka di <strong className="text-notebook-text-primary">Obsidian</strong> untuk tampilan yang rapi dengan navigasi antar bagian</li>
                    <li className="flex gap-2"><span className="text-yellow-400 flex-shrink-0">→</span>Konversi ke PDF dengan <strong className="text-notebook-text-primary">Pandoc</strong>: <code className="bg-notebook-bg px-1 rounded">pandoc laporan.md -o laporan.pdf</code></li>
                    <li className="flex gap-2"><span className="text-yellow-400 flex-shrink-0">→</span>Gunakan bagian <strong className="text-notebook-text-primary">Jurnal Relevan</strong> sebagai daftar bacaan tambahan</li>
                    <li className="flex gap-2"><span className="text-yellow-400 flex-shrink-0">→</span>Tunjukkan bagian <strong className="text-notebook-text-primary">Pertanyaan Sidang</strong> ke teman untuk latihan</li>
                </ul>
            </div>
        </div>
    );
}

// ─── Main ThesisPage ──────────────────────────────────────────────────────────

const ThesisPage = ({ workspaceId }) => {
    const [file, setFile]               = useState(null);
    const [uploading, setUploading]     = useState(false);
    const [uploadErr, setUploadErr]     = useState(null);
    const [sessionId, setSessionId]     = useState(null);
    const [uploadInfo, setUploadInfo]   = useState(null);

    const [analyzing, setAnalyzing]           = useState(false);
    const [progress, setProgress]             = useState(0);
    const [steps, setSteps]                   = useState([]);
    const [analysisStatus, setAnalysisStatus] = useState('idle');
    const [analysis, setAnalysis]             = useState(null);
    const [analysisErr, setAnalysisErr]       = useState(null);
    const pollingRef                          = useRef(null);

    const [activeTab, setActiveTab] = useState('analysis');

    useEffect(() => () => { if (pollingRef.current) clearInterval(pollingRef.current); }, []);

    // ── Upload ──────────────────────────────────────────────────────────────
    const handleFile = async (f) => {
        if (!f.name.toLowerCase().endsWith('.pdf')) { setUploadErr('Hanya file PDF yang didukung.'); return; }
        setFile(f); setUploadErr(null); setUploading(true);
        setAnalysis(null); setAnalysisStatus('idle'); setSessionId(null); setSteps([]); setProgress(0);
        try {
            const res = await api.uploadThesis(f, workspaceId);
            setSessionId(res.session_id);
            setUploadInfo({ file_name: res.file_name, char_count: res.char_count });
        } catch (e) {
            setUploadErr(`Upload gagal: ${e.message}`); setFile(null);
        }
        setUploading(false);
    };

    // ── Analyze ─────────────────────────────────────────────────────────────
    const handleAnalyze = async () => {
        if (!sessionId) return;
        setAnalyzing(true); setAnalysisStatus('analyzing'); setAnalysisErr(null); setProgress(0); setSteps([]);
        try { await api.analyzeThesis(sessionId); } catch (e) {
            setAnalysisErr(`Gagal memulai: ${e.message}`); setAnalysisStatus('error'); setAnalyzing(false); return;
        }
        pollingRef.current = setInterval(async () => {
            try {
                const s = await api.getThesisStatus(sessionId);
                setProgress(s.progress ?? 0); setSteps(s.steps ?? []);
                if (s.status === 'done') {
                    clearInterval(pollingRef.current); setAnalysis(s.analysis);
                    setAnalysisStatus('done'); setAnalyzing(false);
                } else if (s.status === 'error') {
                    clearInterval(pollingRef.current); setAnalysisErr(s.error || 'Error di server.');
                    setAnalysisStatus('error'); setAnalyzing(false);
                }
            } catch { /* continue polling */ }
        }, 2500);
    };

    const handleReset = () => {
        if (pollingRef.current) clearInterval(pollingRef.current);
        setFile(null); setSessionId(null); setUploadInfo(null);
        setUploading(false); setUploadErr(null); setAnalyzing(false);
        setAnalysisStatus('idle'); setAnalysis(null); setAnalysisErr(null);
        setProgress(0); setSteps([]); setActiveTab('analysis');
    };

    const isDone = analysisStatus === 'done';

    return (
        <div className="h-full overflow-y-auto bg-notebook-bg text-notebook-text-primary p-8">

            {/* Header */}
            <header className="mb-8 flex items-start justify-between">
                <div>
                    <h1 className="text-3xl font-semibold flex items-center gap-3 mb-1">
                        <span className="p-2 bg-yellow-500/10 rounded-lg text-yellow-500"><GraduationCap size={26} /></span>
                        Bedah Tugas Akhir
                    </h1>
                    <p className="text-notebook-text-secondary text-sm ml-1">Upload PDF skripsi/TA → analisis novelty, gap, revisi, cari jurnal, dan persiapan sidang.</p>
                </div>
                {(file || sessionId) && (
                    <button onClick={handleReset} className="flex items-center gap-2 text-sm text-notebook-text-secondary hover:text-red-400 transition-colors bg-notebook-card border border-notebook-border px-3 py-1.5 rounded-lg">
                        <X size={14} /> Reset
                    </button>
                )}
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

                {/* ── Left Panel: Upload + Status ── */}
                <div className="lg:col-span-4 space-y-5">

                    {/* Upload Zone */}
                    {!sessionId ? (
                        <div className="bg-notebook-card border border-notebook-border rounded-2xl p-5 shadow-sm">
                            <h2 className="text-xs font-semibold text-notebook-text-secondary uppercase tracking-wider mb-4 flex items-center gap-2"><Upload size={14} /> Upload Dokumen</h2>
                            <DropZone onFile={handleFile} disabled={uploading} />
                            {uploading && <div className="mt-3 flex items-center gap-2 text-sm text-notebook-text-secondary"><RotateCw size={14} className="animate-spin text-yellow-400" />Mengekstrak teks PDF...</div>}
                            {uploadErr && <div className="mt-3 flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5"><AlertCircle size={13} />{uploadErr}</div>}
                        </div>
                    ) : (
                        <div className={clsx('bg-notebook-card border rounded-2xl p-5 shadow-sm', isDone ? 'border-green-500/30' : 'border-notebook-border')}>
                            {/* File info */}
                            <div className="flex items-start gap-3 mb-4 pb-4 border-b border-notebook-border/50">
                                <div className="w-10 h-10 rounded-xl bg-yellow-500/10 flex items-center justify-center flex-shrink-0"><FileText size={18} className="text-yellow-400" /></div>
                                <div className="flex-1 min-w-0">
                                    <p className="font-semibold text-notebook-text-primary truncate text-sm">{uploadInfo?.file_name}</p>
                                    <p className="text-xs text-notebook-text-secondary">{uploadInfo?.char_count?.toLocaleString()} karakter diekstrak</p>
                                </div>
                                {isDone && <CheckCircle2 size={16} className="text-green-400 flex-shrink-0 mt-1" />}
                            </div>

                            {/* Analyze button / progress */}
                            {analysisStatus === 'idle' && (
                                <button onClick={handleAnalyze} className="w-full py-3 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-notebook-bg font-bold text-sm flex items-center justify-center gap-2 transition-all active:scale-[.98] shadow-lg shadow-yellow-500/20">
                                    <Sparkles size={16} /> Mulai Analisis Komprehensif
                                </button>
                            )}
                            {analysisStatus === 'analyzing' && <StepIndicator backendSteps={steps} progress={progress} />}
                            {isDone && (
                                <div className="flex items-center gap-2 text-green-400 text-xs bg-green-500/10 border border-green-500/20 rounded-xl px-3 py-2.5">
                                    <CheckCircle2 size={13} />Analisis selesai! Lihat hasil di tab kanan.
                                </div>
                            )}
                            {analysisStatus === 'error' && (
                                <div className="flex items-start gap-2 text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5">
                                    <AlertCircle size={13} className="flex-shrink-0 mt-0.5" />{analysisErr}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Empty state guide */}
                    {!sessionId && (
                        <div className="bg-notebook-card border border-notebook-border rounded-2xl p-5">
                            <p className="text-xs font-semibold text-notebook-text-secondary uppercase tracking-wider mb-3">Fitur yang Tersedia</p>
                            <div className="space-y-2">
                                {[
                                    { icon: Microscope, label: 'Cek Novelty vs Literatur', color: 'purple' },
                                    { icon: TrendingUp, label: 'Identifikasi Research Gap', color: 'green' },
                                    { icon: Swords,     label: 'Kritik Akademis (Peer Review)', color: 'orange' },
                                    { icon: Shield,     label: 'Simulasi Pertanyaan Sidang', color: 'red' },
                                    { icon: PenTool,    label: 'Revisi Bagian TA', color: 'yellow' },
                                    { icon: BookOpen,   label: 'Cari Jurnal Relevan', color: 'blue' },
                                    { icon: MessageSquare, label: 'Chat dengan Dokumen TA', color: 'purple' },
                                    { icon: Download,   label: 'Ekspor Laporan Lengkap', color: 'green' },
                                ].map(({ icon: Icon, label, color }) => {
                                    const c = colorMap[color];
                                    return (
                                        <div key={label} className="flex items-center gap-2.5 text-xs text-notebook-text-secondary">
                                            <span className={clsx('p-1 rounded-md', c.bg)}><Icon size={11} className={c.text} /></span>
                                            {label}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Right Panel: Tabs ── */}
                <div className="lg:col-span-8">
                    {!sessionId ? (
                        <div className="h-full min-h-[500px] flex flex-col items-center justify-center bg-notebook-card border border-notebook-border rounded-2xl text-notebook-text-secondary">
                            <div className="w-20 h-20 rounded-full bg-notebook-bg border border-notebook-border flex items-center justify-center mb-5">
                                <GraduationCap size={34} className="opacity-25" />
                            </div>
                            <h3 className="text-lg font-semibold text-notebook-text-primary mb-2">Belum Ada Dokumen</h3>
                            <p className="text-sm text-center max-w-xs opacity-70">Upload PDF Tugas Akhir kamu di panel kiri untuk memulai bedah akademis lengkap.</p>
                        </div>
                    ) : (
                        <div className="bg-notebook-card border border-notebook-border rounded-2xl overflow-hidden">
                            {/* Tab Bar */}
                            <div className="flex items-center gap-1 p-2 border-b border-notebook-border bg-notebook-bg/50">
                                {TABS.map(tab => {
                                    const Icon = tab.icon;
                                    const isActive = activeTab === tab.id;
                                    const needsAnalysis = ['revise', 'journals', 'chat', 'export'].includes(tab.id);
                                    const disabled = needsAnalysis && !sessionId;
                                    return (
                                        <button key={tab.id} onClick={() => !disabled && setActiveTab(tab.id)} disabled={disabled}
                                            className={clsx('flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-medium transition-all',
                                                isActive ? 'bg-yellow-500/20 text-yellow-400' : disabled ? 'opacity-30 cursor-not-allowed text-notebook-text-secondary' : 'text-notebook-text-secondary hover:text-notebook-text-primary hover:bg-notebook-card'
                                            )}>
                                            <Icon size={13} />
                                            {tab.label}
                                        </button>
                                    );
                                })}
                            </div>

                            {/* Tab Content */}
                            <div className="p-6">
                                <AnimatePresence mode="wait">
                                    <motion.div key={activeTab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.15 }}>
                                        {activeTab === 'analysis' && (
                                            analysisStatus === 'analyzing' ? (
                                                <div className="flex flex-col items-center justify-center py-16 gap-4 text-notebook-text-secondary">
                                                    <div className="relative w-20 h-20">
                                                        <div className="absolute inset-0 rounded-full border-4 border-notebook-border" />
                                                        <div className="absolute inset-0 rounded-full border-4 border-yellow-400 border-t-transparent animate-spin" />
                                                        <div className="absolute inset-0 flex items-center justify-center"><Brain size={24} className="text-yellow-400" /></div>
                                                    </div>
                                                    <p className="font-semibold text-notebook-text-primary">JAYA sedang membaca TA kamu...</p>
                                                    <p className="text-sm opacity-60">Proses membutuhkan beberapa menit</p>
                                                    <div className="w-48 h-1.5 bg-black/30 rounded-full overflow-hidden">
                                                        <motion.div className="h-full rounded-full bg-gradient-to-r from-yellow-500 to-orange-400" style={{ width: `${progress}%` }} />
                                                    </div>
                                                    <p className="text-xs opacity-50">{progress}% selesai</p>
                                                </div>
                                            ) : <AnalysisTab analysis={analysis} sessionId={sessionId} />
                                        )}
                                        {activeTab === 'revise'   && <ReviseTab  sessionId={sessionId} analysis={analysis} />}
                                        {activeTab === 'journals' && <JournalsTab sessionId={sessionId} analysis={analysis} />}
                                        {activeTab === 'chat'     && <ChatTab sessionId={sessionId} workspaceId={workspaceId} />}
                                        {activeTab === 'export'   && <ExportTab sessionId={sessionId} uploadInfo={uploadInfo} analysis={analysis} />}
                                    </motion.div>
                                </AnimatePresence>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ThesisPage;
