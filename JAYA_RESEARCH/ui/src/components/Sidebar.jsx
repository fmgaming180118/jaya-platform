import { NavLink, Link } from 'react-router-dom';
import { MessageSquare, Library, Network, BookOpen, Activity, ChevronLeft, Settings } from 'lucide-react';
import clsx from 'clsx';

const NavItem = ({ to, icon: Icon, label }) => (
    <NavLink
        to={to}
        className={({ isActive }) => clsx(
            "flex items-center gap-3 px-4 py-3 rounded-full transition-all duration-200 group mx-2",
            "hover:bg-notebook-hover",
            isActive ? "bg-[#282a2f] text-notebook-text-accent font-medium" : "text-notebook-text-secondary"
        )}
    >
        {({ isActive }) => (
            <>
                <Icon size={20} className={clsx("transition-colors", isActive ? "text-notebook-text-accent" : "group-hover:text-notebook-text-primary")} />
                <span className="text-sm tracking-wide">{label}</span>
            </>
        )}
    </NavLink>
);

export default function Sidebar({ workspaceId, setWorkspaceId }) {
    // Note: setWorkspaceId is no longer needed in ProjectLayout mode, 
    // but kept for compatibility if needed. routing is driven by URL now.

    const baseUrl = `/project/${workspaceId}`;

    return (
        <aside className="w-[280px] h-full bg-notebook-sidebar border-r border-notebook-border flex flex-col py-6">
            {/* Header / Back to Projects */}
            <div className="px-4 mb-6">
                <Link
                    to="/"
                    className="flex items-center gap-2 text-notebook-text-secondary hover:text-notebook-text-primary transition-colors mb-4 px-2"
                >
                    <ChevronLeft size={16} />
                    <span className="text-sm font-medium">All Projects</span>
                </Link>

                <div className="px-2">
                    <h2 className="text-lg font-bold text-notebook-text-primary truncate">{workspaceId}</h2>
                    <p className="text-xs text-notebook-text-secondary">Project Workspace</p>
                </div>
            </div>

            {/* Navigation */}
            <nav className="space-y-1 flex-1 px-2">
                <NavItem to={`${baseUrl}/chat`} icon={MessageSquare} label="Knowledge Chat" />
                <NavItem to={`${baseUrl}/research`} icon={Library} label="Deep Research" />
                <NavItem to={`${baseUrl}/graph`} icon={Network} label="Knowledge Graph" />
                <NavItem to={`${baseUrl}/thesis`} icon={BookOpen} label="Thesis Defense" />
                <NavItem to={`${baseUrl}/evolution`} icon={Activity} label="Digital Twin" />
            </nav>

            {/* Footer */}
            <div className="mt-auto px-4 pt-4 border-t border-notebook-border">
                <div className="flex items-center gap-3 px-2 py-2 text-notebook-text-secondary hover:text-notebook-text-primary cursor-pointer transition-colors">
                    <div className="w-8 h-8 rounded-full bg-notebook-card border border-notebook-border flex items-center justify-center">
                        <Settings size={16} />
                    </div>
                    <span className="text-sm">Settings</span>
                </div>
            </div>
        </aside>
    );
}
