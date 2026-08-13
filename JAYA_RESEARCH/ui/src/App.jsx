import { lazy, Suspense } from 'react';
import { AppProvider } from './context/AppContext';
import ProjectLayout from './layouts/ProjectLayout';
import ApiCredentialGate from './components/ApiCredentialGate';
import { FEATURES } from './config/env';
import { parseAppPath } from './routing/contracts';
import { BrowserRouter, Link, usePathname } from './routing/router';

const ProjectListPage = lazy(() => import('./pages/ProjectListPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const ResearchPage = lazy(() => import('./pages/ResearchPage'));
const GraphPage = lazy(() => import('./pages/GraphPage'));
const EvolutionPage = lazy(() => import('./pages/EvolutionPage'));
const ThesisPage = lazy(() => import('./pages/ThesisPage'));

// Route modules are selected only after parseAppPath validates the workspace boundary.
const PROJECT_PAGES = {
    chat: ChatPage,
    research: ResearchPage,
    graph: GraphPage,
    evolution: EvolutionPage,
    thesis: ThesisPage,
};

function RoutedApp() {
    const route = parseAppPath(usePathname());
    if (route.kind === 'project-list') return <ProjectListPage />;
    if (
        route.kind === 'project'
        && (route.module !== 'evolution' || FEATURES.digitalTwin)
    ) {
        const Page = PROJECT_PAGES[route.module];
        return (
            <ProjectLayout workspaceId={route.workspaceId}>
                <Page key={`${route.workspaceId}-${route.module}`} workspaceId={route.workspaceId} />
            </ProjectLayout>
        );
    }
    return (
        <main className="min-h-screen bg-[#080a0f] text-slate-100 flex items-center justify-center p-6">
            <div className="text-center">
                <p className="text-sm font-bold">Halaman tidak ditemukan</p>
                <Link to="/" className="inline-block mt-3 text-xs text-sky-300 hover:text-sky-200">
                    Kembali ke daftar proyek
                </Link>
            </div>
        </main>
    );
}

function App() {
    return (
        // AppProvider membungkus seluruh aplikasi agar context tersedia di mana saja
        <AppProvider>
            <ApiCredentialGate>
                <BrowserRouter>
                    <Suspense fallback={(
                        <main className="min-h-screen bg-[#080a0f] text-slate-400 flex items-center justify-center text-sm">
                            Memuat modul JAYA...
                        </main>
                    )}>
                        <RoutedApp />
                    </Suspense>
                </BrowserRouter>
            </ApiCredentialGate>
        </AppProvider>
    );
}

export default App;
