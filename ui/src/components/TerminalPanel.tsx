import React, { useEffect, useRef, useState, useMemo } from 'react';
import { Play, Square, Trash2, Copy, Pause, Download, WrapText, Clock, X, Activity } from 'lucide-react';
import { useJobContext } from '../contexts/JobContext';
import { stripAnsi } from '../utils/ansi';

export const TerminalPanel: React.FC = () => {
    const { 
        activeJob, historicalJob, events, connectionState, cancelActiveJob, 
        isTerminalExpanded, setTerminalExpanded, clearTerminal, clearHistoricalJob
    } = useJobContext();

    const [followLive, setFollowLive] = useState(true);
    const [wrapText, setWrapText] = useState(localStorage.getItem('terminal.wrapText') === 'true');
    const [showTimestamps, setShowTimestamps] = useState(localStorage.getItem('terminal.timestamps') !== 'false');
    const [unseenCount, setUnseenCount] = useState(0);

    const scrollRef = useRef<HTMLDivElement>(null);
    const lastScrollTop = useRef(0);
    const isAtBottom = useRef(true);

    const toggleWrap = () => {
        setWrapText(prev => {
            localStorage.setItem('terminal.wrapText', String(!prev));
            return !prev;
        });
    };

    const toggleTimestamps = () => {
        setShowTimestamps(prev => {
            localStorage.setItem('terminal.timestamps', String(!prev));
            return !prev;
        });
    };

    const handleScroll = () => {
        if (!scrollRef.current) return;
        const el = scrollRef.current;
        const currentScrollTop = el.scrollTop;
        const distanceToBottom = el.scrollHeight - currentScrollTop - el.clientHeight;
        
        const atBottom = distanceToBottom < 20;
        
        // If user scrolls up, turn off followLive
        if (currentScrollTop < lastScrollTop.current && !atBottom) {
            if (followLive) {
                setFollowLive(false);
            }
        }
        
        // If user hits bottom, turn on followLive
        if (atBottom && !followLive) {
            setFollowLive(true);
            setUnseenCount(0);
        }

        isAtBottom.current = atBottom;
        lastScrollTop.current = currentScrollTop;
    };

    // Auto-scroll effect
    useEffect(() => {
        if (followLive && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        } else if (!followLive && events.length > 0) {
            // Count unseen events roughly by seeing how many were added while not following
            setUnseenCount(prev => prev + 1); 
        }
    }, [events.length, followLive]);

    // Reset unseen when we explicitly return to live
    const returnToLive = () => {
        setFollowLive(true);
        setUnseenCount(0);
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    };

    // Slice last 5000 lines to prevent DOM explosion
    const displayEvents = useMemo(() => {
        if (events.length > 5000) {
            return events.slice(-5000);
        }
        return events;
    }, [events]);

    const handleCopyAll = () => {
        const text = events
            .filter(e => e.type === 'log')
            .map(e => stripAnsi(e.text || ''))
            .join('');
        navigator.clipboard.writeText(text);
    };

    const handleDownload = () => {
        const job = historicalJob || activeJob;
        if (job) {
            window.open(`/api/jobs/${job.id}/log`, '_blank');
        }
    };

    const formatTime = (iso?: string) => {
        if (!iso) return '';
        const d = new Date(iso);
        return d.toLocaleTimeString([], { hour12: false });
    };

    const displayedJob = historicalJob || activeJob;
    const isHistorical = !!historicalJob;

    if (!isTerminalExpanded) {
        return null;
    }

    return (
        <div className="terminal-panel">
            <div className="terminal-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {displayedJob ? (
                        <>
                            <span style={{ fontWeight: 600 }}>{isHistorical ? 'HISTORICAL' : connectionState}</span>
                            <span style={{ color: 'var(--text-secondary)' }}>—</span>
                            <span>{displayedJob.profile_id}</span>
                            {isHistorical && activeJob && (
                                <button className="btn btn-primary" onClick={clearHistoricalJob} style={{ marginLeft: '12px' }}>
                                    Return to Live Job
                                </button>
                            )}
                        </>
                    ) : (
                        <span>Idle</span>
                    )}
                </div>
                
                <div className="terminal-actions">
                    <button className={`btn ${showTimestamps ? 'active' : ''}`} onClick={toggleTimestamps} title="Toggle Timestamps">
                        <Clock size={14} />
                    </button>
                    <button className={`btn ${wrapText ? 'active' : ''}`} onClick={toggleWrap} title="Toggle Line Wrap">
                        <WrapText size={14} />
                    </button>
                    <button className={`btn ${followLive ? 'active' : ''}`} onClick={returnToLive} title="Follow Live">
                        {followLive ? <Pause size={14} /> : <Play size={14} />}
                    </button>
                    <button className="btn" onClick={handleCopyAll} title="Copy All Logs">
                        <Copy size={14} />
                    </button>
                    <button className="btn" onClick={handleDownload} title="Download Raw Log">
                        <Download size={14} />
                    </button>
                    <button className="btn" onClick={clearTerminal} title="Clear View (UI only)">
                        <Trash2 size={14} />
                    </button>
                    {!isHistorical && activeJob?.status === 'RUNNING' && (
                        <button className="btn btn-danger" onClick={cancelActiveJob} title="Stop Job">
                            <Square size={14} /> Stop
                        </button>
                    )}
                    <button className="btn" onClick={() => setTerminalExpanded(false)} title="Close Terminal">
                        <X size={14} />
                    </button>
                </div>
            </div>
            
            <div 
                className={`terminal-output ${wrapText ? 'wrap' : ''}`} 
                ref={scrollRef}
                onScroll={handleScroll}
            >
                {!displayedJob ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
                        <Activity size={48} style={{ opacity: 0.2, marginBottom: '16px' }} />
                        <div style={{ fontSize: '14px', marginBottom: '8px' }}>No active job</div>
                        <div>Run a test or diagnostic to see live output here.</div>
                    </div>
                ) : (
                    <>
                        {events.length > 5000 && (
                            <div className="term-system info">--- Showing last 5000 lines. Download raw log to see full output. ---</div>
                        )}
                        {displayEvents.map((ev, index) => {
                            if (ev.type === 'log') {
                                const isStderr = ev.stream === 'stderr';
                                return (
                                    <div key={ev.seq || index} className={`term-line ${isStderr ? 'stderr' : ''}`}>
                                        {showTimestamps && <span className="term-time">{formatTime(ev.timestamp)}</span>}
                                        <span className="term-text">{stripAnsi(ev.text || '')}</span>
                                    </div>
                                );
                            } else if (ev.type === 'job_started') {
                                return <div key={ev.seq || index} className="term-system info">--- Job Started ---</div>;
                            } else if (ev.type === 'job_finished') {
                                const isPass = ev.status === 'PASSED';
                                return <div key={ev.seq || index} className={`term-system ${isPass ? 'pass' : 'fail'}`}>--- Job Finished: {ev.status} (Exit: {ev.exit_code}) ---</div>;
                            } else if (ev.type === 'job_status') {
                                return <div key={ev.seq || index} className="term-system warn">--- Status Changed: {ev.status} ---</div>;
                            } else if (ev.type === 'error') {
                                return <div key={ev.seq || index} className="term-system fail">--- Error: {ev.message} ---</div>;
                            } else if (ev.type === 'job_progress') {
                                return <div key={ev.seq || index} className="term-system info" style={{ fontWeight: 'normal', color: 'var(--text-secondary)' }}>[ Progress: {ev.progress}% ]</div>;
                            } else if (ev.type === 'job_summary') {
                                return <div key={ev.seq || index} className="term-system pass">=== Job Summary: Duration {ev.duration_seconds?.toFixed(1)}s, Passed: {ev.passed || 0}, Failed: {ev.failed || 0} ===</div>;
                            }
                            return null;
                        })}
                        
                        {!isHistorical && connectionState === 'LIVE' && activeJob?.status === 'RUNNING' && (
                            <div className="term-line" style={{ marginTop: '8px' }}>
                                <span className="cursor-blink">█</span>
                            </div>
                        )}
                        {connectionState === 'RECONNECTING' && (
                            <div className="term-system warn">--- Reconnecting to Live Stream... ---</div>
                        )}
                    </>
                )}
            </div>
            
            {!followLive && unseenCount > 0 && (
                <div 
                    className="return-to-live" 
                    onClick={returnToLive}
                >
                    ↓ {unseenCount} new events. Return to Live
                </div>
            )}
        </div>
    );
};
