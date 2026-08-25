import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { TerminalPanel } from './components/TerminalPanel';
import { Dashboard } from './pages/Dashboard';
import { RunCenter } from './pages/RunCenter';
import { Jobs } from './pages/Jobs';
import { QueueIngest } from './pages/QueueIngest';
import { Archive } from './pages/Archive';
import { ConfigCenter } from './pages/ConfigCenter';
import { ModelCenter } from './pages/ModelCenter';
import { Maintenance } from './pages/Maintenance';
import { JobProvider } from './contexts/JobContext';

function AppContent() {
    return (
        <div className="layout">
            <Sidebar />
            <div className="main-wrapper">
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/run" element={<RunCenter />} />
                    <Route path="/test" element={<RunCenter />} />
                    <Route path="/jobs" element={<Jobs />} />
                    <Route path="/queue" element={<QueueIngest />} />
                    <Route path="/archive" element={<Archive />} />
                    <Route path="/config" element={<ConfigCenter />} />
                    <Route path="/models" element={<ModelCenter />} />
                    <Route path="/maintenance" element={<Maintenance />} />
                </Routes>
                <TerminalPanel />
            </div>
        </div>
    );
}

function App() {
    return (
        <BrowserRouter>
            <JobProvider>
                <AppContent />
            </JobProvider>
        </BrowserRouter>
    );
}

export default App;
