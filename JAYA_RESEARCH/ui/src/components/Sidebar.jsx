import { useState, useEffect } from 'react';
import { NavLink, Link } from 'react-router-dom';
import {
    MessageSquare, Library, Network, BookOpen, Activity,
    ChevronLeft, Settings, Code2, FlaskConical, X, RotateCw,
    CheckCircle2, ChevronDown
} from 'lucide-react';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';
import { useApp } from '../context/AppContext';
import EnvironmentBadge from './EnvironmentBadge';
import api from '../services/api';

const NavItem = ({ to, icon: Icon, label, devOnly = false }) => {
    const { isDevMode } = useApp();
    if (devOnly && !isDevMode) return null;

    return (
        <NavLink
            to={to}
            className={({ isActive }) => clsx(
                'flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 group mx-2',
                'hover:bg-white/5',
                isActive
                    ? 'bg-white/8 text-white font-medium shadow-sm'
                    : 'text-gray-400 hover:text-gray-200'
            )}
        >
            {({ isActive }) => (
                <>
                    <div className={clsx(
                        'w-8 h-8 rounded-lg flex items-center justify-center transition-all',
                        isActive
                            ? 'bg-gradient-to-br from-blue-500/30 to-purple-500/30 text-blue-300'
                            : 'text-gray-500 group-hover:text-gray-300'
                    )}>
                        <Icon size={17} />
                    </div>
                    <span className="text-sm tracking-wide flex-1">{label}</span>
                    {devOnly && (
                        <span className="text-[9px] font-bold text-amber-400/60 bg-amber-500/10 px-1.5 py-0.5 rounded uppercase tracking-wider">DEV</span>
                    )}
                </>
            )}
        </NavLink>
    );
};

