import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { 
    api, 
    type ArchiveRecord, 
    type ArchiveStats, 
    type RoutingExplanation, 
    type MediaTimeline,
    type SimilarMediaResponse,
    type SmartCollection,
    type ArchiveAnalyticsData,
    type AssistantQueryResponse,
    type MemoryEvent,
    type MemoryChatResponse,
    type ArchiveQualityMetrics,
    type RelationshipGraphData,
    type PersonProfile,
    type AutobiographyResponse,
    type LocationHierarchyResponse
} from '../services/api';
import { 
    RefreshCw, 
    CheckCircle, 
    AlertCircle, 
    XCircle, 
    Clock, 
    Sparkles, 
    Folder, 
    Users, 
    ArrowRight, 
    MessageSquare,
    ShieldCheck,
    Heart,
    Network,
    ChevronDown,
    ChevronRight,
    MapPin,
    Calendar,
    Award,
    BookOpen,
    Compass
} from 'lucide-react';

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null | undefined) {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
}

function fmtBytes(b: number | null | undefined) {
    if (b === null || b === undefined) return '—';
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

const STATUS_COLORS: Record<string, string> = {
    BACKED_UP: 'var(--success-color)',
    PENDING: 'var(--warning-color)',
    ANALYZING: 'var(--warning-color)',
    READY: '#818cf8',
    FAILED: 'var(--error-color)',
    CANCELLED: 'var(--text-secondary)',
};

type Tab = 'recent' | 'memories' | 'search' | 'assistant' | 'autobiography' | 'places' | 'collections' | 'analytics' | 'pending';
type ModalTab = 'details' | 'timeline' | 'explain' | 'similar';

interface TimelineMonthGroup {
    monthName: string;
    events: MemoryEvent[];
}

interface TimelineYearGroup {
    year: string;
    months: TimelineMonthGroup[];
}

function groupMemoriesByTimeline(events: MemoryEvent[]): TimelineYearGroup[] {
    const yearsMap = new Map<string, Map<string, MemoryEvent[]>>();
    
    for (const ev of events) {
        const d = new Date(ev.start_date || Date.now());
        const year = isNaN(d.getFullYear()) ? 'Other' : String(d.getFullYear());
        const month = isNaN(d.getMonth()) ? 'General' : d.toLocaleString('default', { month: 'long' });
        
        if (!yearsMap.has(year)) {
            yearsMap.set(year, new Map());
        }
        const monthMap = yearsMap.get(year)!;
        if (!monthMap.has(month)) {
            monthMap.set(month, []);
        }
        monthMap.get(month)!.push(ev);
    }
    
    const result: TimelineYearGroup[] = [];
    for (const [year, monthMap] of yearsMap.entries()) {
        const months: TimelineMonthGroup[] = [];
        for (const [monthName, evs] of monthMap.entries()) {
            months.push({ monthName, events: evs });
        }
        result.push({ year, months });
    }
    return result;
}

// ── Record Detail Modal ────────────────────────────────────────────────────

const RecordDetail: React.FC<{ 
    record: ArchiveRecord; 
    onClose: () => void;
    onRecordUpdated?: (updated: ArchiveRecord) => void;
}> = ({ record, onClose, onRecordUpdated }) => {
    const [currentRecord, setCurrentRecord] = useState<ArchiveRecord>(record);
    const [modalTab, setModalTab] = useState<ModalTab>('details');
    const [explanation, setExplanation] = useState<RoutingExplanation | null>(null);
    const [explainLoading, setExplainLoading] = useState(false);
    const [explainError, setExplainError] = useState<string | null>(null);
    const [timeline, setTimeline] = useState<MediaTimeline | null>(null);
    const [timelineLoading, setTimelineLoading] = useState(false);
    const [timelineError, setTimelineError] = useState<string | null>(null);
    const [similarData, setSimilarData] = useState<SimilarMediaResponse | null>(null);
    const [similarLoading, setSimilarLoading] = useState(false);
    const [similarError, setSimilarError] = useState<string | null>(null);
    const [replayLoading, setReplayLoading] = useState(false);
    const [replayMsg, setReplayMsg] = useState<string | null>(null);

    const loadExplanation = async () => {
        setExplainLoading(true);
        setExplainError(null);
        try {
            const exp = await api.explainRouting(currentRecord.id);
            setExplanation(exp);
        } catch (err: any) {
            setExplainError(err.message || 'Failed to load explanation');
        } finally {
            setExplainLoading(false);
        }
    };

    const loadTimeline = async () => {
        setTimelineLoading(true);
        setTimelineError(null);
        try {
            const tl = await api.getMediaTimeline(currentRecord.id);
            setTimeline(tl);
        } catch (err: any) {
            setTimelineError(err.message || 'Failed to load timeline');
        } finally {
            setTimelineLoading(false);
        }
    };

    const loadSimilar = async () => {
        setSimilarLoading(true);
        setSimilarError(null);
        try {
            const sim = await api.getSimilarMedia(currentRecord.id, 10);
            setSimilarData(sim);
        } catch (err: any) {
            setSimilarError(err.message || 'Failed to load similar media');
        } finally {
            setSimilarLoading(false);
        }
    };

    useEffect(() => {
        if (modalTab === 'explain' && !explanation && !explainLoading) {
            loadExplanation();
        } else if (modalTab === 'timeline' && !timeline && !timelineLoading) {
            loadTimeline();
        } else if (modalTab === 'similar' && !similarData && !similarLoading) {
            loadSimilar();
        }
    }, [modalTab, currentRecord.id]);

    const handleReplayScene = async () => {
        setReplayLoading(true);
        setReplayMsg(null);
        try {
            const res = await api.replayAnalysis(currentRecord.id, 'scene');
            setReplayMsg(`✓ Re-analyzed: ${res.new_labels.join(', ') || 'No labels'}`);
            const updated = { ...currentRecord, scenes: res.new_labels };
            setCurrentRecord(updated);
            if (onRecordUpdated) onRecordUpdated(updated);
        } catch (err: any) {
            setReplayMsg(`Failed: ${err.message}`);
        } finally {
            setReplayLoading(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '640px', maxHeight: '88vh', overflowY: 'auto' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span>Media #{currentRecord.id}:</span>
                        <code style={{ fontSize: '13px', color: 'var(--primary-color)' }}>{currentRecord.original_filename}</code>
                    </h3>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '18px' }}>✕</button>
                </div>

                {/* Subtabs */}
                <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '16px' }}>
                    {[
                        { id: 'details', label: 'Overview & Analysis' },
                        { id: 'similar', label: '🔍 Find Similar' },
                        { id: 'timeline', label: 'Pipeline Timeline' },
                        { id: 'explain', label: 'Explain Routing' },
                    ].map(st => (
                        <button
                            key={st.id}
                            onClick={() => setModalTab(st.id as ModalTab)}
                            style={{
                                padding: '6px 12px',
                                border: 'none',
                                background: 'none',
                                borderBottom: modalTab === st.id ? '2px solid var(--primary-color)' : '2px solid transparent',
                                color: modalTab === st.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                                fontWeight: modalTab === st.id ? 600 : 400,
                                cursor: 'pointer',
                                fontSize: '12px',
                            }}
                        >
                            {st.label}
                        </button>
                    ))}
                </div>

                {/* 1. Overview Tab */}
                {modalTab === 'details' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '8px', fontSize: '13px' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Status:</span>
                            <span>
                                <span style={{
                                    display: 'inline-block',
                                    padding: '2px 8px',
                                    borderRadius: '4px',
                                    fontSize: '11px',
                                    fontWeight: 600,
                                    backgroundColor: `${STATUS_COLORS[currentRecord.status] || '#6b7280'}22`,
                                    color: STATUS_COLORS[currentRecord.status] || '#6b7280',
                                }}>
                                    {currentRecord.status}
                                </span>
                            </span>

                            <span style={{ color: 'var(--text-secondary)' }}>SHA-256 Prefix:</span>
                            <code style={{ fontSize: '12px' }}>{currentRecord.sha256_prefix}…</code>

                            <span style={{ color: 'var(--text-secondary)' }}>Media Type / Size:</span>
                            <span>{currentRecord.media_type} ({fmtBytes(currentRecord.file_size_bytes)})</span>

                            <span style={{ color: 'var(--text-secondary)' }}>Discovered At:</span>
                            <span>{fmtDate(currentRecord.created_at)}</span>

                            {currentRecord.location_label && (
                                <>
                                    <span style={{ color: 'var(--text-secondary)' }}>GPS Location:</span>
                                    <span>📍 {currentRecord.location_label}</span>
                                </>
                            )}
                        </div>

                        {/* SECTION: FACES */}
                        <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px 16px', backgroundColor: 'var(--bg-color)' }}>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                                👤 Detected Faces
                            </div>
                            {currentRecord.faces && currentRecord.faces.length > 0 ? (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                    {currentRecord.faces.map((f, idx) => (
                                        <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                                            <span><strong>Face #{idx + 1}:</strong> {f.name ?? 'Unknown person'}</span>
                                            <span style={{ color: f.decision === 'KNOWN_MATCH' ? 'var(--success-color)' : 'var(--text-secondary)', fontSize: '11px' }}>
                                                {f.decision} {f.score ? `(${f.score.toFixed(2)})` : ''}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>No faces detected.</div>
                            )}
                        </div>

                        {/* SECTION: SCENES */}
                        <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px 16px', backgroundColor: 'var(--bg-color)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    🌄 Scene Labels & Heuristics
                                </div>
                                <button 
                                    className="btn" 
                                    onClick={handleReplayScene}
                                    disabled={replayLoading}
                                    style={{ fontSize: '11px', padding: '3px 8px', display: 'flex', alignItems: 'center', gap: '4px' }}
                                >
                                    <RefreshCw size={11} className={replayLoading ? 'spin' : ''} />
                                    Re-run Scene Analysis
                                </button>
                            </div>
                            {replayMsg && (
                                <div style={{ fontSize: '11px', color: replayMsg.startsWith('✓') ? 'var(--success-color)' : 'var(--error-color)', marginBottom: '6px' }}>
                                    {replayMsg}
                                </div>
                            )}
                            {currentRecord.scenes && currentRecord.scenes.length > 0 ? (
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                    {currentRecord.scenes.map((s, idx) => (
                                        <span key={idx} style={{
                                            padding: '3px 8px',
                                            borderRadius: '4px',
                                            backgroundColor: 'rgba(99, 102, 241, 0.15)',
                                            border: '1px solid rgba(99, 102, 241, 0.3)',
                                            fontSize: '12px',
                                            color: '#a5b4fc',
                                        }}>
                                            #{s}
                                        </span>
                                    ))}
                                </div>
                            ) : (
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>No scene tags extracted.</div>
                            )}
                        </div>

                        {/* SECTION: TELEGRAM */}
                        <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px 16px', backgroundColor: 'var(--bg-color)' }}>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                                ✈️ Telegram Archival
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '6px', fontSize: '12px' }}>
                                <span style={{ color: 'var(--text-secondary)' }}>Topic:</span>
                                <span>{currentRecord.topic ?? '—'}</span>
                                <span style={{ color: 'var(--text-secondary)' }}>Preview Msg ID:</span>
                                <span>{currentRecord.preview_message_id ?? '—'}</span>
                                <span style={{ color: 'var(--text-secondary)' }}>Original Msg ID:</span>
                                <span>{currentRecord.original_message_id ?? '—'}</span>
                                <span style={{ color: 'var(--text-secondary)' }}>Uploaded At:</span>
                                <span>{fmtDate(currentRecord.backed_up_at)}</span>
                            </div>
                        </div>
                    </div>
                )}

                {/* 2. Similar Media Tab */}
                {modalTab === 'similar' && (
                    <div>
                        {similarLoading && (
                            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                                Computing multi-factor similarities…
                            </div>
                        )}
                        {similarError && (
                            <div style={{ color: '#ef4444', fontSize: '13px', padding: '12px' }}>
                                {similarError}
                            </div>
                        )}
                        {similarData && (
                            <div>
                                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '14px' }}>
                                    Found {similarData.total_matches} related media based on shared people, scene categories, date proximity, and GPS locations.
                                </p>
                                {similarData.similar_items.length === 0 ? (
                                    <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                                        No strong similarity matches found in the archive.
                                    </div>
                                ) : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                        {similarData.similar_items.map((item) => (
                                            <div key={item.media_id} style={{
                                                padding: '10px 14px',
                                                borderRadius: '6px',
                                                backgroundColor: 'var(--bg-color)',
                                                border: '1px solid var(--border-color)',
                                                display: 'flex',
                                                justifyContent: 'space-between',
                                                alignItems: 'center'
                                            }}>
                                                <div>
                                                    <div style={{ fontWeight: 600, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                        <span>{item.original_filename}</span>
                                                        <span style={{
                                                            fontSize: '11px',
                                                            fontWeight: 700,
                                                            padding: '2px 6px',
                                                            borderRadius: '4px',
                                                            backgroundColor: item.similarity_score >= 70 ? 'rgba(34,197,94,0.15)' : 'rgba(234,179,8,0.15)',
                                                            color: item.similarity_score >= 70 ? '#22c55e' : '#eab308'
                                                        }}>
                                                            {item.similarity_score}% Similar
                                                        </span>
                                                    </div>
                                                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                                                        {item.reasons.join(' • ')}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* 3. Timeline Tab */}
                {modalTab === 'timeline' && (
                    <div>
                        {timelineLoading && (
                            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                                Loading pipeline timeline…
                            </div>
                        )}
                        {timelineError && (
                            <div style={{ color: '#ef4444', fontSize: '13px', padding: '12px' }}>
                                {timelineError}
                            </div>
                        )}
                        {timeline && (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                {timeline.events.map((ev, i) => {
                                    const isDone = ev.status === 'DONE';
                                    const isRunning = ev.status === 'RUNNING';
                                    const isFailed = ev.status === 'FAILED';
                                    const isSkipped = ev.status === 'SKIPPED';
                                    const col = isDone ? '#22c55e' : isRunning ? '#818cf8' : isFailed ? '#ef4444' : isSkipped ? '#6b7280' : 'var(--text-secondary)';
                                    return (
                                        <div key={i} style={{
                                            display: 'flex',
                                            gap: '12px',
                                            alignItems: 'flex-start',
                                            padding: '10px 14px',
                                            borderRadius: '6px',
                                            backgroundColor: 'var(--bg-color)',
                                            border: '1px solid var(--border-color)',
                                            fontSize: '12px'
                                        }}>
                                            <div style={{ marginTop: '2px' }}>
                                                {isDone ? <CheckCircle size={15} color={col} /> :
                                                 isRunning ? <Clock size={15} color={col} className="spin" /> :
                                                 isFailed ? <XCircle size={15} color={col} /> :
                                                 <AlertCircle size={15} color={col} />}
                                            </div>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                    <strong>{ev.title}</strong>
                                                    <span style={{ fontSize: '10px', color: col, fontWeight: 700 }}>{ev.status}</span>
                                                </div>
                                                {ev.details && (
                                                    <div style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '11px' }}>
                                                        {ev.details}
                                                    </div>
                                                )}
                                                {ev.timestamp && (
                                                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px', fontSize: '10px' }}>
                                                        {fmtDate(ev.timestamp)}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}

                {/* 4. Explain Routing Tab */}
                {modalTab === 'explain' && (
                    <div>
                        {explainLoading && (
                            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                                Evaluating routing policy against active rules…
                            </div>
                        )}
                        {explainError && (
                            <div style={{ color: '#ef4444', fontSize: '13px', padding: '12px' }}>
                                {explainError}
                            </div>
                        )}
                        {explanation && (
                            <div>
                                <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '6px', backgroundColor: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.3)' }}>
                                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#818cf8', marginBottom: '4px' }}>
                                        Winning Rule: {explanation.winning_rule} → Topic "{explanation.assigned_topic}"
                                    </div>
                                    <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '12px', color: 'var(--text-primary)' }}>
                                        {explanation.summary_reasons.map((r, i) => (
                                            <li key={i}>{r}</li>
                                        ))}
                                    </ul>
                                </div>

                                <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '8px' }}>
                                    Evaluation Pipeline
                                </h4>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    {explanation.evaluations.map((ev, i) => (
                                        <div key={i} style={{
                                            padding: '8px 12px',
                                            borderRadius: '6px',
                                            backgroundColor: 'var(--bg-color)',
                                            border: `1px solid ${ev.matched ? (ev.superseded ? 'rgba(234,179,8,0.4)' : 'rgba(34,197,94,0.4)') : 'var(--border-color)'}`,
                                            fontSize: '12px',
                                        }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <strong>{ev.rule_name} → {ev.target_topic}</strong>
                                                <span style={{
                                                    fontSize: '10px',
                                                    fontWeight: 700,
                                                    color: ev.matched ? (ev.superseded ? '#eab308' : '#22c55e') : 'var(--text-secondary)'
                                                }}>
                                                    {ev.matched ? (ev.superseded ? 'MATCHED (SUPERSEDED)' : 'MATCHED (WINNER)') : 'NO MATCH'}
                                                </span>
                                            </div>
                                            <div style={{ color: 'var(--text-secondary)', fontSize: '11px', marginTop: '2px' }}>
                                                {ev.reason}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

// ── Main Archive Page ──────────────────────────────────────────────────────

export const Archive: React.FC = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const initialQuery = searchParams.get('q') || '';
    const initialTab = (searchParams.get('tab') as Tab) || (initialQuery ? 'search' : 'recent');

    const [tab, setTab] = useState<Tab>(initialTab);
    const [stats, setStats] = useState<ArchiveStats | null>(null);
    const [records, setRecords] = useState<ArchiveRecord[]>([]);
    const [searchQuery, setSearchQuery] = useState(initialQuery);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedRecord, setSelectedRecord] = useState<ArchiveRecord | null>(null);

    // Phase 6.5D States
    const [collections, setCollections] = useState<SmartCollection[]>([]);
    const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
    const [analytics, setAnalytics] = useState<ArchiveAnalyticsData | null>(null);
    const [assistantQuery, setAssistantQuery] = useState('');
    const [assistantResponse, setAssistantResponse] = useState<AssistantQueryResponse | null>(null);
    const [assistantLoading, setAssistantLoading] = useState(false);

    // Phase 6.5E Memory Engine States
    const [memories, setMemories] = useState<MemoryEvent[]>([]);
    const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
    const [memoryChatPrompt, setMemoryChatPrompt] = useState('');
    const [memoryChatResponse, setMemoryChatResponse] = useState<MemoryChatResponse | null>(null);
    const [memoryChatLoading, setMemoryChatLoading] = useState(false);
    const [qualityMetrics, setQualityMetrics] = useState<ArchiveQualityMetrics | null>(null);
    const [relationshipData, setRelationshipData] = useState<RelationshipGraphData | null>(null);
    const [peopleProfiles, setPeopleProfiles] = useState<PersonProfile[]>([]);
    const [autobiography, setAutobiography] = useState<AutobiographyResponse | null>(null);
    const [placesHierarchy, setPlacesHierarchy] = useState<LocationHierarchyResponse | null>(null);

    const loadStats = useCallback(async () => {
        try {
            const s = await api.getArchiveStats();
            setStats(s);
        } catch {}
    }, []);

    const loadRecords = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            let res: ArchiveRecord[] = [];
            if (tab === 'recent') {
                res = await api.getArchiveRecent(50);
            } else if (tab === 'pending') {
                res = await api.getArchivePending(50);
            } else if (tab === 'search') {
                if (searchQuery.trim()) {
                    res = await api.searchArchive(searchQuery.trim(), 50);
                } else {
                    res = [];
                }
            } else if (tab === 'autobiography') {
                const auto = await api.getAutobiography('2026');
                setAutobiography(auto);
            } else if (tab === 'places') {
                const plc = await api.getLocationsHierarchy();
                setPlacesHierarchy(plc);
            } else if (tab === 'collections') {
                if (selectedCollectionId) {
                    res = await api.getSmartCollectionItems(selectedCollectionId);
                } else {
                    const cols = await api.getSmartCollections();
                    setCollections(cols);
                }
            } else if (tab === 'memories') {
                const [mems, qm, rel, profs] = await Promise.all([
                    api.getMemories(),
                    api.getArchiveQuality().catch(() => null),
                    api.getRelationships().catch(() => null),
                    api.getPeopleProfiles().catch(() => [])
                ]);
                setMemories(mems);
                setQualityMetrics(qm);
                setRelationshipData(rel);
                setPeopleProfiles(profs);
            } else if (tab === 'analytics') {
                const [ana, qm, rel, profs] = await Promise.all([
                    api.getArchiveAnalytics(),
                    api.getArchiveQuality().catch(() => null),
                    api.getRelationships().catch(() => null),
                    api.getPeopleProfiles().catch(() => [])
                ]);
                setAnalytics(ana);
                setQualityMetrics(qm);
                setRelationshipData(rel);
                setPeopleProfiles(profs);
            }
            setRecords(res);
        } catch (e: any) {
            setError(e.message || 'Failed to load records');
        } finally {
            setLoading(false);
        }
    }, [tab, searchQuery, selectedCollectionId]);

    useEffect(() => {
        loadStats();
    }, [loadStats]);

    useEffect(() => {
        loadRecords();
    }, [loadRecords]);

    const handleSearchSubmit = (e?: React.FormEvent) => {
        if (e) e.preventDefault();
        setSearchParams(prev => {
            const n = new URLSearchParams(prev);
            n.set('tab', 'search');
            n.set('q', searchQuery);
            return n;
        });
        loadRecords();
    };

    const handleAssistantSubmit = async (e?: React.FormEvent, customQ?: string) => {
        if (e) e.preventDefault();
        const q = customQ || assistantQuery;
        if (!q.trim()) return;
        setAssistantLoading(true);
        setError(null);
        try {
            const res = await api.queryAssistant(q.trim());
            setAssistantResponse(res);
        } catch (err: any) {
            setError(`Assistant error: ${err.message}`);
        } finally {
            setAssistantLoading(false);
        }
    };

    const handleMemoryChatSubmit = async (e?: React.FormEvent, customP?: string) => {
        if (e) e.preventDefault();
        const prompt = customP || memoryChatPrompt;
        if (!prompt.trim()) return;
        setMemoryChatLoading(true);
        try {
            const res = await api.chatWithMemory(prompt.trim());
            setMemoryChatResponse(res);
        } catch (err: any) {
            alert(`Chat error: ${err.message}`);
        } finally {
            setMemoryChatLoading(false);
        }
    };

    const timelineTree = groupMemoriesByTimeline(memories);

    return (
        <div className="main-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Folder size={22} color="var(--primary-color)" /> Archive Explorer & Memory Engine
                </h2>
                <button
                    className="btn"
                    onClick={() => { loadStats(); loadRecords(); }}
                    disabled={loading}
                    style={{ fontSize: '12px', padding: '6px 12px' }}
                >
                    ↻ Refresh
                </button>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '20px' }}>
                Browse backed-up media, relive life events and stories, query with natural language, and inspect vault health.
            </p>

            {/* Stat Cards */}
            {stats && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '12px', marginBottom: '24px' }}>
                    {[
                        { label: 'Total Media', val: stats.total, color: 'var(--text-primary)' },
                        { label: 'Backed Up', val: stats.backed_up, color: 'var(--success-color)' },
                        { label: 'Ready', val: stats.ready, color: '#818cf8' },
                        { label: 'Pending', val: stats.pending, color: 'var(--warning-color)' },
                        { label: 'Failed', val: stats.failed, color: 'var(--error-color)' },
                    ].map(s => (
                        <div className="card" key={s.label} style={{ padding: '12px 16px', textAlign: 'center' }}>
                            <div style={{ fontSize: '22px', fontWeight: 700, color: s.color, lineHeight: 1.2 }}>{s.val}</div>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{s.label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* Main Tabs */}
            <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '20px' }}>
                {[
                    { id: 'recent', label: 'Recent Archive' },
                    { id: 'memories', label: '✨ Memories & Timeline' },
                    { id: 'autobiography', label: '📖 Autobiography ("My 2026")' },
                    { id: 'places', label: '📍 Places Visited' },
                    { id: 'search', label: 'Multi-Clause Search' },
                    { id: 'assistant', label: '💬 Ask Archive (AI)' },
                    { id: 'collections', label: '📚 Smart Collections' },
                    { id: 'analytics', label: '📊 Health & Relationships' },
                    { id: 'pending', label: 'Pending Uploads' },
                ].map(t => (
                    <button
                        key={t.id}
                        onClick={() => {
                            setTab(t.id as Tab);
                            setSelectedCollectionId(null);
                            setSearchParams(prev => {
                                const n = new URLSearchParams(prev);
                                n.set('tab', t.id);
                                return n;
                            });
                        }}
                        style={{
                            padding: '8px 16px',
                            border: 'none',
                            background: 'none',
                            borderBottom: tab === t.id ? '2px solid var(--primary-color)' : '2px solid transparent',
                            color: tab === t.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                            fontWeight: tab === t.id ? 600 : 400,
                            cursor: 'pointer',
                            fontSize: '13px',
                        }}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {/* TAB: MEMORIES & TIMELINE (Tasks 1, 2, 4) */}
            {tab === 'memories' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', marginBottom: '24px' }}>
                    {/* Memory Chat Panel */}
                    <div className="card" style={{ padding: '20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                            <MessageSquare size={20} color="var(--primary-color)" />
                            <div>
                                <h3 style={{ margin: 0, fontSize: '15px' }}>Memory Chat & Temporal Q&A</h3>
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                    Ask freeform temporal, relationship, and comparative questions about your archive.
                                </div>
                            </div>
                        </div>

                        <form onSubmit={e => handleMemoryChatSubmit(e)} style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                            <input
                                type="text"
                                placeholder="Ask: 'What did I do in 2026?' or 'Compare 2025 and 2026' or 'Who appears most with Bob?'..."
                                value={memoryChatPrompt}
                                onChange={e => setMemoryChatPrompt(e.target.value)}
                                style={{
                                    flex: 1,
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    border: '1px solid var(--border-color)',
                                    backgroundColor: 'var(--bg-color)',
                                    color: 'var(--text-primary)',
                                    fontSize: '13px'
                                }}
                            />
                            <button
                                type="submit"
                                className="btn btn-primary"
                                disabled={memoryChatLoading}
                                style={{ fontSize: '13px', padding: '10px 20px', display: 'flex', alignItems: 'center', gap: '6px' }}
                            >
                                <Sparkles size={14} /> {memoryChatLoading ? 'Reflecting…' : 'Ask Memory'}
                            </button>
                        </form>

                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                            <span>Try asking:</span>
                            {[
                                "What did I do in 2026?",
                                "Compare 2025 and 2026",
                                "Who appears most with Bob?",
                                "When was the last time I saw Alice?",
                                "Show my biggest trips"
                            ].map(q => (
                                <span
                                    key={q}
                                    onClick={() => {
                                        setMemoryChatPrompt(q);
                                        handleMemoryChatSubmit(undefined, q);
                                    }}
                                    style={{
                                        cursor: 'pointer',
                                        padding: '3px 8px',
                                        borderRadius: '4px',
                                        backgroundColor: 'var(--bg-color)',
                                        border: '1px solid var(--border-color)',
                                        color: 'var(--primary-color)'
                                    }}
                                >
                                    "{q}"
                                </span>
                            ))}
                        </div>

                        {memoryChatResponse && (
                            <div style={{
                                marginTop: '16px',
                                padding: '14px 18px',
                                borderRadius: '8px',
                                backgroundColor: 'rgba(99,102,241,0.08)',
                                border: '1px solid rgba(99,102,241,0.25)',
                                fontSize: '13px'
                            }}>
                                {memoryChatResponse.interpreted_intent && (
                                    <div style={{ fontSize: '11px', color: '#818cf8', fontWeight: 600, marginBottom: '6px' }}>
                                        🎯 Intent: Category "{memoryChatResponse.interpreted_intent.detected_category}" ({memoryChatResponse.interpreted_intent.confidence}% confidence)
                                    </div>
                                )}
                                <div style={{ color: 'var(--text-primary)', lineHeight: 1.5, marginBottom: '10px' }}>
                                    {memoryChatResponse.answer}
                                </div>
                                {memoryChatResponse.relevant_media.length > 0 && (
                                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                        {memoryChatResponse.relevant_media.map(m => (
                                            <span key={m.media_id} style={{
                                                padding: '3px 8px',
                                                borderRadius: '4px',
                                                backgroundColor: 'var(--card-bg)',
                                                border: '1px solid var(--border-color)',
                                                fontSize: '11px',
                                                color: '#818cf8'
                                            }}>
                                                📸 #{m.media_id} {m.filename}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Chronological Visual Memory Timeline (Task 2 / 6.5E.2) */}
                    <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                            <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Heart size={18} color="#f43f5e" /> Chronological Memory Timeline ({memories.length} Clustered Events)
                            </h3>
                        </div>

                        {memories.length === 0 ? (
                            <div className="card" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                                No life events clustered yet. As media is ingested with dates and faces, timeline memories will form automatically.
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                                {timelineTree.map(yGroup => (
                                    <div key={yGroup.year}>
                                        <div style={{
                                            fontSize: '16px',
                                            fontWeight: 800,
                                            color: 'var(--primary-color)',
                                            borderBottom: '2px solid rgba(99,102,241,0.2)',
                                            paddingBottom: '4px',
                                            marginBottom: '16px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px'
                                        }}>
                                            <Calendar size={18} /> {yGroup.year}
                                        </div>

                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', paddingLeft: '12px', borderLeft: '2px solid var(--border-color)' }}>
                                            {yGroup.months.map(mGroup => (
                                                <div key={mGroup.monthName} style={{ position: 'relative' }}>
                                                    <div style={{
                                                        fontSize: '13px',
                                                        fontWeight: 700,
                                                        color: 'var(--text-secondary)',
                                                        textTransform: 'uppercase',
                                                        letterSpacing: '0.05em',
                                                        marginBottom: '10px'
                                                    }}>
                                                        • {mGroup.monthName}
                                                    </div>

                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                                        {mGroup.events.map(ev => {
                                                            const isExpanded = expandedEventId === ev.event_id;
                                                            return (
                                                                <div 
                                                                    key={ev.event_id} 
                                                                    className="card"
                                                                    style={{
                                                                        padding: '16px',
                                                                        borderRadius: '8px',
                                                                        border: '1px solid var(--border-color)',
                                                                        backgroundColor: 'var(--card-bg)'
                                                                    }}
                                                                >
                                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                            <span style={{ fontWeight: 700, fontSize: '15px' }}>{ev.title}</span>
                                                                            {ev.event_confidence && (
                                                                                <span 
                                                                                    title={ev.confidence_reasons?.join(', ')}
                                                                                    style={{
                                                                                        fontSize: '10px',
                                                                                        fontWeight: 700,
                                                                                        padding: '2px 6px',
                                                                                        borderRadius: '4px',
                                                                                        backgroundColor: ev.event_confidence >= 80 ? 'rgba(34,197,94,0.15)' : 'rgba(234,179,8,0.15)',
                                                                                        color: ev.event_confidence >= 80 ? '#22c55e' : '#eab308',
                                                                                        display: 'flex',
                                                                                        alignItems: 'center',
                                                                                        gap: '3px'
                                                                                    }}
                                                                                >
                                                                                    <Award size={10} /> {ev.event_confidence}% Confidence
                                                                                </span>
                                                                            )}
                                                                        </div>
                                                                        <span style={{
                                                                            fontSize: '11px',
                                                                            fontWeight: 700,
                                                                            padding: '2px 8px',
                                                                            borderRadius: '4px',
                                                                            backgroundColor: 'rgba(99,102,241,0.15)',
                                                                            color: '#818cf8'
                                                                        }}>
                                                                            {ev.media_count} Assets
                                                                        </span>
                                                                    </div>

                                                                    <div style={{ fontSize: '12px', color: 'var(--text-primary)', lineHeight: 1.4, marginBottom: '10px' }}>
                                                                        {ev.narrative}
                                                                    </div>

                                                                    {/* Chips: Location + People */}
                                                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
                                                                        {ev.location && ev.location !== 'General' && (
                                                                            <span style={{
                                                                                fontSize: '11px',
                                                                                padding: '2px 8px',
                                                                                borderRadius: '4px',
                                                                                backgroundColor: 'var(--bg-color)',
                                                                                border: '1px solid var(--border-color)',
                                                                                color: 'var(--primary-color)',
                                                                                display: 'flex',
                                                                                alignItems: 'center',
                                                                                gap: '4px'
                                                                            }}>
                                                                                <MapPin size={11} /> {ev.location}
                                                                            </span>
                                                                        )}
                                                                        {ev.participants.map(p => (
                                                                            <span key={p} style={{
                                                                                fontSize: '11px',
                                                                                padding: '2px 8px',
                                                                                borderRadius: '4px',
                                                                                backgroundColor: 'var(--bg-color)',
                                                                                border: '1px solid var(--border-color)',
                                                                                color: '#a5b4fc',
                                                                                display: 'flex',
                                                                                alignItems: 'center',
                                                                                gap: '4px'
                                                                            }}>
                                                                                <Users size={11} /> {p}
                                                                            </span>
                                                                        ))}
                                                                    </div>

                                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--text-secondary)', borderTop: '1px solid var(--border-color)', paddingTop: '8px' }}>
                                                                        <span>{fmtDate(ev.start_date)}</span>
                                                                        <button 
                                                                            className="btn" 
                                                                            onClick={() => setExpandedEventId(isExpanded ? null : ev.event_id)}
                                                                            style={{ fontSize: '11px', padding: '3px 8px', display: 'flex', alignItems: 'center', gap: '4px' }}
                                                                        >
                                                                            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                                                                            {isExpanded ? 'Hide Items' : `View ${ev.media_ids.length} Photos`}
                                                                        </button>
                                                                    </div>

                                                                    {/* Expanded Media List */}
                                                                    {isExpanded && (
                                                                        <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px dashed var(--border-color)' }}>
                                                                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                                                                Media items in this memory:
                                                                            </div>
                                                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                                                                {ev.media_ids.map(mid => (
                                                                                    <span key={mid} style={{
                                                                                        padding: '3px 8px',
                                                                                        borderRadius: '4px',
                                                                                        backgroundColor: 'var(--bg-color)',
                                                                                        border: '1px solid var(--border-color)',
                                                                                        fontFamily: 'monospace',
                                                                                        fontSize: '11px'
                                                                                    }}>
                                                                                        #{mid}
                                                                                    </span>
                                                                                ))}
                                                                            </div>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* TAB: AUTOBIOGRAPHY ("MY 2026") */}
            {tab === 'autobiography' && autobiography && (
                <div style={{ marginBottom: '24px' }}>
                    <div className="card" style={{ padding: '24px', marginBottom: '20px', borderLeft: '4px solid var(--primary-color)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                            <BookOpen size={24} color="var(--primary-color)" />
                            <h2 style={{ margin: 0, fontSize: '18px' }}>{autobiography.book_title}</h2>
                        </div>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '14px' }}>
                            {autobiography.executive_summary}
                        </p>
                        <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                            <span>📸 <strong>{autobiography.total_photos_in_year}</strong> Photos Curated</span>
                            <span>📍 <strong>{autobiography.total_locations_visited}</strong> Destinations</span>
                            <span>👥 <strong>{autobiography.key_people.length}</strong> People Featured</span>
                        </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {autobiography.chapters.map(ch => (
                            <div key={ch.month_number} className="card" style={{ padding: '18px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                    <strong style={{ fontSize: '14px', color: 'var(--primary-color)' }}>{ch.chapter_title}</strong>
                                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{ch.photo_count} moments</span>
                                </div>
                                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5, margin: '0 0 10px 0' }}>
                                    {ch.narrative}
                                </p>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                    {ch.sample_photos.map((fn, idx) => (
                                        <span key={idx} style={{
                                            padding: '4px 8px',
                                            borderRadius: '4px',
                                            backgroundColor: 'var(--bg-color)',
                                            border: '1px solid var(--border-color)',
                                            fontSize: '11px'
                                        }}>
                                            📸 {fn}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* TAB: PLACES VISITED */}
            {tab === 'places' && placesHierarchy && (
                <div style={{ marginBottom: '24px' }}>
                    <div className="card" style={{ padding: '20px', marginBottom: '18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                            <Compass size={22} color="#06b6d4" />
                            <h3 style={{ margin: 0, fontSize: '16px' }}>Location Intelligence & Places Visited Frequency</h3>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                            Ranked geographical hierarchy of cities, regions, and travel frequency.
                        </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px' }}>
                        {placesHierarchy.top_visited_cities.map((plc, idx) => (
                            <div key={idx} className="card" style={{ padding: '16px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                                    <strong style={{ fontSize: '14px' }}>📍 {plc.city}</strong>
                                    <span style={{ fontSize: '11px', color: '#06b6d4', fontWeight: 700 }}>
                                        {plc.photo_count} photos
                                    </span>
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                                    {plc.country} • ~{plc.estimated_trips_count} visits
                                </div>
                                <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                                    First visit: {plc.first_visit?.slice(0, 10) || 'N/A'} • Last: {plc.last_visit?.slice(0, 10) || 'N/A'}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* TAB: SEARCH */}
            {tab === 'search' && (
                <div style={{ marginBottom: '20px' }}>
                    <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                        <input
                            id="archive-search-input"
                            type="text"
                            placeholder="Search multi-clause or semantic AI (e.g. 'sunset over beach', 'kids near water', 'documents from 2025')..."
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            style={{
                                flex: 1,
                                padding: '8px 14px',
                                borderRadius: '6px',
                                border: '1px solid var(--border-color)',
                                backgroundColor: 'var(--card-bg)',
                                color: 'var(--text-primary)',
                                fontSize: '13px',
                            }}
                        />
                        <button 
                            type="button" 
                            className="btn" 
                            onClick={async () => {
                                const q = searchQuery || "Show me my trips with Alice";
                                setSearchQuery(q);
                                const vRes = await api.executeVoiceQuery(q);
                                if (vRes && vRes.semantic_matches && vRes.semantic_matches.length > 0) {
                                    setRecords(vRes.semantic_matches.map((m: any) => ({
                                        id: m.media_id,
                                        file_name: m.filename,
                                        media_type: 'image',
                                        file_size_bytes: 1000,
                                        status: 'BACKED_UP',
                                        created_at: m.date_taken || '2026-08-25',
                                        location_label: m.location
                                    })));
                                } else {
                                    handleSearchSubmit();
                                }
                            }}
                            title="Voice Query / Speech Search"
                            style={{ padding: '8px 12px', fontSize: '12px' }}
                        >
                            🎤 Voice
                        </button>
                        <button type="submit" className="btn btn-primary" style={{ fontSize: '13px', padding: '8px 18px' }}>
                            Search
                        </button>
                    </form>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                        <span>Smart & Vision queries:</span>
                        {[
                            'sunset over beach',
                            'kids near water',
                            'documents from 2025',
                            'nature in Yosemite',
                            'grocery receipts'
                        ].map(q => (
                            <span
                                key={q}
                                onClick={() => {
                                    setSearchQuery(q);
                                    setSearchParams(prev => {
                                        const n = new URLSearchParams(prev);
                                        n.set('tab', 'search');
                                        n.set('q', q);
                                        return n;
                                    });
                                }}
                                style={{
                                    cursor: 'pointer',
                                    padding: '2px 8px',
                                    borderRadius: '4px',
                                    backgroundColor: 'var(--card-bg)',
                                    border: '1px solid var(--border-color)',
                                    color: 'var(--primary-color)'
                                }}
                            >
                                "{q}"
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* TAB: ASK ARCHIVE (AI ASSISTANT) */}
            {tab === 'assistant' && (
                <div style={{ marginBottom: '24px' }}>
                    <div className="card" style={{ padding: '20px', marginBottom: '20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                            <Sparkles size={20} color="#818cf8" />
                            <h3 style={{ margin: 0, fontSize: '15px' }}>Natural Language Archive Assistant</h3>
                        </div>
                        <form onSubmit={e => handleAssistantSubmit(e)} style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                            <input
                                type="text"
                                placeholder="Ask questions like 'Show my family trips in 2025' or 'Find receipts and invoices'..."
                                value={assistantQuery}
                                onChange={e => setAssistantQuery(e.target.value)}
                                style={{
                                    flex: 1,
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    border: '1px solid var(--border-color)',
                                    backgroundColor: 'var(--bg-color)',
                                    color: 'var(--text-primary)',
                                    fontSize: '13px'
                                }}
                            />
                            <button 
                                type="submit" 
                                className="btn btn-primary" 
                                disabled={assistantLoading}
                                style={{ fontSize: '13px', padding: '10px 20px', display: 'flex', alignItems: 'center', gap: '6px' }}
                            >
                                <Sparkles size={14} /> {assistantLoading ? 'Thinking…' : 'Ask Archive'}
                            </button>
                        </form>

                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                            <span>Try asking:</span>
                            {[
                                "Show my family trips in 2025",
                                "Find receipts and tax documents",
                                "Show photos of Alice",
                                "Show all video memories",
                                "Find screenshots with error dialogs"
                            ].map(q => (
                                <span
                                    key={q}
                                    onClick={() => {
                                        setAssistantQuery(q);
                                        handleAssistantSubmit(undefined, q);
                                    }}
                                    style={{
                                        cursor: 'pointer',
                                        padding: '3px 8px',
                                        borderRadius: '4px',
                                        backgroundColor: 'var(--bg-color)',
                                        border: '1px solid var(--border-color)',
                                        color: '#818cf8'
                                    }}
                                >
                                    "{q}"
                                </span>
                            ))}
                        </div>
                    </div>

                    {assistantResponse && (
                        <div style={{ marginBottom: '20px' }}>
                            <div style={{
                                padding: '14px 18px',
                                borderRadius: '8px',
                                backgroundColor: 'rgba(99,102,241,0.08)',
                                border: '1px solid rgba(99,102,241,0.25)',
                                marginBottom: '16px',
                                fontSize: '13px'
                            }}>
                                <div style={{ fontWeight: 600, color: '#818cf8', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <Sparkles size={14} /> Assistant Query Interpretation:
                                </div>
                                <div style={{ color: 'var(--text-primary)' }}>
                                    {assistantResponse.explanation} ({assistantResponse.total_results} matching media found)
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* TAB: SMART COLLECTIONS */}
            {tab === 'collections' && (
                <div style={{ marginBottom: '24px' }}>
                    {selectedCollectionId ? (
                        <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <button className="btn" onClick={() => setSelectedCollectionId(null)} style={{ fontSize: '12px', padding: '4px 10px' }}>
                                ← Back to Collections
                            </button>
                            <span style={{ fontWeight: 600, fontSize: '14px' }}>
                                {collections.find(c => c.id === selectedCollectionId)?.title}
                            </span>
                        </div>
                    ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '16px' }}>
                            {collections.map(col => (
                                <div 
                                    key={col.id} 
                                    className="card"
                                    onClick={() => setSelectedCollectionId(col.id)}
                                    style={{
                                        padding: '16px',
                                        cursor: 'pointer',
                                        transition: 'transform 0.15s ease, border-color 0.15s ease',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        justifyContent: 'space-between',
                                        height: '140px'
                                    }}
                                >
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                                            <div style={{ fontWeight: 700, fontSize: '14px' }}>
                                                {col.category === 'trips' ? '🗺️ ' :
                                                 col.category === 'people' ? '👤 ' :
                                                 col.category === 'documents' ? '📄 ' :
                                                 col.category === 'screenshots' ? '💻 ' :
                                                 col.category === 'videos' ? '🎬 ' : '📅 '}
                                                {col.title}
                                            </div>
                                            <span style={{
                                                fontSize: '10px',
                                                fontWeight: 700,
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                backgroundColor: 'rgba(99,102,241,0.15)',
                                                color: '#818cf8'
                                            }}>
                                                {col.badge}
                                            </span>
                                        </div>
                                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                            {col.description}
                                        </div>
                                    </div>
                                    <div style={{ fontSize: '11px', color: 'var(--primary-color)', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 600 }}>
                                        Browse album <ArrowRight size={12} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* TAB: HEALTH & RELATIONSHIPS (Tasks 5, 6) */}
            {tab === 'analytics' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginBottom: '24px' }}>
                    {/* 100-Point Archive Quality Scoreboard (Task 5 / 6.5E.5) */}
                    {qualityMetrics && (
                        <div className="card" style={{ padding: '20px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <ShieldCheck size={24} color="#22c55e" />
                                    <div>
                                        <h3 style={{ margin: 0, fontSize: '15px' }}>Archive Quality & AI-Readiness Health</h3>
                                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                            {qualityMetrics.readiness_label || `Your archive is ${qualityMetrics.overall_quality_score}% AI-ready`}
                                        </div>
                                    </div>
                                </div>
                                <div style={{ fontSize: '26px', fontWeight: 800, color: '#22c55e' }}>
                                    {qualityMetrics.overall_quality_score}%
                                </div>
                            </div>

                            {/* Breakdown meters */}
                            {qualityMetrics.score_breakdown && (
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginBottom: '16px' }}>
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                                            <span>Metadata</span>
                                            <strong>{qualityMetrics.score_breakdown.metadata}/20 pts</strong>
                                        </div>
                                        <div style={{ height: '5px', backgroundColor: 'var(--bg-color)', borderRadius: '999px', overflow: 'hidden' }}>
                                            <div style={{ width: `${(qualityMetrics.score_breakdown.metadata / 20) * 100}%`, height: '100%', backgroundColor: '#22c55e' }}></div>
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                                            <span>Faces</span>
                                            <strong>{qualityMetrics.score_breakdown.faces}/20 pts</strong>
                                        </div>
                                        <div style={{ height: '5px', backgroundColor: 'var(--bg-color)', borderRadius: '999px', overflow: 'hidden' }}>
                                            <div style={{ width: `${(qualityMetrics.score_breakdown.faces / 20) * 100}%`, height: '100%', backgroundColor: '#818cf8' }}></div>
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                                            <span>Scenes</span>
                                            <strong>{qualityMetrics.score_breakdown.scenes}/20 pts</strong>
                                        </div>
                                        <div style={{ height: '5px', backgroundColor: 'var(--bg-color)', borderRadius: '999px', overflow: 'hidden' }}>
                                            <div style={{ width: `${(qualityMetrics.score_breakdown.scenes / 20) * 100}%`, height: '100%', backgroundColor: '#f59e0b' }}></div>
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                                            <span>Locations</span>
                                            <strong>{qualityMetrics.score_breakdown.locations}/10 pts</strong>
                                        </div>
                                        <div style={{ height: '5px', backgroundColor: 'var(--bg-color)', borderRadius: '999px', overflow: 'hidden' }}>
                                            <div style={{ width: `${(qualityMetrics.score_breakdown.locations / 10) * 100}%`, height: '100%', backgroundColor: '#06b6d4' }}></div>
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                                            <span>Memories</span>
                                            <strong>{qualityMetrics.score_breakdown.memories}/20 pts</strong>
                                        </div>
                                        <div style={{ height: '5px', backgroundColor: 'var(--bg-color)', borderRadius: '999px', overflow: 'hidden' }}>
                                            <div style={{ width: `${(qualityMetrics.score_breakdown.memories / 20) * 100}%`, height: '100%', backgroundColor: '#ec4899' }}></div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Recommendations */}
                            {qualityMetrics.recommendations && qualityMetrics.recommendations.length > 0 && (
                                <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)', fontSize: '12px' }}>
                                    <strong style={{ color: '#818cf8' }}>💡 Actionable Recommendations:</strong>
                                    <ul style={{ margin: '4px 0 0 0', paddingLeft: '16px' }}>
                                        {qualityMetrics.recommendations.map((rec, i) => (
                                            <li key={i} style={{ color: 'var(--text-primary)' }}>{rec}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}

                    {/* People Profiles & Relationships (Task 6 / 6.5E.6) */}
                    {peopleProfiles.length > 0 && (
                        <div className="card" style={{ padding: '20px' }}>
                            <h3 style={{ margin: '0 0 14px 0', fontSize: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Users size={18} color="var(--primary-color)" /> People Profiles & Activity Timeline
                            </h3>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                                {peopleProfiles.map(p => (
                                    <div key={p.person_id} style={{
                                        padding: '12px',
                                        borderRadius: '6px',
                                        backgroundColor: 'var(--bg-color)',
                                        border: '1px solid var(--border-color)',
                                        fontSize: '12px'
                                    }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                            <strong style={{ fontSize: '13px' }}>👤 {p.display_name}</strong>
                                            <span style={{ fontSize: '10px', color: '#818cf8', fontWeight: 700 }}>{p.photo_count} Photos</span>
                                        </div>
                                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', marginBottom: '2px' }}>
                                            First seen: {p.first_seen ? p.first_seen.slice(0, 10) : '—'}
                                        </div>
                                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', marginBottom: '4px' }}>
                                            Last seen: {p.last_seen ? p.last_seen.slice(0, 10) : '—'}
                                        </div>
                                        {p.top_locations.length > 0 && (
                                            <div style={{ color: 'var(--primary-color)', fontSize: '11px' }}>
                                                📍 {p.top_locations.join(', ')}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Pairwise Relationship Interactions (Task 6 / 6.5E.6) */}
                    {relationshipData?.pairwise_relationships && relationshipData.pairwise_relationships.length > 0 && (
                        <div className="card" style={{ padding: '20px' }}>
                            <h3 style={{ margin: '0 0 14px 0', fontSize: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Network size={18} color="var(--primary-color)" /> Co-occurrence Relationship Network
                            </h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                {relationshipData.pairwise_relationships.map((rel, i) => (
                                    <div key={i} style={{
                                        padding: '10px 14px',
                                        borderRadius: '6px',
                                        backgroundColor: 'var(--bg-color)',
                                        border: '1px solid var(--border-color)',
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        fontSize: '12px'
                                    }}>
                                        <div>
                                            <strong>{rel.person_1}</strong> ⟷ <strong>{rel.person_2}</strong>
                                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                                                Interactions: {rel.first_interaction?.slice(0, 10)} to {rel.last_interaction?.slice(0, 10)}
                                            </div>
                                        </div>
                                        <span style={{
                                            fontSize: '11px',
                                            fontWeight: 700,
                                            padding: '3px 8px',
                                            borderRadius: '4px',
                                            backgroundColor: 'rgba(99,102,241,0.15)',
                                            color: '#818cf8'
                                        }}>
                                            {rel.shared_photos} Shared Photos
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Analytics Summary */}
                    {analytics && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
                            <div className="card" style={{ padding: '16px', textAlign: 'center' }}>
                                <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--primary-color)' }}>{analytics.summary.total_media}</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>TOTAL ASSETS</div>
                            </div>
                            <div className="card" style={{ padding: '16px', textAlign: 'center' }}>
                                <div style={{ fontSize: '24px', fontWeight: 700, color: '#22c55e' }}>{analytics.summary.total_size_mb} MB</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>TOTAL VAULT SIZE</div>
                            </div>
                            <div className="card" style={{ padding: '16px', textAlign: 'center' }}>
                                <div style={{ fontSize: '24px', fontWeight: 700, color: '#818cf8' }}>{analytics.summary.images_count} / {analytics.summary.videos_count}</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>PHOTOS / VIDEOS</div>
                            </div>
                            <div className="card" style={{ padding: '16px', textAlign: 'center' }}>
                                <div style={{ fontSize: '24px', fontWeight: 700, color: '#f59e0b' }}>{analytics.summary.unique_people_count}</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>IDENTIFIED PEOPLE</div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {error && (
                <div style={{ padding: '12px 16px', backgroundColor: 'rgba(218,54,51,0.1)', border: '1px solid var(--error-color)', borderRadius: '6px', color: 'var(--error-color)', fontSize: '13px', marginBottom: '16px' }}>
                    {error}
                </div>
            )}

            {/* Media Records Grid (Only show when not in analytics, memories, or top-level collections) */}
            {tab !== 'analytics' && tab !== 'memories' && !(tab === 'collections' && !selectedCollectionId) && (
                <div>
                    {loading ? (
                        <div style={{ textAlign: 'center', padding: '48px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                            Loading archive records…
                        </div>
                    ) : (tab === 'assistant' ? (assistantResponse?.results || []) : records).length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '48px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                            {tab === 'search' && !searchQuery ? 'Enter a search query above.' : 'No records found.'}
                        </div>
                    ) : (
                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        <th style={{ padding: '10px 14px' }}>ID</th>
                                        <th style={{ padding: '10px 14px' }}>Filename</th>
                                        <th style={{ padding: '10px 14px' }}>Status</th>
                                        <th style={{ padding: '10px 14px' }}>Faces</th>
                                        <th style={{ padding: '10px 14px' }}>Scene Tags</th>
                                        <th style={{ padding: '10px 14px' }}>Topic</th>
                                        <th style={{ padding: '10px 14px' }}>Discovered</th>
                                        <th style={{ padding: '10px 14px' }}>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(tab === 'assistant' ? (assistantResponse?.results || []) : records).map((r: any) => (
                                        <tr
                                            key={r.id}
                                            style={{ borderBottom: '1px solid var(--border-color)', cursor: 'pointer' }}
                                            onClick={() => setSelectedRecord(r)}
                                            onMouseEnter={e => (e.currentTarget.style.backgroundColor = 'var(--bg-color)')}
                                            onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
                                        >
                                            <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                                                #{r.id}
                                            </td>
                                            <td style={{ padding: '10px 14px', fontWeight: 600 }}>
                                                {r.original_filename}
                                            </td>
                                            <td style={{ padding: '10px 14px' }}>
                                                <span style={{
                                                    display: 'inline-block',
                                                    padding: '2px 8px',
                                                    borderRadius: '4px',
                                                    fontSize: '11px',
                                                    fontWeight: 600,
                                                    backgroundColor: `${STATUS_COLORS[r.status] || '#6b7280'}22`,
                                                    color: STATUS_COLORS[r.status] || '#6b7280',
                                                }}>
                                                    {r.status}
                                                </span>
                                            </td>
                                            <td style={{ padding: '10px 14px' }}>
                                                {r.faces && r.faces.length > 0 ? (
                                                    <span style={{ fontSize: '11px', color: 'var(--primary-color)' }}>
                                                        👤 {r.faces.length} face{r.faces.length > 1 ? 's' : ''}
                                                    </span>
                                                ) : '—'}
                                            </td>
                                            <td style={{ padding: '10px 14px' }}>
                                                {(r.scenes || r.labels) && (r.scenes || r.labels).length > 0 ? (
                                                    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                                                        {(r.scenes || r.labels).slice(0, 2).map((s: string, idx: number) => (
                                                            <span key={idx} style={{
                                                                padding: '1px 5px',
                                                                borderRadius: '3px',
                                                                backgroundColor: 'rgba(99, 102, 241, 0.15)',
                                                                color: '#a5b4fc',
                                                                fontSize: '10px',
                                                            }}>
                                                                #{s}
                                                            </span>
                                                        ))}
                                                    </div>
                                                ) : '—'}
                                            </td>
                                            <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontSize: '12px' }}>
                                                {r.topic ?? '—'}
                                            </td>
                                            <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontSize: '11px' }}>
                                                {fmtDate(r.created_at || r.date_taken)}
                                            </td>
                                            <td style={{ padding: '10px 14px' }}>
                                                <button
                                                    className="btn"
                                                    style={{ fontSize: '11px', padding: '3px 8px' }}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setSelectedRecord(r);
                                                    }}
                                                >
                                                    Inspect
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* Detail Modal */}
            {selectedRecord && (
                <RecordDetail
                    record={selectedRecord}
                    onClose={() => setSelectedRecord(null)}
                    onRecordUpdated={(updated) => {
                        setRecords(prev => prev.map(rec => rec.id === updated.id ? updated : rec));
                    }}
                />
            )}
        </div>
    );
};
