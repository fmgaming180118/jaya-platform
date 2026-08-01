import { useMemo, useState } from 'react';
import {
    AlertCircle,
    Ban,
    BookOpen,
    CheckCircle2,
    Database,
    FileText,
    FlaskConical,
    Hash,
    Layers3,
    Link2,
    LoaderCircle,
    RotateCcw,
    Search,
    Shield,
} from 'lucide-react';
import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';

import api from '../services/api';

const STATUS_PRESENTATION = {
    ANSWERED: {
        label: 'Evidence ditemukan',
        description: 'Jawaban disusun secara ekstraktif dari evidence yang ditampilkan.',
        tone: 'emerald',
        icon: CheckCircle2,
    },
    ABSTAINED_NO_EVIDENCE: {
        label: 'Abstain — evidence tidak ditemukan',
        description: 'Sistem tidak membuat jawaban tanpa sumber yang dapat ditelusuri.',
        tone: 'amber',
        icon: Ban,
    },
    ABSTAINED_LOW_CONFIDENCE: {
        label: 'Abstain — confidence evidence rendah',
        description: 'Candidate retrieval berada di bawah ambang penerimaan lokal.',
        tone: 'amber',
        icon: AlertCircle,
    },
    CONFLICTING_EVIDENCE: {
        label: 'Evidence saling bertentangan',
        description: 'Tidak ada klaim rekonsiliasi; sumber perlu diperiksa secara manual.',
        tone: 'red',
        icon: AlertCircle,
    },
};

const TONE_CLASSES = {
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300',
    amber: 'bg-amber-500/10 border-amber-500/30 text-amber-300',
    red: 'bg-red-500/10 border-red-500/30 text-red-300',
    slate: 'bg-slate-500/10 border-slate-500/30 text-slate-300',
};

function statusPresentation(status) {
    return STATUS_PRESENTATION[status] || {
        label: status || 'Status tidak tersedia',
        description: 'Backend mengembalikan status yang belum dikenal UI. Periksa artefak dan sumber.',
        tone: 'slate',
        icon: AlertCircle,
    };
}

function asObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function citationLocation(citation) {
    const parts = [];
    if (citation.page_number !== null && citation.page_number !== undefined) {
        parts.push(`halaman ${citation.page_number}`);
    }
    if (citation.span_start !== null && citation.span_start !== undefined) {
        const end = citation.span_end ?? '?';
        parts.push(`span ${citation.span_start}–${end}`);
    }
    return parts.length ? parts.join(' · ') : 'lokasi rinci tidak tersedia';
}

function sourceView(source, index) {
    const item = asObject(source);
    const metadata = {
        ...asObject(item.document),
        ...asObject(item.metadata),
    };
    return {
        id: metadata.source_id || metadata.source_uri || `source-${index + 1}`,
        uri: metadata.source_uri || metadata.path || metadata.file_name || '',
        title: metadata.title || metadata.file_name || metadata.source_id || `Source ${index + 1}`,
        page: metadata.page_number,
        license: metadata.license_id || metadata.license || 'UNKNOWN',
        score: Number.isFinite(Number(item.score)) ? Number(item.score) : null,
        scoreKind: item.score_kind || 'UNSPECIFIED',
        depth: item.retrieval_depth,
        content: String(item.content || item.snippet || '').trim(),
    };
}

function StatusBanner({ status }) {
    const presentation = statusPresentation(status);
    const Icon = presentation.icon;
    return (
        <div className={clsx('rounded-2xl border p-4 flex items-start gap-3', TONE_CLASSES[presentation.tone])}>
            <Icon size={18} className="mt-0.5 shrink-0" />
            <div>
                <p className="text-sm font-bold">{presentation.label}</p>
                <p className="text-[11px] opacity-80 mt-1 leading-relaxed">{presentation.description}</p>
                <code className="inline-block mt-2 text-[10px] font-mono opacity-75">{status || 'UNKNOWN'}</code>
            </div>
        </div>
    );
}

function EvidenceSummary({ result }) {
    const citations = Array.isArray(result.citations) ? result.citations : [];
    const sources = Array.isArray(result.sources) ? result.sources : [];
    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <SummaryCard icon={Database} label="Sources" value={sources.length} />
            <SummaryCard icon={Link2} label="Citations" value={citations.length} />
            <SummaryCard icon={Layers3} label="Depth reached" value={result.depth_reached ?? 0} />
            <SummaryCard
                icon={Shield}
                label="Promotion gate"
                value={result.promotable === true ? 'Review eligible' : 'Non-promotable'}
            />
        </div>
    );
}

