import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, type IngestResult, type QueueStatus, type ImportRecord } from '../services/api';
import { Inbox, History, RefreshCw, ArrowUpRight } from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────

interface PendingFile {
    file: File;
    state: 'pending' | 'uploading' | 'done' | 'error';
    result?: IngestResult;
    error?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtBytes(b: number | undefined | null) {
    if (!b || b === 0) return '0 B';
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(iso: string) {
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
}

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.webp']);
const VIDEO_EXTS = new Set(['.mp4', '.mov', '.mkv', '.webm']);

function classify(name: string) {
    const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
    if (IMAGE_EXTS.has(ext)) return 'image';
    if (VIDEO_EXTS.has(ext)) return 'video';
    return 'unknown';
}

function renderPipelineBadge(status?: string) {
    switch (status) {
        case 'BACKED_UP':
            return <span className="badge" style={{ backgroundColor: 'var(--success-color)', fontSize: '10px' }}>✓ ARCHIVED</span>;
        case 'ANALYZING':
            return <span className="badge" style={{ backgroundColor: '#a855f7', color: '#fff', fontSize: '10px' }}>🔍 ANALYZING</span>;
        case 'READY':
        case 'READY_TO_UPLOAD':
            return <span className="badge" style={{ backgroundColor: 'var(--primary-color)', fontSize: '10px' }}>⚡ READY</span>;
        case 'UPLOADING':
            return <span className="badge" style={{ backgroundColor: '#3b82f6', color: '#fff', fontSize: '10px' }}>📤 UPLOADING</span>;
        case 'DISCOVERED':
        case 'RESERVED':
            return <span className="badge" style={{ backgroundColor: '#eab308', color: '#000', fontSize: '10px' }}>SCANNING</span>;
        case 'WAITING':
        default:
            return <span className="badge" style={{ backgroundColor: 'var(--text-secondary)', fontSize: '10px' }}>WAITING IN QUEUE</span>;
    }
}

// ── Component ──────────────────────────────────────────────────────────────

export const QueueIngest: React.FC = () => {
    const [activeTab, setActiveTab] = useState<'queue' | 'history'>('queue');
    const [queue, setQueue] = useState<PendingFile[]>([]);
    const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
    const [importHistory, setImportHistory] = useState<ImportRecord[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [dragging, setDragging] = useState(false);
    const [statusError, setStatusError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const navigate = useNavigate();

    const loadStatus = useCallback(async () => {
        try {
            const s = await api.getQueueStatus();
            setQueueStatus(s);
            setStatusError(null);
        } catch (e: any) {
            setStatusError(e.message);
        }
    }, []);

    const loadHistory = useCallback(async () => {
        setHistoryLoading(true);
        try {
            const h = await api.getImports(100, 0);
            setImportHistory(h);
        } catch (err) {
            console.error('Failed to load import history:', err);
        } finally {
            setHistoryLoading(false);
        }
    }, []);

    useEffect(() => {
        loadStatus();
        const id = setInterval(loadStatus, 5000);
        return () => clearInterval(id);
    }, [loadStatus]);

    useEffect(() => {
        if (activeTab === 'history') {
            loadHistory();
        }
    }, [activeTab, loadHistory]);

    const addFiles = useCallback((files: FileList | File[]) => {
        const arr = Array.from(files);
        setQueue(prev => [
            ...prev,
            ...arr.map(f => ({ file: f, state: 'pending' as const }))
        ]);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragging(false);
        addFiles(e.dataTransfer.files);
    }, [addFiles]);

    const handleUpload = async () => {
        const pendingFiles = queue.filter(q => q.state === 'pending');
        if (pendingFiles.length === 0) return;

        for (const pf of pendingFiles) {
            setQueue(prev => prev.map(q =>
                q.file === pf.file ? { ...q, state: 'uploading' } : q
            ));
            try {
                const [result] = await api.ingestFiles([pf.file]);
                const isErr = result.status === 'INVALID_MEDIA' || result.status === 'IMPORT_FAILED';
                setQueue(prev => prev.map(q =>
                    q.file === pf.file ? {
                        ...q,
                        state: isErr ? 'error' : 'done',
                        result,
                        error: result.error
                    } : q
                ));
            } catch (e: any) {
                setQueue(prev => prev.map(q =>
                    q.file === pf.file ? { ...q, state: 'error', error: e.message } : q
                ));
            }
        }
        loadStatus();
        if (activeTab === 'history') loadHistory();
    };

    const removeFile = (f: File) => {
        setQueue(prev => prev.filter(q => q.file !== f));
    };

    const clearDone = () => setQueue(prev => prev.filter(q => q.state !== 'done'));
    const hasPending = queue.some(q => q.state === 'pending');

    return (
        <div className="main-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div>
                    <h2 style={{ marginBottom: '4px' }}>Queue & Ingestion Hub</h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
                        Staged, verified media ingestion with full operational history. Source files are never modified.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn" onClick={() => { loadStatus(); if (activeTab === 'history') loadHistory(); }} style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <RefreshCw size={13} /> Refresh
                    </button>
                </div>
            </div>

            {/* Navigation Sub-Tabs */}
            <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '24px' }}>
                <button
                    onClick={() => setActiveTab('queue')}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '8px 16px',
                        border: 'none',
                        background: 'none',
                        borderBottom: activeTab === 'queue' ? '2px solid var(--primary-color)' : '2px solid transparent',
                        color: activeTab === 'queue' ? 'var(--text-primary)' : 'var(--text-secondary)',
                        fontWeight: activeTab === 'queue' ? 600 : 400,
                        cursor: 'pointer',
                        fontSize: '13px'
                    }}
                >
                    <Inbox size={15} /> Current Queue & Upload
                </button>
                <button
                    onClick={() => setActiveTab('history')}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '8px 16px',
                        border: 'none',
                        background: 'none',
                        borderBottom: activeTab === 'history' ? '2px solid var(--primary-color)' : '2px solid transparent',
                        color: activeTab === 'history' ? 'var(--text-primary)' : 'var(--text-secondary)',
                        fontWeight: activeTab === 'history' ? 600 : 400,
                        cursor: 'pointer',
                        fontSize: '13px'
                    }}
                >
                    <History size={15} /> Import History ({importHistory.length})
                </button>
            </div>

            {activeTab === 'queue' ? (
                <>
                    {/* Current Queue Status Summary */}
                    <div style={{ display: 'flex', gap: '16px', marginBottom: '28px' }}>
                        <div className="card" style={{ flex: 1, padding: '16px 20px' }}>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--primary-color)' }}>
                                {queueStatus?.images ?? '—'}
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>Images in Incoming Queue</div>
                        </div>
                        <div className="card" style={{ flex: 1, padding: '16px 20px' }}>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--primary-color)' }}>
                                {queueStatus?.videos ?? '—'}
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>Videos in Incoming Queue</div>
                        </div>
                    </div>

                    {statusError && (
                        <div style={{ padding: '10px 14px', backgroundColor: 'rgba(218,54,51,0.1)', border: '1px solid var(--error-color)', borderRadius: '6px', color: 'var(--error-color)', fontSize: '13px', marginBottom: '20px' }}>
                            Could not read queue status: {statusError}
                        </div>
                    )}

                    {/* Drop Zone */}
                    <div
                        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                        onDragLeave={() => setDragging(false)}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                        style={{
                            border: `2px dashed ${dragging ? 'var(--primary-color)' : 'var(--border-color)'}`,
                            borderRadius: '12px',
                            padding: '44px 32px',
                            textAlign: 'center',
                            cursor: 'pointer',
                            backgroundColor: dragging ? 'rgba(99,102,241,0.06)' : 'var(--surface-color)',
                            transition: 'all 0.2s',
                            marginBottom: '24px',
                        }}
                    >
                        <div style={{ fontSize: '38px', marginBottom: '10px' }}>📥</div>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            Drop media here to stage and import
                        </div>
                        <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                            or click to browse — JPG, PNG, WEBP, MP4, MOV, MKV, WebM
                        </div>
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.mkv,.webm"
                            style={{ display: 'none' }}
                            onChange={(e) => e.target.files && addFiles(e.target.files)}
                        />
                    </div>

                    {/* Staged Files Table */}
                    {queue.length > 0 && (
                        <div className="card" style={{ marginBottom: '24px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                                <h3 style={{ margin: 0, fontSize: '15px' }}>Upload Batch ({queue.length})</h3>
                                <div style={{ display: 'flex', gap: '8px' }}>
                                    <button className="btn" onClick={clearDone} style={{ fontSize: '12px' }}>Clear Completed</button>
                                    <button
                                        className="btn btn-primary"
                                        onClick={handleUpload}
                                        disabled={!hasPending}
                                        style={{ fontSize: '12px' }}
                                    >
                                        Ingest {queue.filter(q => q.state === 'pending').length} File{queue.filter(q => q.state === 'pending').length !== 1 ? 's' : ''}
                                    </button>
                                </div>
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                {queue.map((pf, i) => {
                                    const kind = classify(pf.file.name);
                                    const icon = kind === 'image' ? '🖼' : kind === 'video' ? '🎬' : '📄';
                                    const res = pf.result;
                                    return (
                                        <div key={i} style={{
                                            display: 'flex',
                                            flexDirection: 'column',
                                            gap: '6px',
                                            padding: '12px 14px',
                                            borderRadius: '8px',
                                            backgroundColor: 'var(--bg-color)',
                                            border: '1px solid var(--border-color)',
                                        }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                                <span style={{ fontSize: '20px' }}>{icon}</span>
                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                    <div style={{ fontWeight: 500, fontSize: '13px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                        {res?.filename || pf.file.name}
                                                    </div>
                                                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', gap: '10px', alignItems: 'center' }}>
                                                        <span>{fmtBytes(res?.size_bytes || pf.file.size)}</span>
                                                        {res?.sha256_prefix && (
                                                            <span style={{ fontFamily: 'monospace', opacity: 0.8 }}>
                                                                sha256:{res.sha256_prefix}…
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Status Badge */}
                                                {pf.state === 'uploading' && (
                                                    <span className="badge" style={{ backgroundColor: 'var(--warning-color)', fontSize: '10px' }}>
                                                        ⏳ Staging & Hashing…
                                                    </span>
                                                )}
                                                {pf.state === 'pending' && (
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                        <span className="badge" style={{ backgroundColor: 'var(--text-secondary)', fontSize: '10px' }}>Pending</span>
                                                        <button
                                                            onClick={() => removeFile(pf.file)}
                                                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '16px' }}
                                                        >✕</button>
                                                    </div>
                                                )}
                                                {res?.status === 'IMPORT_COMPLETE' && (
                                                    <span className="badge" style={{ backgroundColor: 'var(--success-color)', fontSize: '10px' }}>
                                                        ✓ IMPORTED
                                                    </span>
                                                )}
                                                {res?.status === 'ARCHIVE_DUPLICATE' && (
                                                    <span className="badge" style={{ backgroundColor: '#eab308', color: '#000', fontSize: '10px', fontWeight: 600 }}>
                                                        ⚠️ EXACT DUPLICATE (ARCHIVED)
                                                    </span>
                                                )}
                                                {res?.status === 'QUEUE_DUPLICATE' && (
                                                    <span className="badge" style={{ backgroundColor: '#eab308', color: '#000', fontSize: '10px', fontWeight: 600 }}>
                                                        ⚠️ DUPLICATE IN QUEUE
                                                    </span>
                                                )}
                                                {res?.status === 'INVALID_MEDIA' && (
                                                    <span className="badge" style={{ backgroundColor: 'var(--error-color)', fontSize: '10px' }}>
                                                        ✕ INVALID MEDIA
                                                    </span>
                                                )}
                                                {res?.status === 'IMPORT_FAILED' && (
                                                    <span className="badge" style={{ backgroundColor: 'var(--error-color)', fontSize: '10px' }}>
                                                        ✕ FAILED
                                                    </span>
                                                )}
                                            </div>

                                            {/* Detailed duplicate banner */}
                                            {res?.status === 'ARCHIVE_DUPLICATE' && (
                                                <div style={{
                                                    marginTop: '6px',
                                                    padding: '8px 12px',
                                                    borderRadius: '6px',
                                                    backgroundColor: 'rgba(234, 179, 8, 0.1)',
                                                    border: '1px solid rgba(234, 179, 8, 0.3)',
                                                    fontSize: '12px',
                                                    display: 'flex',
                                                    justifyContent: 'space-between',
                                                    alignItems: 'center'
                                                }}>
                                                    <div>
                                                        <strong>Already in Archive:</strong> Media ID #{res.existing_media_id} ({res.existing_state})
                                                        {res.existing_route && ` | Route: ${res.existing_route}`}
                                                        {res.existing_preview_id && ` | Preview Msg: ${res.existing_preview_id}`}
                                                    </div>
                                                    <button
                                                        className="btn"
                                                        style={{ fontSize: '11px', padding: '3px 8px' }}
                                                        onClick={() => navigate(`/archive?q=${res.sha256_prefix}`)}
                                                    >
                                                        View in Archive →
                                                    </button>
                                                </div>
                                            )}

                                            {res?.status === 'QUEUE_DUPLICATE' && (
                                                <div style={{
                                                    marginTop: '6px',
                                                    padding: '6px 12px',
                                                    borderRadius: '6px',
                                                    backgroundColor: 'rgba(234, 179, 8, 0.1)',
                                                    border: '1px solid rgba(234, 179, 8, 0.3)',
                                                    fontSize: '12px',
                                                }}>
                                                    <strong>Already waiting in Incoming queue:</strong> {res.destination || res.filename}
                                                </div>
                                            )}

                                            {(pf.error || res?.error) && (
                                                <div style={{ fontSize: '11px', color: 'var(--error-color)', marginTop: '4px' }}>
                                                    {pf.error || res?.error}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Current Queue Contents with Pipeline Stage Badges */}
                    {queueStatus && (queueStatus.image_files.length > 0 || queueStatus.video_files.length > 0) && (
                        <div className="card">
                            <h3 style={{ marginBottom: '16px', fontSize: '15px' }}>Incoming Queue Pipeline Status</h3>
                            {queueStatus.image_files.length > 0 && (
                                <div style={{ marginBottom: '16px' }}>
                                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.05em' }}>
                                        Images ({queueStatus.images})
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                        {queueStatus.image_files.map((f, i) => (
                                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', padding: '8px 12px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                    <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>🖼 {f.filename}</span>
                                                    <span style={{ color: 'var(--text-secondary)' }}>{fmtBytes(f.size_bytes)}</span>
                                                </div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                    {renderPipelineBadge(f.pipeline_status)}
                                                    <span style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>{fmtDate(f.modified_at)}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {queueStatus.video_files.length > 0 && (
                                <div>
                                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.05em' }}>
                                        Videos ({queueStatus.videos})
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                        {queueStatus.video_files.map((f, i) => (
                                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', padding: '8px 12px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                    <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>🎬 {f.filename}</span>
                                                    <span style={{ color: 'var(--text-secondary)' }}>{fmtBytes(f.size_bytes)}</span>
                                                </div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                    {renderPipelineBadge(f.pipeline_status)}
                                                    <span style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>{fmtDate(f.modified_at)}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </>
            ) : (
                /* Import History Tab */
                <div className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <h3 style={{ margin: 0, fontSize: '15px' }}>Historical Control Center Uploads</h3>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Showing last 100 uploads</span>
                    </div>

                    {historyLoading ? (
                        <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-secondary)' }}>Loading history…</div>
                    ) : importHistory.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-secondary)' }}>No uploads recorded yet.</div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {importHistory.map(item => (
                                <div key={item.id} style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    backgroundColor: 'var(--bg-color)',
                                    border: '1px solid var(--border-color)',
                                    fontSize: '12px'
                                }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                        <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                                            <span>{item.media_type === 'video' ? '🎬' : '🖼'}</span>
                                            <span>{item.filename}</span>
                                            {item.original_filename !== item.filename && (
                                                <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>(was {item.original_filename})</span>
                                            )}
                                        </div>
                                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', gap: '12px' }}>
                                            <span>Size: {fmtBytes(item.size_bytes)}</span>
                                            {item.sha256 && (
                                                <span style={{ fontFamily: 'monospace' }}>SHA: {item.sha256.slice(0, 16)}…</span>
                                            )}
                                            <span>{fmtDate(item.created_at)}</span>
                                        </div>
                                    </div>

                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                        {item.status === 'COMPLETE' && (
                                            <span className="badge" style={{ backgroundColor: 'var(--success-color)', fontSize: '10px' }}>✓ COMPLETE</span>
                                        )}
                                        {item.status === 'DUPLICATE' && (
                                            <span className="badge" style={{ backgroundColor: '#eab308', color: '#000', fontSize: '10px' }}>DUPLICATE</span>
                                        )}
                                        {item.status === 'INVALID_MEDIA' && (
                                            <span className="badge" style={{ backgroundColor: 'var(--error-color)', fontSize: '10px' }}>INVALID</span>
                                        )}
                                        {item.status === 'FAILED' && (
                                            <span className="badge" style={{ backgroundColor: 'var(--error-color)', fontSize: '10px' }}>FAILED</span>
                                        )}
                                        {item.sha256 && item.status === 'COMPLETE' && (
                                            <button 
                                                className="btn" 
                                                style={{ padding: '2px 8px', fontSize: '11px' }}
                                                onClick={() => navigate(`/archive?q=${item.sha256?.slice(0, 16)}`)}
                                                title="View in Archive"
                                            >
                                                <ArrowUpRight size={12} />
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
