import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, PlaySquare, FileTerminal, LayoutDashboard, Settings } from 'lucide-react';
import { useJobContext } from '../contexts/JobContext';

export const Sidebar: React.FC = () => {
    const { activeJob, connectionState, setTerminalExpanded, isTerminalExpanded } = useJobContext();
    const [durationStr, setDurationStr] = useState('');

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

    return (
        <div className="sidebar">
            <div className="sidebar-header">
                Telegram Media Archive
                <div className="badge">SAFE / READ-ONLY</div>
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
                <div className="nav-item disabled"><Settings className="nav-icon" /> Config (Coming Soon)</div>
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
        </div>
    );
};