function SummaryCard({ icon: Icon, label, value }) {
    return (
        <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
            <p className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <Icon size={11} /> {label}
            </p>
            <p className="mt-2 text-sm font-bold text-slate-200 break-words">{value}</p>
        </div>
    );
}

function PromotionNotice({ promotable }) {
    const eligible = promotable === true;
    return (
        <div className={clsx(
            'rounded-xl border p-3 flex items-start gap-2.5',
            eligible
                ? 'bg-sky-500/8 border-sky-500/25 text-sky-200'
                : 'bg-amber-500/8 border-amber-500/25 text-amber-200'
        )}>
            <Shield size={15} className="mt-0.5 shrink-0" />
            <div>
                <p className="text-xs font-bold">
                    {eligible ? 'Candidate eligible untuk review terpisah' : 'Candidate non-promotable'}
                </p>
                <p className="text-[10px] opacity-80 mt-1 leading-relaxed">
                    {eligible
                        ? 'Status ini bukan verified, applied, atau deployed. Gate Core dan persetujuan manusia tetap wajib.'
                        : 'Evidence belum memenuhi promotion gate. Tidak ada perubahan pada JAYA_CORE atau sistem lain.'}
                </p>
            </div>
        </div>
    );
}

function CitationCard({ citation, index }) {
    const item = asObject(citation);
    const score = Number(item.retrieval_score);
    return (
        <div className="rounded-xl border border-white/[0.07] bg-black/15 p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                    <p className="text-xs font-bold text-sky-300">
                        {item.citation_id || `CIT-${index + 1}`}
                    </p>
                    <p className="text-[10px] text-slate-500 font-mono mt-1 break-all">
                        {item.source_id || 'source_id tidak tersedia'}
                    </p>
                </div>
                <span className={clsx(
                    'px-2 py-1 rounded-lg border text-[9px] font-bold uppercase tracking-wide',
                    item.provenance_complete
                        ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'
                        : 'bg-amber-500/10 border-amber-500/25 text-amber-300'
                )}>
                    {item.provenance_complete ? 'Provenance lengkap' : 'Provenance belum lengkap'}
                </span>
            </div>

            <blockquote className="text-[11px] text-slate-300 leading-relaxed border-l-2 border-sky-500/40 pl-3">
                {item.snippet || 'Snippet tidak tersedia.'}
            </blockquote>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-[10px]">
                <MetadataRow label="Source URI" value={item.source_uri || 'tidak tersedia'} mono />
                <MetadataRow label="Lokasi" value={citationLocation(item)} />
                <MetadataRow label="License" value={item.license_id || 'UNKNOWN'} />
                <MetadataRow
                    label="Retrieval score"
                    value={Number.isFinite(score) ? `${score.toFixed(4)} (${item.score_kind || 'UNSPECIFIED'})` : 'tidak tersedia'}
                />
                <MetadataRow label="Chunk SHA-256" value={item.chunk_sha256 || 'tidak tersedia'} mono />
                <MetadataRow label="Accessed at" value={item.accessed_at || 'tidak tersedia'} />
            </dl>
        </div>
    );
}

function SourceCard({ source, index }) {
    const item = sourceView(source, index);
    return (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-2">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-[11px] font-bold text-slate-200 truncate">{item.title}</p>
                    <p className="text-[9px] text-slate-600 font-mono break-all mt-0.5">{item.uri || item.id}</p>
                </div>
                {item.score !== null && (
                    <span className="text-[9px] font-mono text-sky-300 bg-sky-500/10 border border-sky-500/20 px-1.5 py-0.5 rounded">
                        {item.score.toFixed(4)}
                    </span>
                )}
            </div>
            {item.content && (
                <p className="text-[10px] text-slate-400 leading-relaxed line-clamp-4">{item.content}</p>
            )}
            <div className="flex flex-wrap gap-1.5 text-[9px] text-slate-500">
                <span className="px-1.5 py-0.5 rounded bg-white/[0.04]">license: {item.license}</span>
                {item.page !== undefined && item.page !== null && (
                    <span className="px-1.5 py-0.5 rounded bg-white/[0.04]">page: {item.page}</span>
                )}
                {item.depth !== undefined && (
                    <span className="px-1.5 py-0.5 rounded bg-white/[0.04]">depth: {item.depth}</span>
                )}
                <span className="px-1.5 py-0.5 rounded bg-white/[0.04]">score kind: {item.scoreKind}</span>
            </div>
        </div>
    );
}

