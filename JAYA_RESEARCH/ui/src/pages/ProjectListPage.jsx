import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from '../routing/router';
import { Plus, Folder, Clock, ArrowRight, Brain, Search, BookOpen, X, Sparkles, Compass, ChevronRight, Zap } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../services/api';
import { useApp } from '../context/AppContext';
import EnvironmentBadge from '../components/EnvironmentBadge';

// Interactive Feature Card
const FeatureCard = ({ icon: Icon, title, desc, onClick, badge }) => (
    <motion.div
        whileHover={{ y: -4, scale: 1.01 }}
        whileTap={{ scale: 0.98 }}
        onClick={onClick}
        className="linear-card p-6 flex flex-col justify-between cursor-pointer group relative overflow-hidden border border-white/[0.08] hover:border-white/25 transition-all shadow-subtle"
    >
        <div>
            <div className="flex items-center justify-between mb-4">
                <div className="w-10 h-10 rounded-xl bg-white/[0.06] border border-white/[0.08] flex items-center justify-center text-slate-200 group-hover:bg-white/[0.12] group-hover:text-white transition-all shadow-sm">
                    <Icon size={20} />
                </div>
                <div className="flex items-center gap-1.5 text-xs text-slate-400 group-hover:text-white transition-colors font-medium">
                    <span>Buka</span>
                    <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
                </div>
            </div>
            <h4 className="text-sm font-bold text-slate-100 mb-1.5 tracking-tight flex items-center justify-between">
                <span>{title}</span>
                {badge && <span className="text-[10px] font-bold text-sky-400 bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 rounded-full">{badge}</span>}
            </h4>
            <p className="text-xs text-slate-400 leading-relaxed">{desc}</p>
        </div>
    </motion.div>
);

