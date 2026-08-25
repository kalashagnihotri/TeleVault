import React, { useEffect, useRef, useState, useMemo } from 'react';
import { Play, Square, Trash2, Copy, Pause, Download, WrapText, Clock, X, Activity, Search, ChevronUp, ChevronDown, AlertCircle } from 'lucide-react';
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

    // Search and Jump State
    const [searchTerm, setSearchTerm] = useState('');
    const [showSearch, setShowSearch] = useState(false);
    const [currentMatchIdx, setCurrentMatchIdx] = useState(0);

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
        
        if (currentScrollTop < lastScrollTop.current && !atBottom) {
            if (followLive) setFollowLive(false);
        }
        
        if (atBottom && !followLive) {
            setFollowLive(true);
            setUnseenCount(0);
        }

        isAtBottom.current = atBottom;
        lastScrollTop.current = currentScrollTop;
    };

    useEffect(() => {
        if (followLive && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        } else if (!followLive && events.length > 0) {
            setUnseenCount(prev => prev + 1); 
        }
    }, [events.length, followLive]);

    const returnToLive = () => {
        setFollowLive(true);
        setUnseenCount(0);
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    };

    const displayEvents = useMemo(() => {
        if (events.length > 5000) {
            return events.slice(-5000);
        }
        return events;
    }, [events]);

    // Progress detection from logs
    const detectedProgress = useMemo(() => {
        for (let i = displayEvents.length - 1; i >= Math.max(0, displayEvents.length - 30); i--) {
            const ev = displayEvents[i];
            if (ev.type === 'job_progress' && ev.progress !== undefined) {
                return ev.progress;
            }
            if (ev.type === 'log' && ev.text) {
                const clean = stripAnsi(ev.text);
                const pctMatch = clean.match(/\[\s*(\d+)%\s*\]/);
                if (pctMatch) {
                    return parseInt(pctMatch[1], 10);
                }
            }
        }
        return null;
    }, [displayEvents]);

    // Search matches calculation
    const searchMatches = useMemo(() => {
        if (!searchTerm.trim()) return [];
        const matches: number[] = [];
        displayEvents.forEach((ev, idx) => {
            const text = stripAnsi(ev.text || ev.message || '');
            if (text.toLowerCase().includes(searchTerm.toLowerCase())) {
                matches.push(idx);
            }
        });
        return matches;
    }, [displayEvents, searchTerm]);

    // Error line indexes
    const errorLineIndices = useMemo(() => {
        const indices: number[] = [];
        displayEvents.forEach((ev, idx) => {
            if (ev.type === 'error' || ev.stream === 'stderr') {
                indices.push(idx);
            } else if (ev.type === 'log' && ev.text) {
                const text = stripAnsi(ev.text).toLowerCase();
                if (text.includes('failed') || text.includes('error:') || text.includes('traceback')) {
                    indices.push(idx);
                }
            }
        });
        return indices;
    }, [displayEvents]);

    const jumpToLine = (lineIdx: number) => {
        if (!scrollRef.current) return;
        const lineEl = scrollRef.current.children[lineIdx] as HTMLElement;
        if (lineEl) {
            setFollowLive(false);
            lineEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    };

    const nextMatch = () => {
        if (searchMatches.length === 0) return;
        const nextIdx = (currentMatchIdx + 1) % searchMatches.length;
        setCurrentMatchIdx(nextIdx);
        jumpToLine(searchMatches[nextIdx]);
    };

    const prevMatch = () => {
        if (searchMatches.length === 0) return;
        const prevIdx = (currentMatchIdx - 1 + searchMatches.length) % searchMatches.length;
        setCurrentMatchIdx(prevIdx);
        jumpToLine(searchMatches[prevIdx]);
    };

    const jumpToNextError = () => {
        if (errorLineIndices.length === 0) return;
        jumpToLine(errorLineIndices[0]);
    };

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
                            {detectedProgress !== null && (
                                <span style={{ backgroundColor: 'rgba(163, 113, 247, 0.2)', color: '#c084fc', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700 }}>
                                    {detectedProgress}%
                                </span>
                            )}
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
                    {errorLineIndices.length > 0 && (
                        <button className="btn btn-danger" onClick={jumpToNextError} title={`Jump to errors (${errorLineIndices.length} found)`} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <AlertCircle size={13} /> {errorLineIndices.length} Errors
                        </button>
                    )}
                    <button className={`btn ${showSearch ? 'active' : ''}`} onClick={() => setShowSearch(!showSearch)} title="Search inside terminal">
                        <Search size={14} />
                    </button>
                    <button className={`btn ${showTimestamps ? 'active' : ''}`} onClick={toggleTimestamps} title="Toggle Timestamps">
                        <Clock size={14} />
                    </button>
                    <button className={`btn ${wrapText ? 'active' : ''}`} onClick={toggleWrap} title="Toggle Line Wrap">
                        <WrapText size={14} />
                    </button>
                    <button className={`btn ${followLive ? 'active' : ''}`} onClick={returnToLive} title="Follow Live / Pause">
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

            {/* In-Terminal Search Bar */}
            {showSearch && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 12px', backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-color)' }}>
                    <Search size={14} style={{ color: 'var(--text-secondary)' }} />
                    <input 
                        type="text" 
                        placeholder="Search logs..." 
                        value={searchTerm} 
                        onChange={e => { setSearchTerm(e.target.value); setCurrentMatchIdx(0); }}
                        style={{ flex: 1, backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px 8px', color: 'var(--text-primary)', fontSize: '12px' }}
                        autoFocus
                    />
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)', minWidth: '70px', textAlign: 'center' }}>
                        {searchMatches.length > 0 ? `${currentMatchIdx + 1} of ${searchMatches.length}` : 'No matches'}
                    </span>
                    <button className="btn" onClick={prevMatch} disabled={searchMatches.length === 0} title="Previous match">
                        <ChevronUp size={14} />
                    </button>
                    <button className="btn" onClick={nextMatch} disabled={searchMatches.length === 0} title="Next match">
                        <ChevronDown size={14} />
                    </button>
                    <button className="btn" onClick={() => { setShowSearch(false); setSearchTerm(''); }} title="Close search">
                        <X size={14} />
                    </button>
                </div>
            )}

            {/* Progress Bar Header */}
            {detectedProgress !== null && (
                <div style={{ height: '3px', backgroundColor: 'rgba(255, 255, 255, 0.05)', width: '100%' }}>
                    <div style={{ height: '100%', width: `${detectedProgress}%`, backgroundColor: '#a855f7', transition: 'width 0.3s ease' }} />
                </div>
            )}
            
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
                                const rawText = stripAnsi(ev.text || '');
                                return (
                                    <div key={ev.seq || index} className={`term-line ${isStderr ? 'stderr' : ''}`}>
                                        {showTimestamps && <span className="term-time">{formatTime(ev.timestamp)}</span>}
                                        <span className="term-text">{rawText}</span>
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