function MetadataRow({ label, value, mono = false }) {
    return (
        <div className="min-w-0">
            <dt className="text-slate-600 uppercase tracking-wide">{label}</dt>
            <dd className={clsx('text-slate-300 mt-0.5 break-all', mono && 'font-mono')}>{value}</dd>
        </div>
    );
}

function ArtifactPanel({ result }) {
    return (
        <div className="rounded-2xl border border-purple-500/20 bg-purple-500/[0.04] p-4">
            <div className="flex items-center gap-2 text-purple-300 mb-3">
                <FileText size={15} />
                <h3 className="text-xs font-bold">Artefak candidate</h3>
            </div>
            <dl className="space-y-3 text-[10px]">
                <MetadataRow label="Artifact URI" value={result.artifact_uri || 'tidak tersedia'} mono />
                <MetadataRow label="Artifact SHA-256" value={result.artifact_sha256 || 'tidak tersedia'} mono />
            </dl>
            <p className="text-[10px] text-purple-200/60 mt-3 leading-relaxed">
                URI dan checksum memungkinkan artefak diaudit. Keberadaan artefak tidak berarti hasil telah diverifikasi atau diterapkan.
            </p>
        </div>
    );
}

function ResearchResult({ result }) {
    const citations = Array.isArray(result.citations) ? result.citations : [];
    const sources = Array.isArray(result.sources) ? result.sources : [];
    const answeredWithoutCitation = result.status === 'ANSWERED' && citations.length === 0;

    return (
        <motion.section
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4"
        >
            <StatusBanner status={result.status} />
            <EvidenceSummary result={result} />
            <PromotionNotice promotable={result.promotable} />

            {answeredWithoutCitation && (
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-red-200 flex items-start gap-2">
                    <AlertCircle size={15} className="mt-0.5 shrink-0" />
                    <p className="text-[10px] leading-relaxed">
                        Backend menandai hasil ANSWERED tanpa citation. Perlakukan sebagai contract violation dan jangan gunakan synthesis sebagai evidence.
                    </p>
                </div>
            )}

            <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-5">
                <div className="flex items-center gap-2 mb-4">
                    <BookOpen size={15} className="text-sky-300" />
                    <h2 className="text-sm font-bold text-slate-100">Synthesis ekstraktif</h2>
                </div>
                <div className="prose prose-invert prose-sm max-w-none text-slate-300 text-xs leading-relaxed">
                    <ReactMarkdown>{String(result.synthesis || 'Tidak ada synthesis yang dikembalikan.')}</ReactMarkdown>
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
                <div className="xl:col-span-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="flex items-center justify-between gap-3 mb-3">
                        <h2 className="text-xs font-bold text-slate-200 flex items-center gap-2">
                            <Link2 size={13} className="text-sky-300" /> Citations
                        </h2>
                        <span className="text-[9px] text-slate-500">{citations.length} item</span>
                    </div>
                    <div className="space-y-3">
                        {citations.length > 0 ? citations.map((citation, index) => (
                            <CitationCard
                                key={citation?.citation_id || citation?.chunk_sha256 || index}
                                citation={citation}
                                index={index}
                            />
                        )) : (
                            <EmptyEvidence message="Tidak ada citation. Sistem seharusnya abstain jika evidence tidak tersedia." />
                        )}
                    </div>
                </div>
                <ArtifactPanel result={result} />
            </div>

            <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4">
                <div className="flex items-center justify-between gap-3 mb-3">
                    <h2 className="text-xs font-bold text-slate-200 flex items-center gap-2">
                        <Database size={13} className="text-emerald-300" /> Retrieved sources
                    </h2>
                    <span className="text-[9px] text-slate-500">{sources.length} item</span>
                </div>
                {sources.length > 0 ? (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        {sources.map((source, index) => (
                            <SourceCard
                                key={`${sourceView(source, index).id}-${index}`}
                                source={source}
                                index={index}
                            />
                        ))}
                    </div>
                ) : (
                    <EmptyEvidence message="Tidak ada source retrieval untuk query ini." />
                )}
            </div>
        </motion.section>
    );
}

