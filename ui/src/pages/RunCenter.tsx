import { useEffect, useState } from 'react';
import { api, type CommandProfile, type JobSummary } from '../services/api';
import { useJobContext } from '../contexts/JobContext';
import { ShieldCheck, AlertTriangle } from 'lucide-react';

// ── Risk badge colors ──────────────────────────────────────────────────────

const RISK_COLORS: Record<string, { bg: string; text: string }> = {
    SAFE:        { bg: 'rgba(34,197,94,0.15)',  text: '#22c55e' },
    CONTROLLED:  { bg: 'rgba(234,179,8,0.15)',  text: '#ca8a04' },
    LIVE:        { bg: 'rgba(239,68,68,0.15)',  text: '#ef4444' },
    'HIGH RISK': { bg: 'rgba(239,68,68,0.2)',   text: '#ef4444' },
};

const CATEGORY_ICONS: Record<string, string> = {
    PIPELINE:    '🚀',
    LIVE:        '📡',
    TEST:        '🧪',
    'READ-ONLY': '🔍',
    DIAGNOSTICS: '⚙️',
    MAINTENANCE: '🛠',
};

function fmtDuration(d: number | null) {
    if (d === null || d === undefined) return '';
    if (d < 60) return `${d.toFixed(1)}s`;
    return `${Math.floor(d / 60)}m ${(d % 60).toFixed(0)}s`;
}

function fmtRelative(iso: string | null) {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

// ── Confirm Dialog ─────────────────────────────────────────────────────────

const ConfirmDialog: React.FC<{
    profile: CommandProfile;
    onConfirm: () => void;
    onCancel: () => void;
}> = ({ profile, onConfirm, onCancel }) => (
    <div style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        backgroundColor: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '24px',
    }} onClick={onCancel}>
        <div
            className="card"
            style={{ maxWidth: '420px', width: '100%', padding: '28px' }}
            onClick={e => e.stopPropagation()}
        >
            <div style={{ fontSize: '32px', textAlign: 'center', marginBottom: '12px' }}>⚠️</div>
            <h3 style={{ margin: 0, marginBottom: '8px', textAlign: 'center' }}>Confirm Live Execution</h3>
            <p style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '20px' }}>
                <strong style={{ color: 'var(--text-primary)' }}>{profile.display_name}</strong> will interact with your real Telegram group and upload media.
            </p>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-color)', padding: '12px', borderRadius: '6px', marginBottom: '24px' }}>
                {profile.description}
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
                <button className="btn" onClick={onCancel} style={{ flex: 1 }}>Cancel</button>
                <button
                    className="btn btn-primary"
                    onClick={onConfirm}
                    style={{ flex: 1, backgroundColor: '#ef4444', borderColor: '#ef4444' }}
                >
                    Run Anyway
                </button>
            </div>
        </div>
    </div>
);

// ── Main Component ─────────────────────────────────────────────────────────

