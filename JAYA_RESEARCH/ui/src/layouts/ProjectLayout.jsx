import React from 'react';
import { Outlet, useParams } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import DevBanner from '../components/DevBanner';
import DevPanel from '../components/DevPanel';
import { useApp } from '../context/AppContext';
import { Terminal } from 'lucide-react';
import { useEffect } from 'react';
import { setApiLogCallback } from '../services/api';

export default function ProjectLayout() {
    const { projectId } = useParams();
    const { isDevMode, canShowDevPanel, toggleDevPanel, addApiLog } = useApp();

    // Wire API log callback saat mount
    useEffect(() => {
        if (isDevMode) setApiLogCallback(addApiLog);
        return () => setApiLogCallback(null);
    }, [isDevMode, addApiLog]);

    return (
        <div className="flex flex-col h-screen bg-notebook-bg text-notebook-text-primary overflow-hidden font-sans">
            {/* Dev Banner — hanya tampil di mode DEV */}
            {isDevMode && <DevBanner />}

            {/* Main Layout Row */}
            <div className="flex flex-1 overflow-hidden">
                <Sidebar workspaceId={projectId} />

                {/* Main Content Area */}
                <main className="flex-1 overflow-hidden relative flex flex-col">
                    <Outlet context={{ workspaceId: projectId }} />
                </main>
            </div>

            {/* Dev Panel Slideout (hanya DEV) */}
            {canShowDevPanel && (
                <>
                    <DevPanel />
                    {/* FAB Toggle Button */}
                    <button
                        onClick={toggleDevPanel}
                        title="Buka Developer Panel (DEV only)"
                        className="fixed bottom-6 right-6 z-30 w-10 h-10 rounded-full bg-amber-500/20 hover:bg-amber-500/40 border border-amber-500/40 hover:border-amber-500/70 text-amber-400 flex items-center justify-center shadow-lg transition-all duration-200 hover:scale-110"
                    >
                        <Terminal size={16} />
                    </button>
                </>
            )}
        </div>
    );
}
