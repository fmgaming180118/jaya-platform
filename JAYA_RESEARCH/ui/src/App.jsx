import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ProjectLayout from './layouts/ProjectLayout';
import ProjectListPage from './pages/ProjectListPage';
import ChatPage from './pages/ChatPage';
import ResearchPage from './pages/ResearchPage';
import GraphPage from './pages/GraphPage';
import EvolutionPage from './pages/EvolutionPage';
import ThesisPage from './pages/ThesisPage';

function App() {
    return (
        <BrowserRouter>
            <Routes>
                {/* Landing Page: List Projects */}
                <Route path="/" element={<ProjectListPage />} />

                {/* Project Context: All routes under /project/:projectId */}
                <Route path="/project/:projectId" element={<ProjectLayout />}>
                    <Route index element={<Navigate to="chat" replace />} />
                    <Route path="chat" element={<ChatPageWrapper />} />
                    <Route path="research" element={<ResearchPageWrapper />} />
                    <Route path="graph" element={<GraphPageWrapper />} />
                    <Route path="thesis" element={<ThesisPageWrapper />} />
                    <Route path="evolution" element={<EvolutionPageWrapper />} />
                </Route>
            </Routes>
        </BrowserRouter>
    );
}

// Wrappers to extract workspaceId from context (provided by ProjectLayout outlet context)
// But wait, ProjectLayout uses <Outlet context={{ workspaceId }} />.
// The child components need to use useOutletContext().
// However, the existing components take `workspaceId` as a prop.
// So we need small wrappers here.

import { useOutletContext } from 'react-router-dom';

const ChatPageWrapper = () => { const { workspaceId } = useOutletContext(); return <ChatPage key={workspaceId} workspaceId={workspaceId} />; };
const ResearchPageWrapper = () => { const { workspaceId } = useOutletContext(); return <ResearchPage key={workspaceId} workspaceId={workspaceId} />; };
const GraphPageWrapper = () => { const { workspaceId } = useOutletContext(); return <GraphPage key={workspaceId} workspaceId={workspaceId} />; };
// EvolutionPage might currently treat DigitalTwin as global, but let's pass workspaceId anyway for future proofing
const EvolutionPageWrapper = () => { const { workspaceId } = useOutletContext(); return <EvolutionPage key={workspaceId} workspaceId={workspaceId} />; };
const ThesisPageWrapper = () => { const { workspaceId } = useOutletContext(); return <ThesisPage key={workspaceId} workspaceId={workspaceId} />; };

export default App;
