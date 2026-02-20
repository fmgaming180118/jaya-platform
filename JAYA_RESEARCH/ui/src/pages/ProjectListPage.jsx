import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Folder, Clock, MoreVertical, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';
import api from '../services/api';

export default function ProjectListPage() {
    const navigate = useNavigate();
    const [projects, setProjects] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');

    useEffect(() => {
        loadProjects();
    }, []);

    const loadProjects = async () => {
        try {
            setIsLoading(true);
            const data = await api.listWorkspaces();
            // Ensure data is array
            const projectList = Array.isArray(data) ? data : (data.workspaces || []);
            setProjects(projectList);
        } catch (error) {
            console.error("Failed to load projects:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleCreateProject = async (e) => {
        e.preventDefault();
        if (!newProjectName.trim()) return;

        try {
            const res = await api.createWorkspace(newProjectName);
            // Assuming res returns the created workspace or status
            // Reload list
            await loadProjects();
            setShowCreateModal(false);
            setNewProjectName('');

            // Optionally navigate directly to new project
            // if (res.workspace_id) navigate(`/project/${res.workspace_id}/chat`);
        } catch (error) {
            console.error("Failed to create project:", error);
        }
    };

    const openProject = (projectId) => {
        navigate(`/project/${projectId}/chat`);
    };

    return (
        <div className="min-h-screen bg-notebook-bg text-notebook-text-primary p-8 font-sans">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="flex justify-between items-end mb-12">
                    <div>
                        <h1 className="text-4xl font-bold tracking-tight mb-2 bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">JAYA Research</h1>
                        <p className="text-notebook-text-secondary text-lg">Select a project to begin your research.</p>
                    </div>
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="flex items-center gap-2 px-5 py-3 bg-notebook-text-primary text-notebook-bg font-semibold rounded-full hover:bg-white transition-all shadow-lg hover:shadow-xl transform hover:-translate-y-0.5"
                    >
                        <Plus size={20} />
                        <span>New Project</span>
                    </button>
                </div>

                {/* Grid */}
                {isLoading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="h-48 rounded-2xl bg-notebook-card/50 animate-pulse" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {/* Create New Card (Alternative access) */}
                        <motion.div
                            whileHover={{ y: -4 }}
                            onClick={() => setShowCreateModal(true)}
                            className="h-56 rounded-2xl border-2 border-dashed border-notebook-border hover:border-notebook-text-accent/50 flex flex-col items-center justify-center cursor-pointer group transition-colors bg-white/5 hover:bg-white/10"
                        >
                            <div className="w-12 h-12 rounded-full bg-notebook-bg flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Plus size={24} className="text-notebook-text-secondary group-hover:text-notebook-text-accent" />
                            </div>
                            <span className="font-medium text-notebook-text-secondary group-hover:text-notebook-text-primary">Create new project</span>
                        </motion.div>

                        {/* Project Cards */}
                        {projects.map((project) => (
                            <motion.div
                                key={project.id || project.name}
                                whileHover={{ y: -4 }}
                                onClick={() => openProject(project.id || project.name)}
                                className="h-56 p-6 rounded-2xl bg-notebook-card border border-notebook-border hover:border-notebook-text-accent/30 cursor-pointer flex flex-col justify-between group shadow-sm hover:shadow-md transition-all relative overflow-hidden"
                            >
                                <div className="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button className="p-2 hover:bg-notebook-hover rounded-full text-notebook-text-secondary hover:text-notebook-text-primary">
                                        <ArrowRight size={18} />
                                    </button>
                                </div>

                                <div>
                                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center text-blue-400 mb-4">
                                        <Folder size={20} />
                                    </div>
                                    <h3 className="text-xl font-semibold text-notebook-text-primary mb-1 truncate">{project.name || project}</h3>
                                    <p className="text-sm text-notebook-text-secondary line-clamp-2">
                                        {project.description || "Project workspace"}
                                    </p>
                                </div>

                                <div className="flex items-center gap-2 text-xs text-notebook-text-secondary font-medium">
                                    <Clock size={12} />
                                    <span>{project.created_at ? new Date(project.created_at).toLocaleDateString() : "Recently"}</span>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                )}
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <motion.div
                        initial={{ scale: 0.9, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        className="bg-notebook-card w-full max-w-md rounded-2xl border border-notebook-border p-6 shadow-2xl"
                    >
                        <h2 className="text-xl font-semibold mb-4">Create New Project</h2>
                        <form onSubmit={handleCreateProject}>
                            <div className="mb-6">
                                <label className="block text-sm font-medium text-notebook-text-secondary mb-2">Project Name</label>
                                <input
                                    type="text"
                                    value={newProjectName}
                                    onChange={(e) => setNewProjectName(e.target.value)}
                                    placeholder="e.g., Quantum Computing Research"
                                    className="w-full bg-notebook-bg border border-notebook-border rounded-xl px-4 py-3 text-notebook-text-primary focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                                    autoFocus
                                />
                            </div>
                            <div className="flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setShowCreateModal(false)}
                                    className="px-4 py-2 rounded-lg hover:bg-notebook-hover text-notebook-text-secondary transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={!newProjectName.trim()}
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    Create Project
                                </button>
                            </div>
                        </form>
                    </motion.div>
                </div>
            )}
        </div>
    );
}
