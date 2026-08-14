import React, { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { api, type JobSummary, WS_BASE } from '../services/api';

export interface TerminalEvent {
    seq: number;
    type: string;
    timestamp?: string;
    text?: string;
    stream?: string;
    progress?: number;
    status?: string;
    exit_code?: number;
    duration_seconds?: number;
    message?: string;
    passed?: number;
    failed?: number;
    skipped?: number;
    warnings?: number;
}

export type ConnectionState = 'IDLE' | 'LIVE' | 'RECONNECTING' | 'HISTORICAL';

interface JobContextState {
    activeJob: JobSummary | null;
    historicalJob: JobSummary | null;
    connectionState: ConnectionState;
    events: TerminalEvent[];
    startJob: (profileId: string) => Promise<void>;
    cancelActiveJob: () => Promise<void>;
    viewHistoricalJob: (job: JobSummary) => void;
    clearHistoricalJob: () => void;
    isTerminalExpanded: boolean;
    setTerminalExpanded: (val: boolean) => void;
    clearTerminal: () => void;
}

const JobContext = createContext<JobContextState | null>(null);

export const useJobContext = () => {
    const ctx = useContext(JobContext);
    if (!ctx) throw new Error("useJobContext must be used within JobProvider");
    return ctx;
};

export const JobProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [activeJob, setActiveJob] = useState<JobSummary | null>(null);
    const [historicalJob, setHistoricalJob] = useState<JobSummary | null>(null);
    const [connectionState, setConnectionState] = useState<ConnectionState>('IDLE');
    const [events, setEvents] = useState<TerminalEvent[]>([]);
    const [isTerminalExpanded, setTerminalExpanded] = useState(false);
    
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<any>(null);
    const reconnectDelayRef = useRef<number>(1000);
    const isMounted = useRef(true);

    const activeJobRef = useRef<JobSummary | null>(null);
    
    // We keep events in a ref to avoid stale closures in the websocket message handler
    const eventsRef = useRef<TerminalEvent[]>([]);

    useEffect(() => {
        isMounted.current = true;
        return () => { isMounted.current = false; };
    }, []);

    const setEventsSafe = (newEvents: TerminalEvent[]) => {
        eventsRef.current = newEvents;
        setEvents(newEvents);
    };

    const appendEvent = useCallback((ev: TerminalEvent) => {
        if (!eventsRef.current.some(e => e.seq === ev.seq)) {
            const next = [...eventsRef.current, ev];
            eventsRef.current = next;
            setEvents(next);
        }
    }, []);

    // 1. Initial Hydration
    useEffect(() => {
        const init = async () => {
            try {
                const current = await api.getCurrentJob();
                if (isMounted.current && current) {
                    setActiveJob(current);
                    activeJobRef.current = current;
                    setTerminalExpanded(true);
                }
            } catch (e) {
                console.error("Failed to fetch current job", e);
            }
        };
        init();
    }, []);

    // 2. WebSocket Manager
    useEffect(() => {
        const job = activeJob;
        if (!job) {
            if (wsRef.current) {
                wsRef.current.close(1000);
                wsRef.current = null;
            }
            if (!historicalJob) {
                setConnectionState('IDLE');
            }
            return;
        }

        // We are going to connect to activeJob
        let intentionalClose = false;

        const connect = () => {
            if (!isMounted.current || activeJobRef.current?.id !== job.id) return;
            
            const lastSeq = eventsRef.current.length > 0 ? eventsRef.current[eventsRef.current.length - 1].seq : 0;
            const ws = new WebSocket(`${WS_BASE}/jobs/${job.id}/stream?after_seq=${lastSeq}`);
            
            ws.onopen = () => {
                setConnectionState('LIVE');
                reconnectDelayRef.current = 1000;
            };

            ws.onmessage = (e) => {
                try {
                    const ev: TerminalEvent = JSON.parse(e.data);
                    appendEvent(ev);
                    
                    if (ev.type === 'job_finished') {
                        // Backend finished. We can disconnect.
                        intentionalClose = true;
                        ws.close(1000);
                        // Refresh current job status to get final duration/exit code
                        api.getCurrentJob().then(current => {
                            if (!current && activeJobRef.current?.id === job.id) {
                                // Job finished and is no longer current
                                api.getJobs().then(jobs => {
                                    const finalJob = jobs.find(j => j.id === job.id);
                                    if (finalJob) {
                                        setHistoricalJob(finalJob);
                                        setActiveJob(null);
                                        activeJobRef.current = null;
                                        setConnectionState('HISTORICAL');
                                    }
                                });
                            }
                        });
                    }
                } catch (err) {
                    console.error("Parse error:", err);
                }
            };
            
            ws.onclose = (e) => {
                if (intentionalClose) return;
                
                // Unexpected close (e.g., backend restart or network drop)
                if (e.code === 1008) {
                    console.error("WebSocket rejected due to invalid Origin.");
                    return;
                }
                
                if (activeJobRef.current?.id === job.id) {
                    setConnectionState('RECONNECTING');
                    reconnectTimeoutRef.current = setTimeout(() => {
                        connect();
                    }, Math.min(reconnectDelayRef.current, 10000));
                    reconnectDelayRef.current *= 2;
                }
            };

            wsRef.current = ws;
        };

        // If we switch to a new active job, clear events if it's different from the one we have
        if (eventsRef.current.length > 0 && activeJobRef.current?.id !== job.id) {
             setEventsSafe([]);
        }
        
        activeJobRef.current = job;
        setHistoricalJob(null); // Clear historical when active job starts
        connect();

        return () => {
            intentionalClose = true;
            if (wsRef.current) wsRef.current.close(1000);
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        };
    }, [activeJob?.id]); // Only re-evaluate if the ID changes

    // 3. Polling Fallback
    useEffect(() => {
        let interval: any = null;
        if (activeJob) {
            interval = setInterval(async () => {
                try {
                    const current = await api.getCurrentJob();
                    if (!current && activeJobRef.current) {
                        // The backend says no active job, but we think there is one.
                        // Wait for websocket to close naturally, or force a sync.
                        if (connectionState !== 'LIVE') {
                            setActiveJob(null);
                            activeJobRef.current = null;
                        }
                    }
                } catch (e) {
                    // network error, ignore
                }
            }, 3000);
        }
        return () => {
            if (interval) clearInterval(interval);
        };
    }, [activeJob?.id, connectionState]);

    const startJob = async (profileId: string) => {
        setEventsSafe([]);
        const job = await api.startJob(profileId);
        setActiveJob(job);
        activeJobRef.current = job;
        setTerminalExpanded(true);
    };

    const cancelActiveJob = async () => {
        if (activeJob) {
            await api.cancelJob(activeJob.id);
        }
    };

    const viewHistoricalJob = async (job: JobSummary) => {
        if (activeJob) {
            alert("A live job is currently running.");
            return;
        }
        setEventsSafe([]);
        setHistoricalJob(job);
        setConnectionState('HISTORICAL');
        setTerminalExpanded(true);
        try {
            // we load historical via REST
            const log = await api.getJobLog(job.id); // Or events endpoint if implemented. For now, log is plain text.
            // Wait, we can't just throw raw text into structured events, 
            // but we can wrap it as one giant log event for now, or fetch events!
            // Let's wrap as a single log event for historical viewing, 
            // since we don't have a REST endpoint for events yet.
            // Actually, we do have /api/jobs/{id}/log. Let's just use it.
            setEventsSafe([{ seq: 0, type: 'log', text: log }]);
        } catch (e) {
            console.error(e);
        }
    };

    const clearHistoricalJob = () => {
        setHistoricalJob(null);
        setConnectionState('IDLE');
        setEventsSafe([]);
    };
    
    const clearTerminal = () => {
        setEventsSafe([]);
    };

    return (
        <JobContext.Provider value={{
            activeJob,
            historicalJob,
            connectionState,
            events,
            startJob,
            cancelActiveJob,
            viewHistoricalJob,
            clearHistoricalJob,
            isTerminalExpanded,
            setTerminalExpanded,
            clearTerminal
        }}>
            {children}
        </JobContext.Provider>
    );
};
