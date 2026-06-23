import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Folder, Clock, ArrowRight, Brain, Search, BookOpen, Network, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../services/api';
import { useApp } from '../context/AppContext';
import EnvironmentBadge from '../components/EnvironmentBadge';

// Feature Card for the hero section
const FeatureCard = ({ icon: Icon, title, desc, color }) => (
    <div className={`flex items-start gap-3 p-4 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/10 transition-colors`}>
        <div className={`w-8 h-8 rounded-lg ${color} flex items-center justify-center shrink-0 mt-0.5`}>
            <Icon size={16} />
        </div>
        <div>
            <p className="text-sm font-semibold text-gray-200">{title}</p>
            <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{desc}</p>
        </div>
    </div>
);

export default function ProjectListPage() {
    const navigate = useNavigate();
    const { isDevMode, appName, version } = useApp();

    const [projects, setProjects] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [newProjectDesc, setNewProjectDesc] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    useEffect(() => { loadProjects(); }, []);

    const loadProjects = async () => {
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
    };

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

    const filtered = projects.filter(p =>
        (p.name || p).toLowerCase().includes(searchQuery.toLowerCase())
    );

    const features = [
        { icon: Brain,    title: 'Knowledge Chat',    desc: 'Tanya JAYA tentang dokumen, jurnal, atau topik apapun', color: 'bg-blue-500/20 text-blue-400' },
        { icon: Search,   title: 'Deep Research',     desc: 'Pencarian akademik otomatis dari ArXiv, Semantic Scholar, OpenAlex', color: 'bg-purple-500/20 text-purple-400' },
        { icon: BookOpen, title: 'Thesis Defense',    desc: 'Bantu merancang, menulis, dan mempertahankan skripsi', color: 'bg-emerald-500/20 text-emerald-400' },
        { icon: Network,  title: 'Knowledge Graph',   desc: 'Visualisasi hubungan antar konsep dari dokumen yang diindeks', color: 'bg-amber-500/20 text-amber-400' },
    ];

    return (
        <div className="min-h-screen bg-[#080a0f] text-gray-200 font-sans">
            {/* Background gradient effect */}
            <div className="fixed inset-0 pointer-events-none">
                <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-600/5 rounded-full blur-3xl" />
                <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-600/5 rounded-full blur-3xl" />
            </div>

            <div className="relative max-w-6xl mx-auto px-8 py-10">

                {/* Top Bar */}
                <div className="flex items-center justify-between mb-12">
                    <div className="flex items-center gap-3">
                        {/* JAYA Logo */}
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                            <Brain size={20} className="text-white" />
                        </div>
                        <div>
                            <h1 className="text-lg font-bold text-white tracking-tight leading-none">{appName}</h1>
                            <p className="text-xs text-gray-600 mt-0.5">AI Research Intelligence</p>
                        </div>
                    </div>
                    <EnvironmentBadge />
                </div>

                {/* Hero */}
                <div className="mb-10">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                    >
                        <h2 className="text-4xl font-bold tracking-tight mb-3">
                            <span className="bg-gradient-to-r from-blue-400 via-purple-400 to-blue-400 bg-clip-text text-transparent">
                                Selamat Datang di JAYA
                            </span>
                        </h2>
                        <p className="text-gray-400 text-lg max-w-xl leading-relaxed">
                            AI Research Intelligence yang membantu Anda membaca jurnal, menganalisis dokumen,
                            dan menemukan penelitian baru secara otonom.
                        </p>
                    </motion.div>
                </div>

                {/* Feature Grid — hanya tampil jika belum ada project */}
                {projects.length === 0 && !isLoading && (
                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="grid grid-cols-2 gap-3 mb-10"
                    >
                        {features.map((f, i) => <FeatureCard key={i} {...f} />)}
                    </motion.div>
                )}

                {/* Projects Section Header */}
                <div className="flex items-center justify-between mb-5">
                    <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">
                        Proyek Penelitian {projects.length > 0 && <span className="text-gray-600 ml-1">({projects.length})</span>}
                    </h3>
                    <div className="flex items-center gap-3">
                        {/* Search */}
                        {projects.length > 3 && (
                            <div className="relative">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Cari proyek..."
                                    className="pl-8 pr-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg text-gray-300 placeholder:text-gray-600 focus:outline-none focus:border-blue-500/50 w-48"
                                />
                            </div>
                        )}
                        {/* New Project Button */}
                        <button
                            id="btn-new-project"
                            onClick={() => setShowCreateModal(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 hover:-translate-y-0.5 transform"
                        >
                            <Plus size={16} />
                            <span>Proyek Baru</span>
                        </button>
                    </div>
                </div>

                {/* Project Grid */}
                {isLoading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="h-44 rounded-2xl bg-white/[0.03] animate-pulse border border-white/5" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {/* Create New Card */}
                        <motion.div
                            whileHover={{ y: -3, scale: 1.01 }}
                            whileTap={{ scale: 0.99 }}
                            onClick={() => setShowCreateModal(true)}
                            className="h-44 rounded-2xl border-2 border-dashed border-white/10 hover:border-blue-500/30 flex flex-col items-center justify-center cursor-pointer group transition-all bg-white/[0.02] hover:bg-white/[0.04]"
                        >
                            <div className="w-10 h-10 rounded-xl bg-white/5 group-hover:bg-blue-500/20 flex items-center justify-center mb-3 transition-colors">
                                <Plus size={20} className="text-gray-500 group-hover:text-blue-400 transition-colors" />
                            </div>
                            <span className="text-sm font-medium text-gray-500 group-hover:text-gray-300 transition-colors">Buat proyek baru</span>
                        </motion.div>

                        {/* Project Cards */}
                        <AnimatePresence>
                            {filtered.map((project, idx) => {
                                const id   = project.id || project.name || project;
                                const name = project.name || project;
                                const desc = project.description || 'Workspace penelitian';
                                const date = project.created_at ? new Date(project.created_at).toLocaleDateString('id-ID') : 'Baru dibuat';

                                // Generate a color based on name for variety
                                const colors = [
                                    'from-blue-500/20 to-cyan-500/20 text-blue-400',
                                    'from-purple-500/20 to-pink-500/20 text-purple-400',
                                    'from-emerald-500/20 to-teal-500/20 text-emerald-400',
                                    'from-amber-500/20 to-orange-500/20 text-amber-400',
                                ];
                                const color = colors[idx % colors.length];

                                return (
                                    <motion.div
                                        key={id}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: idx * 0.05 }}
                                        whileHover={{ y: -3, scale: 1.01 }}
                                        whileTap={{ scale: 0.99 }}
                                        onClick={() => navigate(`/project/${id}/chat`)}
                                        className="h-44 p-5 rounded-2xl bg-[#0d1018] border border-white/8 hover:border-white/15 cursor-pointer flex flex-col justify-between group shadow-sm hover:shadow-lg hover:shadow-black/30 transition-all relative overflow-hidden"
                                    >
                                        {/* Subtle corner gradient on hover */}
                                        <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-bl from-white/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

                                        <div>
                                            <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center mb-3`}>
                                                <Folder size={17} />
                                            </div>
                                            <h3 className="text-base font-semibold text-gray-100 mb-1 truncate group-hover:text-white transition-colors">{name}</h3>
                                            <p className="text-xs text-gray-500 line-clamp-2 leading-relaxed">{desc}</p>
                                        </div>

                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-1.5 text-xs text-gray-600">
                                                <Clock size={11} />
                                                <span>{date}</span>
                                            </div>
                                            <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                                                <div className="w-7 h-7 rounded-lg bg-blue-500/20 flex items-center justify-center text-blue-400">
                                                    <ArrowRight size={14} />
                                                </div>
                                            </div>
                                        </div>
                                    </motion.div>
                                );
                            })}
                        </AnimatePresence>
                    </div>
                )}

                {/* Footer */}
                <div className="mt-16 text-center text-xs text-gray-700">
                    JAYA Research v{version} · Powered by NVIDIA NIM
                    {isDevMode && <span className="text-amber-600 ml-2">· DEV BUILD</span>}
                </div>
            </div>

            {/* Create Modal */}
            <AnimatePresence>
                {showCreateModal && (
                    <div className="fixed inset-0 bg-black/70 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div
                            initial={{ scale: 0.92, opacity: 0, y: 10 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.92, opacity: 0, y: 10 }}
                            transition={{ type: 'spring', damping: 25 }}
                            className="bg-[#0d1018] w-full max-w-md rounded-2xl border border-white/10 p-6 shadow-2xl"
                        >
                            <div className="flex items-center justify-between mb-6">
                                <div>
                                    <h2 className="text-lg font-semibold text-white">Buat Proyek Baru</h2>
                                    <p className="text-xs text-gray-500 mt-0.5">Proyek = workspace terisolasi untuk penelitian Anda</p>
                                </div>
                                <button
                                    onClick={() => { setShowCreateModal(false); setNewProjectName(''); }}
                                    className="p-1.5 hover:bg-white/5 rounded-lg text-gray-500 hover:text-gray-300 transition-colors"
                                >
                                    <X size={16} />
                                </button>
                            </div>

                            <form onSubmit={handleCreate} className="space-y-4">
                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1.5">
                                        Nama Proyek <span className="text-red-400">*</span>
                                    </label>
                                    <input
                                        id="input-project-name"
                                        type="text"
                                        value={newProjectName}
                                        onChange={(e) => setNewProjectName(e.target.value)}
                                        placeholder="cth: Skripsi Sistem Informasi 2025"
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all"
                                        autoFocus
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1.5">
                                        Deskripsi <span className="text-gray-600">(opsional)</span>
                                    </label>
                                    <textarea
                                        id="input-project-desc"
                                        value={newProjectDesc}
                                        onChange={(e) => setNewProjectDesc(e.target.value)}
                                        placeholder="Topik atau tujuan penelitian..."
                                        rows={2}
                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all resize-none"
                                    />
                                </div>

                                <div className="flex justify-end gap-3 pt-2">
                                    <button
                                        type="button"
                                        onClick={() => setShowCreateModal(false)}
                                        className="px-4 py-2.5 rounded-xl text-sm text-gray-400 hover:text-gray-200 hover:bg-white/5 transition-colors"
                                    >
                                        Batal
                                    </button>
                                    <button
                                        id="btn-create-project"
                                        type="submit"
                                        disabled={!newProjectName.trim() || isCreating}
                                        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/30 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-blue-500/20 flex items-center gap-2"
                                    >
                                        {isCreating ? (
                                            <>
                                                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                Membuat...
                                            </>
                                        ) : (
                                            <>
                                                <Plus size={15} /> Buat Proyek
                                            </>
                                        )}
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
}
