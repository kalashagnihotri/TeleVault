import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, PlaySquare, FileTerminal, LayoutDashboard, Settings, Database, Inbox, ShieldCheck, AlertTriangle, Cpu, Wrench } from 'lucide-react';
import { useJobContext } from '../contexts/JobContext';
import { api } from '../services/api';

export const Sidebar: React.FC = () => {
    const { activeJob, connectionState, setTerminalExpanded, isTerminalExpanded } = useJobContext();
    const [durationStr, setDurationStr] = useState('');
    const [queueCount, setQueueCount] = useState<number | null>(null);
    const [systemMode, setSystemMode] = useState<'safe' | 'production'>('safe');
    const [showConfirmModal, setShowConfirmModal] = useState(false);
    const [unreadNotifs, setUnreadNotifs] = useState(0);

    const loadMode = () => {
        api.getSystemMode()
            .then(res => setSystemMode(res.mode === 'production' ? 'production' : 'safe'))
            .catch(() => setSystemMode('safe'));
    };

    const loadNotifications = () => {
        api.getNotifications()
            .then(notifs => {
                const unread = notifs.filter(n => !n.read).length;
                setUnreadNotifs(unread);
            })
            .catch(() => {});
    };

    useEffect(() => {
        loadMode();
        loadNotifications();
        const id = setInterval(() => {
            loadMode();
            loadNotifications();
        }, 5000);
        return () => clearInterval(id);
    }, []);

    const toggleMode = () => {
        if (systemMode === 'safe') {
            setShowConfirmModal(true);
        } else {
            api.setSystemMode('safe').then(() => setSystemMode('safe')).catch(console.error);
        }
    };

    const confirmProductionMode = () => {
        api.setSystemMode('production').then(() => {
            setSystemMode('production');
            setShowConfirmModal(false);
        }).catch(console.error);
    };

    useEffect(() => {
        if (!activeJob || connectionState !== 'LIVE') {
            setDurationStr('');
            return;
        }
        
        let startedAt = new Date(activeJob.started_at).getTime();
        const interval = setInterval(() => {
            const now = new Date().getTime();
            const diff = Math.floor((now - startedAt) / 1000);
            const m = Math.floor(diff / 60);
            const s = diff % 60;
            setDurationStr(`${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`);
        }, 1000);
        
        return () => clearInterval(interval);
    }, [activeJob?.id, connectionState]);

    useEffect(() => {
        const load = () => {
            api.getQueueStatus()
                .then(s => setQueueCount(s.images + s.videos))
                .catch(() => setQueueCount(null));
        };
        load();
        const id = setInterval(load, 10000);
        return () => clearInterval(id);
    }, []);

    return (
        <div className="sidebar">
            <div className="sidebar-header">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Telegram Media Vault</span>
                    <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 6px', borderRadius: '4px', backgroundColor: 'rgba(255,255,255,0.08)', color: 'var(--text-secondary)', letterSpacing: '0.04em' }}>
                        ADMIN
                    </span>
                </div>
                <div 
                    onClick={toggleMode}
                    style={{
                        cursor: 'pointer',
                        marginTop: '8px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '11px',
                        fontWeight: 700,
                        padding: '4px 8px',
                        borderRadius: '6px',
                        backgroundColor: systemMode === 'production' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.15)',
                        color: systemMode === 'production' ? '#f87171' : '#4ade80',
                        border: `1px solid ${systemMode === 'production' ? 'rgba(239, 68, 68, 0.4)' : 'rgba(34, 197, 94, 0.3)'}`,
                        transition: 'all 0.2s'
                    }}
                    title="Click to toggle Safe / Production mode"
                >
                    {systemMode === 'production' ? <AlertTriangle size={12} /> : <ShieldCheck size={12} />}
                    {systemMode === 'production' ? '🔴 PRODUCTION MODE' : '🟢 SAFE MODE'}
                </div>
            </div>
            
            <div className="sidebar-nav">
                <NavLink to="/" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
                    <LayoutDashboard className="nav-icon" /> Dashboard
                </NavLink>
                <NavLink to="/run" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
                    <PlaySquare className="nav-icon" /> Run Center
                </NavLink>
                <NavLink to="/test" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
                    <FileTerminal className="nav-icon" /> Test Lab
                </NavLink>
                <NavLink to="/jobs" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
                    <Activity className="nav-icon" /> Jobs
                </NavLink>
                <NavLink to="/queue" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Inbox className="nav-icon" /> Queue & Ingest
                    </span>
                    {queueCount !== null && queueCount > 0 && (
                        <span style={{ backgroundColor: 'var(--primary-color)', color: 'white', borderRadius: '999px', fontSize: '10px', fontWeight: 700, padding: '1px 7px', minWidth: '18px', textAlign: 'center' }}>
                            {queueCount}
                        </span>
                    )}
                </NavLink>
                <NavLink to="/archive" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
                    <Database className="nav-icon" /> Archive
                </NavLink>
                <NavLink to="/config" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
                    <Settings className="nav-icon" /> Config Center
                </NavLink>
                <NavLink to="/models" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
                    <Cpu className="nav-icon" /> AI Models
                </NavLink>
                <NavLink to="/maintenance" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Wrench className="nav-icon" /> Maintenance
                    </span>
                    {unreadNotifs > 0 && (
                        <span style={{ backgroundColor: '#eab308', color: 'black', borderRadius: '999px', fontSize: '10px', fontWeight: 700, padding: '1px 7px' }}>
                            {unreadNotifs}
                        </span>
                    )}
                </NavLink>
            </div>

            {/* Global Active Job Banner at bottom of sidebar */}
            <div 
                style={{
                    padding: '16px', 
                    borderTop: '1px solid var(--border-color)', 
                    backgroundColor: activeJob ? 'rgba(163, 113, 247, 0.1)' : 'transparent',
                    cursor: activeJob ? 'pointer' : 'default',
                    transition: '0.2s',
                    userSelect: 'none'
                }}
                onClick={() => {
                    if (activeJob) {
                        setTerminalExpanded(!isTerminalExpanded);
                    }
                }}
            >
                {activeJob ? (
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--running-color)', fontWeight: 600, fontSize: '11px' }}>
                                <span className={`dot`} style={{ backgroundColor: 'var(--running-color)' }}></span> 
                                RUNNING
                            </div>
                            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{durationStr}</span>
                        </div>
                        <div style={{ fontWeight: 500, fontSize: '13px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {activeJob.profile_id}
                        </div>
                    </div>
                ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '11px', fontWeight: 600 }}>
                        <span className={`dot`} style={{ backgroundColor: 'var(--text-secondary)' }}></span> 
                        IDLE
                    </div>
                )}
            </div>

            {/* Production Mode Confirmation Modal */}
            {showConfirmModal && (
                <div className="modal-overlay" onClick={() => setShowConfirmModal(false)}>
                    <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '440px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: '#f87171', marginBottom: '12px' }}>
                            <AlertTriangle size={24} />
                            <h3 style={{ margin: 0 }}>Enable Production Mode?</h3>
                        </div>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.5 }}>
                            In Production Mode, live pipeline runs and real Telegram uploads are permitted.
                            Ensure your queue and configuration are verified before executing live operations.
                        </p>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
                            <button className="btn" onClick={() => setShowConfirmModal(false)}>Cancel</button>
                            <button className="btn btn-danger" onClick={confirmProductionMode}>Enable Production Mode</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
