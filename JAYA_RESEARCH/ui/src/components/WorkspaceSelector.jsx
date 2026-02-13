import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

const WorkspaceSelector = ({ currentWorkspace, onWorkspaceChange }) => {
    const [workspaces, setWorkspaces] = useState([]);
    const [newWorkspaceName, setNewWorkspaceName] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    useEffect(() => {
        loadWorkspaces();
    }, []);

    const loadWorkspaces = async () => {
        try {
            const list = await api.listWorkspaces();
            setWorkspaces(list);
        } catch (error) {
            console.error("Failed to list workspaces", error);
        }
    };

    const handleCreate = async () => {
        if (!newWorkspaceName.trim()) return;
        try {
            const res = await api.createWorkspace(newWorkspaceName);
            if (res.status !== 'error') {
                await loadWorkspaces();
                setNewWorkspaceName('');
                setIsCreating(false);
                // Switch to new workspace
                if (res.id) onWorkspaceChange(res.id);
            }
        } catch (error) {
            console.error("Failed to create workspace", error);
        }
    };

    return (
        <div className="workspace-selector p-4 bg-gray-900 border-b border-gray-800">
            <div className="flex items-center justify-between mb-2">
                <h3 className="text-gray-400 text-xs uppercase font-bold tracking-wider">Active Room</h3>
                <button
                    onClick={() => setIsCreating(!isCreating)}
                    className="text-cyan-400 hover:text-cyan-300 text-xs"
                >
                    {isCreating ? 'Cancel' : '+ New Room'}
                </button>
            </div>

            {isCreating && (
                <div className="mb-3 flex gap-2">
                    <input
                        type="text"
                        value={newWorkspaceName}
                        onChange={(e) => setNewWorkspaceName(e.target.value)}
                        placeholder="Room Name..."
                        className="bg-gray-800 text-white text-sm px-2 py-1 rounded border border-gray-700 w-full focus:outline-none focus:border-cyan-500"
                        onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                    />
                    <button
                        onClick={handleCreate}
                        className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs"
                    >
                        Add
                    </button>
                </div>
            )}

            <select
                value={currentWorkspace}
                onChange={(e) => onWorkspaceChange(e.target.value)}
                className="w-full bg-gray-800 text-white text-sm px-3 py-2 rounded border border-gray-700 focus:outline-none focus:border-cyan-500"
            >
                {workspaces.map((ws) => (
                    <option key={ws.id || ws.name} value={ws.id || ws.name}>
                        {ws.name}
                    </option>
                ))}
            </select>

            <div className="mt-1 text-xs text-gray-500">
                ID: <span className="font-mono">{currentWorkspace}</span>
            </div>
        </div>
    );
};

export default WorkspaceSelector;