function EmptyEvidence({ message }) {
    return (
        <div className="rounded-xl border border-dashed border-white/10 p-6 text-center">
            <Database size={20} className="mx-auto text-slate-700 mb-2" />
            <p className="text-[10px] text-slate-500">{message}</p>
        </div>
    );
}

function validateInputs(query, depthValue, maxSourcesValue) {
    const normalizedQuery = query.trim();
    const depth = Number(depthValue);
    const maxSourcesPerLevel = Number(maxSourcesValue);
    if (!normalizedQuery) return { error: 'Pertanyaan riset wajib diisi.' };
    if (normalizedQuery.length > 8_000) return { error: 'Pertanyaan maksimal 8.000 karakter.' };
    if (!Number.isInteger(depth) || depth < 1 || depth > 5) {
        return { error: 'Depth harus berupa bilangan bulat antara 1 dan 5.' };
    }
    if (!Number.isInteger(maxSourcesPerLevel) || maxSourcesPerLevel < 1 || maxSourcesPerLevel > 10) {
        return { error: 'Sources per level harus berupa bilangan bulat antara 1 dan 10.' };
    }
    return { query: normalizedQuery, depth, maxSourcesPerLevel };
}

export default function ResearchPage({ workspaceId }) {
    const activeWorkspace = workspaceId || 'default';
    const [query, setQuery] = useState('');
    const [depth, setDepth] = useState('3');
    const [maxSourcesPerLevel, setMaxSourcesPerLevel] = useState('5');
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const queryLength = query.length;
    const validation = useMemo(
        () => validateInputs(query, depth, maxSourcesPerLevel),
        [query, depth, maxSourcesPerLevel]
    );

    const runResearch = async (event) => {
        event.preventDefault();
        if (validation.error) {
            setError(validation.error);
            return;
        }
        setIsLoading(true);
        setError('');
        try {
            const response = await api.startRecursiveResearch(
                validation.query,
                activeWorkspace,
                validation.depth,
                validation.maxSourcesPerLevel
            );
            if (!response || typeof response !== 'object' || typeof response.status !== 'string') {
                throw new Error('Backend mengembalikan response deep research yang tidak valid.');
            }
            setResult(response);
        } catch (requestError) {
            const code = requestError?.code ? `[${requestError.code}] ` : '';
            setError(`${code}${requestError?.message || 'Deep research gagal dijalankan.'}`);
        } finally {
            setIsLoading(false);
        }
    };

    const resetResearch = () => {
        setResult(null);
        setError('');
        setQuery('');
        setDepth('3');
        setMaxSourcesPerLevel('5');
    };

    return (
        <div className="min-h-full bg-[#0b0c10] text-slate-100 p-5 lg:p-7 overflow-y-auto">
            <div className="max-w-6xl mx-auto space-y-6">
                <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-5 border-b border-white/[0.07]">
                    <div>
                        <div className="flex items-center gap-3">
                            <span className="p-2.5 rounded-xl bg-sky-500/10 border border-sky-500/20 text-sky-300">
                                <FlaskConical size={20} />
                            </span>
                            <div>
                                <p className="text-[10px] uppercase tracking-[0.2em] text-sky-400 font-bold">Phase A</p>
                                <h1 className="text-xl font-bold">Deep Research berbasis evidence</h1>
                            </div>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-3 max-w-2xl leading-relaxed">
                            Retrieval berjalan secara bounded. JAYA menjawab hanya dari evidence yang dapat ditelusuri,
                            menampilkan konflik, atau abstain ketika bukti tidak memadai.
                        </p>
                    </div>
                    <div className="rounded-xl border border-white/[0.08] bg-white/[0.025] px-3 py-2 min-w-48">
                        <p className="text-[9px] uppercase tracking-wider text-slate-600">Workspace boundary</p>
                        <p className="text-xs font-mono text-slate-300 mt-1 break-all">{activeWorkspace}</p>
                    </div>
                </header>

                <form onSubmit={runResearch} className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-5 space-y-4">
                    <div>
                        <div className="flex items-center justify-between gap-3 mb-2">
                            <label htmlFor="research-query" className="text-xs font-bold text-slate-200 flex items-center gap-2">
                                <Search size={13} className="text-sky-300" /> Pertanyaan riset
                            </label>
                            <span className={clsx('text-[9px] font-mono', queryLength > 8_000 ? 'text-red-400' : 'text-slate-600')}>
                                {queryLength}/8000
                            </span>
                        </div>
                        <textarea
                            id="research-query"
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            maxLength={8_001}
                            rows={5}
                            disabled={isLoading}
                            placeholder="Contoh: Bukti apa yang mendukung penggunaan provenance SHA-256 pada evaluasi retrieval?"
                            className="w-full resize-y rounded-xl border border-white/[0.1] bg-black/20 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500/40 disabled:opacity-60"
                        />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <label className="rounded-xl border border-white/[0.07] bg-black/10 p-3">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                                <Layers3 size={11} /> Retrieval depth
                            </span>
                            <input
                                type="number"
                                min="1"
                                max="5"
                                step="1"
                                value={depth}
                                disabled={isLoading}
                                onChange={(event) => setDepth(event.target.value)}
                                className="mt-2 w-full bg-transparent text-sm font-bold text-slate-200 focus:outline-none disabled:opacity-60"
                            />
                            <span className="text-[9px] text-slate-600">Batas backend: 1–5</span>
                        </label>
                        <label className="rounded-xl border border-white/[0.07] bg-black/10 p-3">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                                <Database size={11} /> Sources per level
                            </span>
                            <input
                                type="number"
                                min="1"
                                max="10"
                                step="1"
                                value={maxSourcesPerLevel}
                                disabled={isLoading}
                                onChange={(event) => setMaxSourcesPerLevel(event.target.value)}
                                className="mt-2 w-full bg-transparent text-sm font-bold text-slate-200 focus:outline-none disabled:opacity-60"
                            />
                            <span className="text-[9px] text-slate-600">Batas backend: 1–10</span>
                        </label>
                    </div>

                    <AnimatePresence>
                        {error && (
                            <motion.div
                                initial={{ opacity: 0, y: -5 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                                role="alert"
                                className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-red-200 flex items-start gap-2"
                            >
                                <AlertCircle size={15} className="mt-0.5 shrink-0" />
                                <p className="text-[11px] leading-relaxed">{error}</p>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                        <p className="text-[10px] text-slate-500 leading-relaxed max-w-xl">
                            Hasil adalah candidate research. Tidak ada instalasi, injeksi, atau mutasi JAYA_CORE dari halaman ini.
                        </p>
                        <div className="flex gap-2 shrink-0">
                            {(result || query) && (
                                <button
                                    type="button"
                                    onClick={resetResearch}
                                    disabled={isLoading}
                                    className="px-3 py-2 rounded-xl border border-white/[0.1] bg-white/[0.03] text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors text-xs flex items-center gap-1.5 disabled:opacity-50"
                                >
                                    <RotateCcw size={12} /> Reset
                                </button>
                            )}
                            <button
                                type="submit"
                                disabled={isLoading || Boolean(validation.error)}
                                className="px-4 py-2 rounded-xl border border-sky-500/35 bg-sky-500/15 text-sky-200 hover:bg-sky-500/25 transition-colors text-xs font-bold flex items-center gap-2 disabled:opacity-45 disabled:cursor-not-allowed"
                            >
                                {isLoading ? (
                                    <><LoaderCircle size={13} className="animate-spin" /> Meneliti...</>
                                ) : (
                                    <><Search size={13} /> Jalankan deep research</>
                                )}
                            </button>
                        </div>
                    </div>
                </form>

                <AnimatePresence mode="wait">
                    {isLoading && !result ? (
                        <motion.div
                            key="loading"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="rounded-2xl border border-dashed border-sky-500/20 bg-sky-500/[0.025] p-10 text-center"
                        >
                            <LoaderCircle size={24} className="animate-spin mx-auto text-sky-300" />
                            <p className="text-xs font-bold text-slate-300 mt-3">Menjalankan retrieval bounded</p>
                            <p className="text-[10px] text-slate-600 mt-1">Tidak ada jawaban generatif tanpa evidence.</p>
                        </motion.div>
                    ) : result ? (
                        <ResearchResult key={`${result.artifact_sha256 || result.query}-${result.status}`} result={result} />
                    ) : (
                        <motion.div
                            key="empty"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="rounded-2xl border border-dashed border-white/10 p-10 text-center"
                        >
                            <Hash size={25} className="mx-auto text-slate-700" />
                            <p className="text-xs font-bold text-slate-400 mt-3">Belum ada artefak research</p>
                            <p className="text-[10px] text-slate-600 mt-1">Masukkan pertanyaan untuk mengambil evidence dari workspace ini.</p>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
