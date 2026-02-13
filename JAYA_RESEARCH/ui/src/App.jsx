import { useState, useEffect } from 'react';
import WorkspaceSelector from './components/WorkspaceSelector';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import ResearchPage from './pages/ResearchPage';
import GraphPage from './pages/GraphPage';
import EvolutionPage from './pages/EvolutionPage';
import ThesisPage from './pages/ThesisPage';

function App() {
    const [activeTab, setActiveTab] = useState('chat');
    // Load from localStorage or default
    const [workspaceId, setWorkspaceId] = useState(() => localStorage.getItem('JAYA_LAST_WORKSPACE') || 'default');

    // Save to localStorage whenever it changes
    useEffect(() => {
        localStorage.setItem('JAYA_LAST_WORKSPACE', workspaceId);
    }, [workspaceId]);

    return (
        <div className="flex bg-gray-900 text-white min-h-screen">
            {/* Sidebar */}
            <aside className="w-64 bg-black border-r border-gray-800 flex flex-col">
                <div className="p-4 border-b border-gray-800">
                    <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-500 bg-clip-text text-transparent">
                        JAYA Research
                    </h1>
                    <div className="text-xs text-gray-500 mt-1">Autonomous Knowledge Engine</div>
                </div>

                {/* Workspace Selector */}
                <WorkspaceSelector
                    currentWorkspace={workspaceId}
                    onWorkspaceChange={setWorkspaceId}
                />

                <nav className="flex-1 p-4 space-y-2">
                    <button
                        onClick={() => setActiveTab('chat')}
                        className={`w-full text-left px-4 py-3 rounded-lg flex items-center space-x-3 transition-colors ${activeTab === 'chat' ? 'bg-cyan-900/30 text-cyan-400 border border-cyan-800' : 'hover:bg-gray-800 text-gray-400'
                            }`}
                    >
                        <span>💬</span>
                        <span>Knowledge Chat</span>
                    </button>

                    <button
                        onClick={() => setActiveTab('research')}
                        className={`w-full text-left px-4 py-3 rounded-lg flex items-center space-x-3 transition-colors ${activeTab === 'research' ? 'bg-purple-900/30 text-purple-400 border border-purple-800' : 'hover:bg-gray-800 text-gray-400'
                            }`}
                    >
                        <span>🧪</span>
                        <span>Deep Research</span>
                    </button>

                    <button
                        onClick={() => setActiveTab('graph')}
                        className={`w-full text-left px-4 py-3 rounded-lg flex items-center space-x-3 transition-colors ${activeTab === 'graph' ? 'bg-green-900/30 text-green-400 border border-green-800' : 'hover:bg-gray-800 text-gray-400'
                            }`}
                    >
                        <span>🕸️</span>
                        <span>Knowledge Graph</span>
                    </button>

                    <button
                        onClick={() => setActiveTab('evolution')}
                        className={`w-full text-left px-4 py-3 rounded-lg flex items-center space-x-3 transition-colors ${activeTab === 'evolution' ? 'bg-pink-900/30 text-pink-400 border border-pink-800' : 'hover:bg-gray-800 text-gray-400'
                            }`}
                    >
                        <span>🧬</span>
                        <span>Digital Twin</span>
                    </button>
                </nav>

                <div className="p-4 border-t border-gray-800">
                    <div className="flex items-center space-x-2 text-xs text-gray-600">
                        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                        <span>System Online • v1.0</span>
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 overflow-hidden relative">
                {activeTab === 'chat' && <ChatPage workspaceId={workspaceId} />}
                {activeTab === 'research' && <ResearchPage workspaceId={workspaceId} />}
                {activeTab === 'graph' && <GraphPage workspaceId={workspaceId} />}
                {activeTab === 'evolution' && <EvolutionPage />}
                {activeTab === 'thesis' && <ThesisPage />}
            </main>
        </div>
    );
}

export default App;
