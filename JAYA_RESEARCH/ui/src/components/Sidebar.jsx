import { NavLink, Link } from 'react-router-dom';
import {
    MessageSquare, Library, Network, BookOpen, Activity,
    ChevronLeft, Settings, Code2, FlaskConical
} from 'lucide-react';
import clsx from 'clsx';
import { useApp } from '../context/AppContext';
import EnvironmentBadge from './EnvironmentBadge';

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
                <div className="flex items-center gap-3 px-2 py-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-white/5 cursor-pointer transition-colors group">
                    <div className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
                        <Settings size={14} />
                    </div>
                    <span className="text-sm">Pengaturan</span>
                </div>
            </div>
        </aside>
    );
}