export default function ProjectListPage() {
    const navigate = useNavigate();
    const { appName, version } = useApp();

    const [projects, setProjects] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [newProjectDesc, setNewProjectDesc] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    const loadProjects = useCallback(async () => {
        try {
            setIsLoading(true);
            const data = await api.listWorkspaces();
            const list = Array.isArray(data) ? data : (data.workspaces || []);
            setProjects(list);
        } catch (err) {
            console.error('Failed to load projects:', err);
            setProjects([]);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        let active = true;
        queueMicrotask(() => {
            if (active) void loadProjects();
        });
        return () => {
            active = false;
        };
    }, [loadProjects]);

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!newProjectName.trim()) return;
        setIsCreating(true);
        try {
            await api.createWorkspace(newProjectName.trim());
            await loadProjects();
            setShowCreateModal(false);
            setNewProjectName('');
            setNewProjectDesc('');
        } catch (err) {
            console.error('Failed to create project:', err);
        } finally {
            setIsCreating(false);
        }
    };

    const getTargetWorkspaceId = () => {
        if (projects.length > 0) {
            const first = projects[0];
            return first.id || first.name || first;
        }
        return 'default';
    };

    const handleFeatureClick = (modulePath) => {
        const wsId = getTargetWorkspaceId();
        navigate(`/project/${wsId}/${modulePath}`);
    };

    const filtered = projects.filter(p =>
        (p.name || p).toLowerCase().includes(searchQuery.toLowerCase())
    );

    const features = [
        { icon: Brain,    title: 'Knowledge Chat',    desc: 'Dialog RAG interaktif berbasis AI dengan seluruh paper & skripsi.', path: 'chat', badge: 'RAG Chat' },
        { icon: Search,   title: 'Deep Research',     desc: 'Pencarian hipotesis otonom dari ArXiv, Semantic Scholar & OpenAlex.', path: 'research', badge: 'AI-Q' },
        { icon: Sparkles, title: 'Autonomous Discovery', desc: 'Loop riset otonom & injeksi patch pengetahuan ke basis data otak JAYA.', path: 'evolution', badge: 'Auto Upgrade' },
        { icon: BookOpen, title: 'Thesis Defense',    desc: 'Analisis gap skripsi, uji novelty, dan simulasi revisi otomatis.', path: 'thesis', badge: 'Thesis AI' },
    ];

    return (
        <div className="w-full min-h-screen bg-[#0b0c10] text-slate-100 font-sans relative overflow-x-hidden">
            {/* Subtle Top Ambient Glow */}
            <div className="fixed top-0 left-0 right-0 h-96 bg-gradient-to-b from-slate-800/10 via-transparent to-transparent pointer-events-none z-0" />

            {/* Full Window Responsive Container */}
            <div className="relative z-10 w-full px-6 md:px-12 lg:px-16 py-8">

                {/* Top Header Bar */}
                <header className="flex items-center justify-between pb-8 mb-8 border-b border-white/[0.06]">
                    <div className="flex items-center gap-3.5">
                        <div className="w-10 h-10 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center text-slate-100 shadow-sm">
                            <Brain size={20} />
                        </div>
                        <div>
                            <div className="flex items-center gap-2.5">
                                <h1 className="text-base font-bold text-slate-100 tracking-tight leading-none">{appName}</h1>
                                <span className="text-[10px] font-medium text-slate-400 bg-white/[0.06] border border-white/[0.08] px-2 py-0.5 rounded-full">v{version}</span>
                            </div>
                            <p className="text-xs text-slate-400 mt-1 font-medium">Autonomous Scientific Discovery Engine</p>
                        </div>
                    </div>
                    <EnvironmentBadge />
                </header>

                {/* Hero Banner Section */}
                <div className="mb-10 max-w-4xl">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs text-slate-300 mb-4">
                        <Sparkles size={13} className="text-sky-400" />
                        <span className="font-medium">NVIDIA NIM & AI-Q Research Architecture</span>
                    </div>
                    <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight mb-3 leading-tight clean-gradient-text">
                        Pusat Riset & Penemuan Ilmiah JAYA
                    </h2>
                    <p className="text-slate-400 text-sm md:text-base leading-relaxed">
                        Pilih modul atau workspace di bawah ini untuk memulai analisis skripsi, riset otonom, atau komunikasi RAG.
                    </p>
                </div>

                {/* Interactive Feature Cards Grid */}
                <div className="mb-12">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                        <Zap size={14} className="text-amber-400" />
                        <span>Pilih Modul Riset (Klik Untuk Membuka)</span>
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                        {features.map((f, i) => (
                            <FeatureCard
                                key={i}
                                icon={f.icon}
                                title={f.title}
                                desc={f.desc}
                                badge={f.badge}
                                onClick={() => handleFeatureClick(f.path)}
                            />
                        ))}
                    </div>
                </div>

                {/* Projects Section Header */}
                <div className="flex items-center justify-between mb-6 pt-6 border-t border-white/[0.06]">
                    <div className="flex items-center gap-2">
                        <Compass size={17} className="text-slate-400" />
                        <h3 className="text-xs font-bold text-slate-300 uppercase tracking-widest">
                            Workspace Proyek {projects.length > 0 && <span className="text-slate-400 font-semibold ml-1">({projects.length})</span>}
                        </h3>
                    </div>
                    <div className="flex items-center gap-3">
                        {projects.length > 3 && (
                            <div className="relative">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Cari workspace..."
                                    className="pl-8 pr-3 py-2 text-xs bg-white/[0.04] border border-white/[0.08] rounded-xl text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-white/20 w-60 transition-all"
                                />
                            </div>
                        )}
                        <button
                            id="btn-new-project"
                            onClick={() => setShowCreateModal(true)}
                            className="flex items-center gap-2 px-4 py-2.5 bg-slate-100 hover:bg-white text-slate-950 text-xs font-bold rounded-xl transition-all shadow-md hover:scale-[1.01]"
                        >
                            <Plus size={16} />
                            <span>Workspace Baru</span>
                        </button>
                    </div>
                </div>

                {/* Project Cards Grid */}
                {isLoading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                        {[1, 2, 3, 4].map(i => (
                            <div key={i} className="h-48 rounded-2xl bg-white/[0.02] animate-pulse border border-white/[0.05]" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                        {/* Create New Card */}
                        <motion.div
                            whileHover={{ y: -3, scale: 1.01 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => setShowCreateModal(true)}
                            className="h-48 rounded-2xl border border-dashed border-white/[0.12] hover:border-white/30 flex flex-col items-center justify-center cursor-pointer group transition-all bg-white/[0.01] hover:bg-white/[0.03]"
                        >
                            <div className="w-10 h-10 rounded-xl bg-white/[0.05] border border-white/[0.08] flex items-center justify-center mb-3 text-slate-400 group-hover:text-slate-200 transition-colors">
                                <Plus size={20} />
                            </div>
                            <span className="text-xs font-bold text-slate-400 group-hover:text-slate-200 transition-colors">Buat Workspace Riset Baru</span>
                        </motion.div>

                        {/* Project Cards */}
                        <AnimatePresence>
                            {filtered.map((project, idx) => {
                                const id   = project.id || project.name || project;
                                const name = project.name || project;
                                const desc = project.description || 'Workspace riset & analisis tesis';
                                const date = project.created_at ? new Date(project.created_at).toLocaleDateString('id-ID') : 'Baru dibuat';

                                return (
                                    <motion.div
                                        key={id}
                                        initial={{ opacity: 0, y: 8 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: idx * 0.04 }}
                                        whileHover={{ y: -4, scale: 1.01 }}
                                        whileTap={{ scale: 0.98 }}
                                        onClick={() => navigate(`/project/${id}/chat`)}
                                        className="linear-card h-48 p-5 flex flex-col justify-between cursor-pointer group relative overflow-hidden border border-white/[0.08] hover:border-white/30"
                                    >
                                        <div>
                                            <div className="flex items-center justify-between mb-3">
                                                <div className="w-9 h-9 rounded-xl bg-white/[0.06] border border-white/[0.08] flex items-center justify-center text-slate-200 group-hover:bg-white/[0.12] transition-colors">
                                                    <Folder size={17} />
                                                </div>
                                                <div className="flex items-center gap-1 text-[11px] font-bold text-slate-400 group-hover:text-white transition-colors">
                                                    <span>Buka</span>
                                                    <ChevronRight size={14} className="group-hover:translate-x-1 transition-transform" />
                                                </div>
                                            </div>
                                            <h3 className="text-sm font-bold text-slate-100 mb-1 truncate group-hover:text-white transition-colors">{name}</h3>
                                            <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">{desc}</p>
                                        </div>

                                        <div className="flex items-center justify-between pt-3 border-t border-white/[0.06]">
                                            <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
                                                <Clock size={12} />
                                                <span>{date}</span>
                                            </div>
                                            <span className="text-[10px] font-semibold text-slate-300 bg-white/[0.05] border border-white/[0.08] px-2.5 py-0.5 rounded-full group-hover:bg-white/[0.1] transition-colors">
                                                Buka Workspace →
                                            </span>
                                        </div>
                                    </motion.div>
                                );
                            })}
                        </AnimatePresence>
                    </div>
                )}

                {/* Create Project Modal */}
                <AnimatePresence>
                    {showCreateModal && (
                        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
                            <motion.div
                                initial={{ opacity: 0, scale: 0.96 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 0.96 }}
                                className="bg-[#12141d] border border-white/[0.1] rounded-2xl w-full max-w-md overflow-hidden shadow-2xl p-6"
                            >
                                <div className="flex items-center justify-between mb-4">
                                    <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                                        <Folder size={17} className="text-slate-300" />
                                        Buat Workspace Riset Baru
                                    </h3>
                                    <button onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-white p-1 rounded-lg">
                                        <X size={16} />
                                    </button>
                                </div>

                                <form onSubmit={handleCreate} className="space-y-4">
                                    <div>
                                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Nama Workspace / Judul Skripsi</label>
                                        <input
                                            type="text"
                                            value={newProjectName}
                                            onChange={(e) => setNewProjectName(e.target.value)}
                                            placeholder="Contoh: Optimasi Edge LLM 2026"
                                            required
                                            className="w-full bg-[#181b27] border border-white/[0.1] rounded-xl px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-white/30"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Deskripsi Singkat (Opsional)</label>
                                        <textarea
                                            value={newProjectDesc}
                                            onChange={(e) => setNewProjectDesc(e.target.value)}
                                            placeholder="Catatan topik riset atau deskripsi singkat..."
                                            rows={3}
                                            className="w-full bg-[#181b27] border border-white/[0.1] rounded-xl px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-white/30 resize-none"
                                        />
                                    </div>
                                    <div className="flex items-center justify-end gap-2 pt-2">
                                        <button
                                            type="button"
                                            onClick={() => setShowCreateModal(false)}
                                            className="px-4 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-white"
                                        >
                                            Batal
                                        </button>
                                        <button
                                            type="submit"
                                            disabled={isCreating || !newProjectName.trim()}
                                            className="px-4 py-2 bg-slate-100 text-slate-950 text-xs font-bold rounded-xl shadow-md hover:bg-white transition-all disabled:opacity-50"
                                        >
                                            {isCreating ? 'Membuat...' : 'Buat Workspace'}
                                        </button>
                                    </div>
                                </form>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>

                {/* Footer */}
                <footer className="mt-20 pt-6 border-t border-white/[0.06] text-center text-xs text-slate-500">
                    JAYA Research Engine v{version} · Autonomous Discovery & NVIDIA NIM Ecosystem
                </footer>
            </div>
        </div>
    );
}