export default function Sidebar({ workspaceId }) {
    const { isDevMode, features } = useApp();
    const baseUrl = `/project/${workspaceId}`;

    // Settings Modal State
    const [showSettings, setShowSettings] = useState(false);
    const [models, setModels] = useState([]);
    const [activeModel, setActiveModel] = useState('');
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [success, setSuccess] = useState(false);

    // Fetch models on settings open
    useEffect(() => {
        if (showSettings) {
            setLoading(true);
            setSuccess(false);
            api.getModels()
                .then(res => {
                    setModels(res.available_models || []);
                    setActiveModel(res.active_model || '');
                })
                .catch(err => {
                    console.error('[Sidebar] Gagal mengambil list model:', err);
                })
                .finally(() => {
                    setLoading(false);
                });
        }
    }, [showSettings]);

    const handleSave = async () => {
        if (!activeModel) return;
        setSaving(true);
        setSuccess(false);
        try {
            await api.updateModel(activeModel);
            setSuccess(true);
            setTimeout(() => {
                setShowSettings(false);
                setSuccess(false);
            }, 1000);
        } catch (err) {
            console.error('[Sidebar] Gagal memperbarui model:', err);
        } finally {
            setSaving(false);
        }
    };

    return (
        <aside className="w-[260px] h-full bg-[#0c0e13] border-r border-white/5 flex flex-col py-5 shrink-0">

            {/* Back Button & Project Name */}
            <div className="px-4 mb-5">
                <Link
                    to="/"
                    className="flex items-center gap-2 text-gray-500 hover:text-gray-300 transition-colors mb-4 px-2 group"
                >
                    <ChevronLeft size={15} className="group-hover:-translate-x-0.5 transition-transform" />
                    <span className="text-xs font-medium">Semua Proyek</span>
                </Link>

                <div className="px-2">
                    <h2 className="text-base font-bold text-white truncate leading-tight">{workspaceId}</h2>
                    <p className="text-xs text-gray-600 mt-0.5">Workspace Aktif</p>
                </div>
            </div>

            {/* Divider */}
            <div className="mx-4 border-t border-white/5 mb-3" />

            {/* Navigation */}
            <nav className="space-y-0.5 flex-1 overflow-y-auto px-2">
                {/* Label Seksi */}
                <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest px-4 pt-1 pb-2">Menu Utama</p>

                <NavItem to={`${baseUrl}/chat`}     icon={MessageSquare} label="Knowledge Chat" />
                <NavItem to={`${baseUrl}/research`} icon={Library}       label="Deep Research" />
                <NavItem to={`${baseUrl}/graph`}    icon={Network}       label="Knowledge Graph" />
                {features.thesisMode && (
                    <NavItem to={`${baseUrl}/thesis`} icon={BookOpen} label="Thesis Defense" />
                )}

                {/* Label Seksi DEV-ONLY */}
                {isDevMode && (
                    <>
                        <p className="text-[10px] font-semibold text-amber-500/50 uppercase tracking-widest px-4 pt-4 pb-2 flex items-center gap-1.5">
                            <Code2 size={10} /> Developer Only
                        </p>
                        <NavItem to={`${baseUrl}/evolution`} icon={Activity}    label="Digital Twin"   devOnly />
                        <NavItem to={`${baseUrl}/evolution`} icon={FlaskConical} label="Experiments"   devOnly />
                    </>
                )}
            </nav>

            {/* Footer */}
            <div className="mt-auto px-4 pt-4 border-t border-white/5 space-y-3">
                {/* Environment Badge */}
                <div className="px-2">
                    <EnvironmentBadge />
                </div>

                {/* Settings — selalu tampil */}
                <div
                    onClick={() => setShowSettings(true)}
                    className="flex items-center gap-3 px-2 py-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-white/5 cursor-pointer transition-colors group"
                >
                    <div className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
                        <Settings size={14} />
                    </div>
                    <span className="text-sm">Pengaturan</span>
                </div>
            </div>

            {/* Settings Modal (AnimatePresence) */}
            <AnimatePresence>
                {showSettings && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            className="bg-[#141721] border border-white/10 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl text-left"
                        >
                            {/* Modal Header */}
                            <div className="p-5 border-b border-white/5 flex items-center justify-between">
                                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                                    <Settings size={16} className="text-yellow-400" />
                                    Pengaturan Model
                                </h3>
                                <button
                                    onClick={() => setShowSettings(false)}
                                    className="text-gray-400 hover:text-white transition-colors"
                                >
                                    <X size={16} />
                                </button>
                            </div>
                            
                            {/* Modal Content */}
                            <div className="p-5 space-y-4">
                                <div>
                                    <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider block mb-2">
                                        NVIDIA NIM Model Penyelidikan (Reasoning)
                                    </label>
                                    {loading ? (
                                        <div className="flex items-center gap-2.5 text-xs text-gray-500 py-3">
                                            <RotateCw size={13} className="animate-spin text-yellow-400" />
                                            <span>Mengambil daftar model dari NVIDIA NIM API...</span>
                                        </div>
                                    ) : (
                                        <div className="relative">
                                            <select
                                                value={activeModel}
                                                onChange={(e) => {
                                                    setActiveModel(e.target.value);
                                                    setSuccess(false);
                                                }}
                                                className="w-full bg-[#0c0e13] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-yellow-500/50 appearance-none cursor-pointer pr-10"
                                            >
                                                {models.map(m => (
                                                    <option key={m} value={m} className="bg-[#141721] text-white">
                                                        {m}
                                                    </option>
                                                ))}
                                            </select>
                                            <ChevronDown size={13} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                                        </div>
                                    )}
                                    <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                                        Model yang dipilih akan langsung digunakan oleh agen riset otonom, modul novelty check, gap finder, dan critique.
                                    </p>
                                </div>
                            </div>
                            
                            {/* Modal Footer */}
                            <div className="p-5 bg-white/[0.01] border-t border-white/5 flex items-center justify-between">
                                {success ? (
                                    <span className="text-xs text-green-400 flex items-center gap-1.5 font-medium animate-pulse">
                                        <CheckCircle2 size={12} /> Model berhasil diperbarui!
                                    </span>
                                ) : <span />}
                                
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setShowSettings(false)}
                                        className="px-3.5 py-1.5 text-xs font-semibold text-gray-400 hover:text-white rounded-lg transition-colors"
                                    >
                                        Batal
                                    </button>
                                    <button
                                        onClick={handleSave}
                                        disabled={saving || loading}
                                        className="px-4 py-1.5 text-xs font-bold text-black bg-yellow-400 hover:bg-yellow-300 disabled:opacity-40 rounded-lg transition-all"
                                    >
                                        {saving ? 'Menyimpan...' : 'Simpan'}
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </aside>
    );
}
