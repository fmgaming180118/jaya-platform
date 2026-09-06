import { useState } from 'react';
import { Link, NavLink } from '../routing/router';
import {
    MessageSquare, Library, Network, BookOpen, Activity,
    ChevronLeft, Settings, Code2, FlaskConical, X, RotateCw,
    CheckCircle2, Sparkles, Cpu
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
                'flex items-center gap-3 px-3.5 py-2.5 rounded-xl transition-all duration-200 group mx-2 relative overflow-hidden',
                isActive
                    ? 'bg-gradient-to-r from-blue-600/20 via-indigo-600/15 to-purple-600/20 text-white font-medium shadow-md border border-blue-500/30'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
            )}
        >
            {({ isActive }) => (
                <>
                    {isActive && (
                        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-gradient-to-b from-blue-400 to-indigo-500 rounded-r-full shadow-glow" />
                    )}
                    <div className={clsx(
                        'w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200',
                        isActive
                            ? 'bg-blue-500/20 text-blue-300 shadow-inner'
                            : 'text-slate-500 group-hover:text-slate-300 group-hover:bg-white/5'
                    )}>
                        <Icon size={18} />
                    </div>
                    <span className="text-sm tracking-tight flex-1 font-medium">{label}</span>
                    {devOnly && (
                        <span className="text-[9px] font-bold text-amber-400/80 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded-full uppercase tracking-wider">DEV</span>
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

    const handleOpenSettings = () => {
        setShowSettings(true);
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
    };

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
        <aside className="w-[260px] h-full bg-[#0b0d14]/90 backdrop-blur-xl border-r border-white/5 flex flex-col py-5 shrink-0 z-20 shadow-2xl">

            {/* Logo & Workspace Brand */}
            <div className="px-4 mb-4">
                <Link
                    to="/"
                    className="flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors mb-3 px-2 group"
                >
                    <ChevronLeft size={15} className="group-hover:-translate-x-1 transition-transform" />
                    <span className="text-xs font-medium tracking-wide">Semua Proyek</span>
                </Link>

                <div className="px-2.5 py-3 rounded-2xl bg-gradient-to-b from-white/5 to-white/[0.02] border border-white/10 shadow-inner">
                    <div className="flex items-center gap-2.5 mb-1">
                        <div className="w-6 h-6 rounded-lg bg-blue-500/20 border border-blue-400/30 flex items-center justify-center text-blue-400 shadow-glow">
                            <Sparkles size={13} />
                        </div>
                        <h2 className="text-sm font-bold text-slate-100 truncate tracking-tight">{workspaceId}</h2>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        <p className="text-[11px] font-medium text-slate-400">Workspace Aktif</p>
                    </div>
                </div>
            </div>

            {/* Divider */}
            <div className="mx-4 border-t border-white/5 mb-3" />

            {/* Navigation */}
            <nav className="space-y-1 flex-1 overflow-y-auto px-1">
                {/* Label Seksi */}
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-4 pt-1 pb-2">Menu Utama</p>

                <NavItem to={`${baseUrl}/chat`}     icon={MessageSquare} label="Knowledge Chat" />
                {features.recursiveResearch && (
                    <NavItem to={`${baseUrl}/research`} icon={Library} label="Deep Research" />
                )}
                {features.digitalTwin && (
                    <NavItem to={`${baseUrl}/evolution`} icon={Sparkles} label="Autonomous Discovery" />
                )}
                <NavItem to={`${baseUrl}/graph`}    icon={Network}       label="Knowledge Graph" />
                {features.thesisMode && (
                    <NavItem to={`${baseUrl}/thesis`} icon={BookOpen} label="Thesis Defense" />
                )}

                {/* Label Seksi DEV-ONLY */}
                {isDevMode && features.digitalTwin && (
                    <>
                        <p className="text-[10px] font-bold text-amber-400/70 uppercase tracking-widest px-4 pt-4 pb-2 flex items-center gap-1.5">
                            <Code2 size={11} /> Developer Only
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
                    onClick={handleOpenSettings}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-white/5 cursor-pointer transition-all duration-200 group border border-transparent hover:border-white/5"
                >
                    <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/5 flex items-center justify-center group-hover:bg-blue-500/20 group-hover:border-blue-500/30 text-slate-400 group-hover:text-blue-300 transition-all">
                        <Settings size={15} />
                    </div>
                    <span className="text-xs font-medium">Pengaturan Model</span>
                </div>
            </div>

            {/* Settings Modal */}
            <AnimatePresence>
                {showSettings && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 10 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 10 }}
                            className="bg-[#121520] border border-white/10 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl text-left"
                        >
                            {/* Modal Header */}
                            <div className="p-5 border-b border-white/5 flex items-center justify-between bg-white/[0.02]">
                                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                                    <Cpu size={16} className="text-blue-400" />
                                    Pengaturan Model NVIDIA NIM
                                </h3>
                                <button
                                    onClick={() => setShowSettings(false)}
                                    className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors"
                                >
                                    <X size={16} />
                                </button>
                            </div>

                            {/* Modal Body */}
                            <div className="p-5 space-y-4">
                                {loading ? (
                                    <div className="flex items-center justify-center py-8 text-slate-400 text-xs gap-2">
                                        <RotateCw size={16} className="animate-spin text-blue-400" />
                                        <span>Memuat daftar model...</span>
                                    </div>
                                ) : (
                                    <div>
                                        <label className="block text-xs font-semibold text-slate-300 mb-2">
                                            Pilih Model Active (LLM / Reasoning):
                                        </label>
                                        <select
                                            value={activeModel}
                                            onChange={(e) => setActiveModel(e.target.value)}
                                            className="w-full bg-[#1a1e2d] border border-white/10 rounded-xl px-3 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500/50 transition-colors"
                                        >
                                            {models.map(m => (
                                                <option key={m} value={m}>{m}</option>
                                            ))}
                                        </select>
                                        <p className="text-[11px] text-slate-500 mt-2">
                                            Model terpilih akan digunakan oleh seluruh modul penalaran JAYA RESEARCH & CORE.
                                        </p>
                                    </div>
                                )}
                            </div>

                            {/* Modal Footer */}
                            <div className="p-4 border-t border-white/5 bg-white/[0.02] flex items-center justify-end gap-2">
                                <button
                                    onClick={() => setShowSettings(false)}
                                    className="px-4 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
                                >
                                    Batal
                                </button>
                                <button
                                    onClick={handleSave}
                                    disabled={saving || loading}
                                    className="px-4 py-2 rounded-xl text-xs font-medium bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg transition-all flex items-center gap-1.5 disabled:opacity-50"
                                >
                                    {saving ? <RotateCw size={13} className="animate-spin" /> : success ? <CheckCircle2 size={13} className="text-emerald-300" /> : null}
                                    <span>{success ? 'Tersimpan!' : saving ? 'Menyimpan...' : 'Simpan Perubahan'}</span>
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </aside>
    );
}
