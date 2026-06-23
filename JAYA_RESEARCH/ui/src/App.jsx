import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useOutletContext } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import ProjectLayout from './layouts/ProjectLayout';
import ProjectListPage from './pages/ProjectListPage';
import ChatPage from './pages/ChatPage';
import ResearchPage from './pages/ResearchPage';
import GraphPage from './pages/GraphPage';
import EvolutionPage from './pages/EvolutionPage';
import ThesisPage from './pages/ThesisPage';

// Page wrappers — extract workspaceId from ProjectLayout outlet context
const ChatPageWrapper     = () => { const { workspaceId } = useOutletContext(); return <ChatPage     key={workspaceId} workspaceId={workspaceId} />; };
const ResearchPageWrapper = () => { const { workspaceId } = useOutletContext(); return <ResearchPage key={workspaceId} workspaceId={workspaceId} />; };
const GraphPageWrapper    = () => { const { workspaceId } = useOutletContext(); return <GraphPage    key={workspaceId} workspaceId={workspaceId} />; };
const EvolutionPageWrapper= () => { const { workspaceId } = useOutletContext(); return <EvolutionPage key={workspaceId} workspaceId={workspaceId} />; };
const ThesisPageWrapper   = () => { const { workspaceId } = useOutletContext(); return <ThesisPage   key={workspaceId} workspaceId={workspaceId} />; };

function App() {
    return (
        // AppProvider membungkus seluruh aplikasi agar context tersedia di mana saja
        <AppProvider>
            <BrowserRouter>
                <Routes>
                    {/* Landing Page: List Projects */}
                    <Route path="/" element={<ProjectListPage />} />

                    {/* Project Context: semua rute di bawah /project/:projectId */}
                    <Route path="/project/:projectId" element={<ProjectLayout />}>
                        <Route index element={<Navigate to="chat" replace />} />
                        <Route path="chat"     element={<ChatPageWrapper />} />
                        <Route path="research" element={<ResearchPageWrapper />} />
                        <Route path="graph"    element={<GraphPageWrapper />} />
                        <Route path="thesis"   element={<ThesisPageWrapper />} />
                        <Route path="evolution" element={<EvolutionPageWrapper />} />
                    </Route>
                </Routes>
            </BrowserRouter>
        </AppProvider>
    );
}

export default App;
