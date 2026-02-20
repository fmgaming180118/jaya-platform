import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Plus, ChevronDown, Check } from 'lucide-react';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';

const WorkspaceSelector = ({ currentWorkspace, onWorkspaceChange }) => {
    const [workspaces, setWorkspaces] = useState([]);
    const [newWorkspaceName, setNewWorkspaceName] = useState('');
    const [isCreating, setIsCreating] = useState(false);
    const [isOpen, setIsOpen] = useState(false);

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
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between px-3 py-2 bg-notebook-card hover:bg-notebook-hover border border-notebook-border rounded-lg text-notebook-text-primary text-sm font-medium transition-colors"
            >
                <span className="truncate">{currentWorkspace || "Select Workspace"}</span>
                <ChevronDown size={14} className={clsx("text-notebook-text-secondary transition-transform", isOpen && "rotate-180")} />
            </button>

            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="absolute top-full left-0 right-0 mt-2 bg-notebook-card border border-notebook-border rounded-xl shadow-xl overflow-hidden z-50 p-2"
                    >

                        <div className="max-h-48 overflow-y-auto mb-2 custom-scrollbar">
                            <div className="px-2 py-1 text-[10px] font-bold text-notebook-text-secondary uppercase tracking-wider">Your Workspaces</div>
                            {workspaces.map((ws) => (
                                <button
                                    key={ws.id || ws.name}
                                    onClick={() => {
                                        onWorkspaceChange(ws.id || ws.name);
                                        setIsOpen(false);
                                    }}
                                    className={clsx(
                                        "w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm text-left transition-colors",
                                        (ws.id || ws.name) === currentWorkspace
                                            ? "bg-notebook-text-accent/10 text-notebook-text-accent"
                                            : "text-notebook-text-primary hover:bg-notebook-hover"
                                    )}
                                >
                                    <span className="truncate">{ws.name}</span>
                                    {(ws.id || ws.name) === currentWorkspace && <Check size={14} />}
                                </button>
                            ))}
                        </div>

                        <div className="border-t border-notebook-border pt-2">
                            {isCreating ? (
                                <div className="space-y-2 px-1">
                                    <input
                                        type="text"
                                        value={newWorkspaceName}
                                        autoFocus
                                        onChange={(e) => setNewWorkspaceName(e.target.value)}
                                        placeholder="Name..."
                                        className="w-full bg-notebook-bg text-notebook-text-primary text-xs px-2 py-1.5 rounded border border-notebook-border focus:border-notebook-text-accent focus:outline-none"
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') handleCreate();
                                            if (e.key === 'Escape') setIsCreating(false);
                                        }}
                                    />
                                    <div className="flex gap-2">
                                        <button
                                            onClick={handleCreate}
                                            className="flex-1 bg-notebook-text-accent text-notebook-bg text-xs font-bold py-1 rounded hover:bg-white transition-colors"
                                        >
                                            Create
                                        </button>
                                        <button
                                            onClick={() => setIsCreating(false)}
                                            className="px-2 text-notebook-text-secondary hover:text-notebook-text-primary text-xs transition-colors"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <button
                                    onClick={() => setIsCreating(true)}
                                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-notebook-text-secondary hover:text-notebook-text-primary hover:bg-notebook-hover text-xs transition-colors"
                                >
                                    <Plus size={14} />
                                    <span>Create New Workspace</span>
                                </button>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default WorkspaceSelector;
