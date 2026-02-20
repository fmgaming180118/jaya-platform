import React from 'react';
import { Outlet, useParams } from 'react-router-dom';
import Sidebar from '../components/Sidebar';

export default function ProjectLayout() {
    // Get projectId from URL (mapped to workspaceId logic)
    const { projectId } = useParams();

    // Pass projectId as workspaceId to Sidebar and Context
    return (
        <div className="flex h-screen bg-notebook-bg text-notebook-text-primary overflow-hidden font-sans">
            {/* Sidebar now strictly scoped to projectId */}
            <Sidebar workspaceId={projectId} />

            {/* Main Content Area */}
            <main className="flex-1 overflow-hidden relative flex flex-col">
                <Outlet context={{ workspaceId: projectId }} />
            </main>
        </div>
    );
}
