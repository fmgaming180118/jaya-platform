import { Layers, MessageSquare, LineChart, Brain, Settings } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import clsx from 'clsx';

const NavItem = ({ to, icon: Icon, label }) => (
    <NavLink
        to={to}
        className={({ isActive }) => clsx(
            "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200",
            "hover:bg-white/5",
            isActive ? "bg-primary text-white shadow-lg shadow-primary/25" : "text-gray-400"
        )}
    >
        <Icon size={20} />
        <span className="font-medium text-sm">{label}</span>
    </NavLink>
);

export default function Sidebar() {
    return (
        <div className="w-64 h-full bg-[var(--bg-sidebar)] border-r border-[var(--border)] flex flex-col p-4">
            <div className="flex items-center gap-3 px-2 mb-8 mt-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
                    <Brain className="text-white" size={18} />
                </div>
                <h1 className="font-bold text-lg tracking-tight">AI-Q Research</h1>
            </div>

            <nav className="space-y-1 flex-1">
                <NavItem to="/chat" icon={MessageSquare} label="Notebook Chat" />
                <NavItem to="/research" icon={Layers} label="Auto Research" />
                <NavItem to="/graph" icon={LineChart} label="Knowledge Graph" />
            </nav>

            <div className="mt-auto pt-4 border-t border-[var(--border)]">
                <NavItem to="/settings" icon={Settings} label="Settings" />
            </div>
        </div>
    );
}
