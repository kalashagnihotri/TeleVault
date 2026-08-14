import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Download, RefreshCw, AlertTriangle } from 'lucide-react';

export const Dashboard: React.FC = () => {
    const [system, setSystem] = useState<any>(null);
    const [dashboard, setDashboard] = useState<any>(null);
    const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

    const fetchData = async () => {
        try {
            const sys = await api.getSystem();
            const dash = await api.getDashboard();
            setSystem(sys);
            setDashboard(dash);
            setLastRefreshed(new Date());
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000); // 10s auto refresh
        return () => clearInterval(interval);
    }, []);

    const handleExport = async () => {
        try {
            const res = await fetch('/api/system/diagnostic_report');
            const data = await res.json();
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `control_center_diagnostics_${new Date().getTime()}.json`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            console.error(e);
        }
    };

    if (!system || !dashboard) return <div className="main-content">Loading dashboard...</div>;

    const venvWarning = system.python.executable && !system.python.executable.includes('.venv');

    return (
        <div className="main-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2>Dashboard</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    {venvWarning && (
                        <div style={{ color: 'var(--warn-color)', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}>
                            <AlertTriangle size={14} /> Control Center is not running from the project virtual environment.
                        </div>
                    )}
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        Last refreshed: {lastRefreshed?.toLocaleTimeString()}
                    </span>
                    <button className="btn" onClick={fetchData} title="Refresh">
                        <RefreshCw size={12} />
                    </button>
                    <button className="btn" onClick={handleExport} title="Export Diagnostic Report">
                        <Download size={12} /> Export Diagnostics
                    </button>
                </div>
            </div>
            
            <div className="grid">
                <div className="card">
                    <h3>Archive Status</h3>
                    <div className="stat-row">
                        <span className="stat-label">Backed Up</span>
                        <span className="stat-value">{dashboard.archive.backed_up}</span>
                    </div>
                    <div className="stat-row">
                        <span className="stat-label">Ready for Upload</span>
                        <span className="stat-value">{dashboard.archive.ready}</span>
                    </div>
                    <div className="stat-row">
                        <span className="stat-label">Failed Analysis</span>
                        <span className="stat-value">{dashboard.archive.failed}</span>
                    </div>
                </div>
                
                <div className="card">
                    <h3>Queue Overview</h3>
                    <div className="stat-row">
                        <span className="stat-label">Incoming Images</span>
                        <span className="stat-value">{dashboard.queue.incoming_images}</span>
                    </div>
                    <div className="stat-row">
                        <span className="stat-label">Incoming Videos</span>
                        <span className="stat-value">{dashboard.queue.incoming_videos}</span>
                    </div>
                </div>

                <div className="card">
                    <h3>System Health</h3>
                    <div className="stat-row">
                        <span className="stat-label">Database Integrity</span>
                        <span className="stat-value">
                            <span className={`status-indicator`}><span className={`dot ${system.archive_db.readable ? 'green' : 'red'}`}></span> {system.archive_db.readable ? 'OK' : 'Error'}</span>
                        </span>
                    </div>
                    <div className="stat-row">
                        <span className="stat-label">Python Backend</span>
                        <span className="stat-value">v{system.python.version}</span>
                    </div>
                    <div className="stat-row">
                        <span className="stat-label">Migration Version</span>
                        <span className="stat-value">{system.archive_db.latest_migration}</span>
                    </div>
                </div>

                <div className="card">
                    <h3>AI Intelligence</h3>
                    <div className="stat-row">
                        <span className="stat-label">Face Models</span>
                        <span className="stat-value">
                             <span className={`status-indicator`}><span className={`dot ${system.faces.models_present ? 'green' : 'red'}`}></span> {system.faces.models_present ? 'Loaded' : 'Missing'}</span>
                        </span>
                    </div>
                    <div className="stat-row">
                        <span className="stat-label">Face Calibration</span>
                        <span className="stat-value">{system.faces.calibration_status}</span>
                    </div>
                    <div className="stat-row">
                        <span className="stat-label">Scene Model</span>
                        <span className="stat-value">
                            <span className={`status-indicator`}><span className={`dot ${system.scenes.model_present ? 'green' : 'red'}`}></span> {system.scenes.model_present ? 'Loaded' : 'Missing'}</span>
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
};