export const RunCenter: React.FC = () => {
    const [profiles, setProfiles] = useState<CommandProfile[]>([]);
    const [recentJobs, setRecentJobs] = useState<JobSummary[]>([]);
    const [systemMode, setSystemMode] = useState<'safe' | 'production'>('safe');
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const [confirmProfile, setConfirmProfile] = useState<CommandProfile | null>(null);
    const { startJob } = useJobContext();

    const loadData = () => {
        api.getProfiles().then(setProfiles).catch(console.error);
        api.getJobs().then(jobs => setRecentJobs(jobs.slice(0, 50))).catch(console.error);
        api.getSystemMode().then(r => setSystemMode(r.mode === 'production' ? 'production' : 'safe')).catch(console.error);
    };

    useEffect(() => {
        loadData();
        const id = setInterval(loadData, 5000);
        return () => clearInterval(id);
    }, []);

    // Map profile_id -> most recent job run
    const lastRunByProfile = recentJobs.reduce((acc, j) => {
        if (!acc[j.profile_id]) acc[j.profile_id] = j;
        return acc;
    }, {} as Record<string, JobSummary>);

    const handleRun = async (profile: CommandProfile) => {
        if (profile.risk_level === 'LIVE' || profile.risk_level === 'HIGH RISK') {
            if (systemMode === 'safe') {
                setErrorMsg(`Safe Mode is active: Switch to Production Mode in the top-left sidebar to run "${profile.display_name}".`);
                return;
            }
            setConfirmProfile(profile);
            return;
        }
        await doRun(profile.id);
    };

    const doRun = async (profileId: string) => {
        setConfirmProfile(null);
        try {
            setErrorMsg(null);
            await startJob(profileId);
        } catch (e: any) {
            setErrorMsg(e.message || 'Failed to start job.');
        }
    };

    const grouped = profiles.reduce((acc, p) => {
        const cat = p.category || 'OTHER';
        if (!acc[cat]) acc[cat] = [];
        acc[cat].push(p);
        return acc;
    }, {} as Record<string, CommandProfile[]>);

    const categoryOrder = ['PIPELINE', 'LIVE', 'TEST', 'READ-ONLY', 'DIAGNOSTICS', 'MAINTENANCE'];
    const sortedCategories = [
        ...categoryOrder.filter(c => grouped[c]),
        ...Object.keys(grouped).filter(c => !categoryOrder.includes(c)),
    ];

    return (
        <div className="main-content">
            {confirmProfile && (
                <ConfirmDialog
                    profile={confirmProfile}
                    onConfirm={() => doRun(confirmProfile.id)}
                    onCancel={() => setConfirmProfile(null)}
                />
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <h2 style={{ margin: 0 }}>Run Center</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: systemMode === 'production' ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
                    {systemMode === 'production' ? <AlertTriangle size={14} /> : <ShieldCheck size={14} />}
                    {systemMode === 'production' ? 'Production Mode Active' : 'Safe Mode Active'}
                </div>
            </div>
            
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '24px' }}>
                Launch controlled jobs against the archive environment. LIVE actions require Production Mode confirmation.
            </p>

            {errorMsg && (
                <div id="run-center-error" style={{ padding: '12px 16px', backgroundColor: 'rgba(218,54,51,0.1)', border: '1px solid var(--error-color)', borderRadius: '6px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--error-color)', fontWeight: 500 }}>{errorMsg}</span>
                    <button onClick={() => setErrorMsg(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '16px' }}>✕</button>
                </div>
            )}

            {/* Pipeline warning / safe mode notice */}
            {systemMode === 'safe' && (
                <div style={{ padding: '10px 14px', backgroundColor: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.25)', borderRadius: '6px', marginBottom: '24px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                    🟢 <strong style={{ color: 'var(--text-primary)' }}>Safe Mode Active</strong>: Dry runs, DB backups, diagnostics, and test suites can be executed freely. Live Telegram operations are locked.
                </div>
            )}

            {sortedCategories.map((category) => (
                <div key={category} style={{ marginBottom: '32px' }}>
                    <h3 style={{ marginBottom: '16px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontSize: '11px', letterSpacing: '0.08em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span>{CATEGORY_ICONS[category] || '▸'}</span>
                        <span>{category}</span>
                    </h3>
                    <div className="grid">
                        {grouped[category].map(p => {
                            const isLive = p.risk_level === 'LIVE' || p.risk_level === 'HIGH RISK';
                            const risk = RISK_COLORS[p.risk_level] || { bg: 'rgba(255,255,255,0.05)', text: 'var(--text-secondary)' };
                            const lastRun = lastRunByProfile[p.id];
                            return (
                                <div className="card" key={p.id} style={{ display: 'flex', flexDirection: 'column' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                                        <h3 style={{ margin: 0, fontSize: '14px' }}>{p.display_name}</h3>
                                        <span style={{
                                            fontSize: '10px',
                                            fontWeight: 700,
                                            padding: '2px 8px',
                                            borderRadius: '999px',
                                            backgroundColor: risk.bg,
                                            color: risk.text,
                                            whiteSpace: 'nowrap',
                                            letterSpacing: '0.04em',
                                        }}>{p.risk_level}</span>
                                    </div>
                                    <p style={{ marginBottom: 'auto', color: 'var(--text-secondary)', fontSize: '12px', lineHeight: '1.5' }}>{p.description}</p>
                                    <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                            {lastRun ? (
                                                <span title={lastRun.finished_at}>
                                                    Last: <span style={{ color: lastRun.status === 'PASSED' ? 'var(--success-color)' : lastRun.status === 'FAILED' ? 'var(--error-color)' : 'var(--text-secondary)' }}>
                                                        {lastRun.status}
                                                    </span> {fmtRelative(lastRun.finished_at)} {lastRun.duration ? `(${fmtDuration(lastRun.duration)})` : ''}
                                                </span>
                                            ) : (
                                                <span style={{ opacity: 0.5 }}>Never run</span>
                                            )}
                                        </div>
                                        <button
                                            id={`run-btn-${p.id}`}
                                            className="btn btn-primary"
                                            onClick={() => handleRun(p)}
                                            style={{
                                                fontSize: '12px',
                                                padding: '6px 14px',
                                                ...(isLive ? { backgroundColor: '#ef4444', borderColor: '#ef4444' } : {})
                                            }}
                                        >
                                            {isLive ? '⚡ Run Live' : 'Run Job'}
                                        </button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            ))}
        </div>
    );
};
