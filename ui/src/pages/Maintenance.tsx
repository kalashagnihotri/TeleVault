import React, { useEffect, useState } from 'react';
import { 
    api, 
    type FailureOverviewResponse, 
    type StorageBreakdownResponse, 
    type ConfigVersionItem, 
    type MarketplacePluginItem 
} from '../services/api';
import { 
    Wrench, 
    Archive, 
    RefreshCw, 
    CheckCircle2, 
    AlertTriangle, 
    Play, 
    HardDrive, 
    RotateCcw, 
    Sliders, 
    ShoppingBag,
    ShieldCheck,
    Database
} from 'lucide-react';

export const Maintenance: React.FC = () => {
    const [creatingSnapshot, setCreatingSnapshot] = useState(false);
    const [loading, setLoading] = useState(true);
    const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    // States
    const [scanningIntegrity, setScanningIntegrity] = useState(false);
    const [runningRestoreTest, setRunningRestoreTest] = useState(false);
    const [failures, setFailures] = useState<FailureOverviewResponse | null>(null);
    const [storageInfo, setStorageInfo] = useState<StorageBreakdownResponse | null>(null);
    const [configHistory, setConfigHistory] = useState<ConfigVersionItem[]>([]);
    const [marketplace, setMarketplace] = useState<MarketplacePluginItem[]>([]);
    const [retryingFailures, setRetryingFailures] = useState(false);

    const loadData = async () => {
        setLoading(true);
        try {
            const [fail, stor, cfg, mkt] = await Promise.all([
                api.getFailureOverview().catch(() => null),
                api.getStorageBreakdown().catch(() => null),
                api.getConfigHistory().catch(() => []),
                api.listMarketplacePlugins().catch(() => [])
            ]);
            setFailures(fail);
            setStorageInfo(stor);
            setConfigHistory(cfg);
            setMarketplace(mkt);
        } catch (err: any) {
            console.error('Failed to load maintenance data:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    const handleCreateSnapshot = async () => {
        setCreatingSnapshot(true);
        setStatusMsg(null);
        try {
            const snap = await api.createSnapshot();
            setStatusMsg({ type: 'success', text: `✓ Created full system snapshot: ${snap.filename}` });
            loadData();
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Failed to create snapshot: ${err.message}` });
        } finally {
            setCreatingSnapshot(false);
        }
    };

    const handleRunIntegrityScan = async () => {
        setScanningIntegrity(true);
        try {
            const rep = await api.runIntegrityScan();
            setStatusMsg({ 
                type: rep.status === 'HEALTHY' ? 'success' : 'error', 
                text: `Integrity scan completed: ${rep.total_files_audited} files checked, score ${rep.integrity_score_pct}%.` 
            });
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Integrity scan failed: ${err.message}` });
        } finally {
            setScanningIntegrity(false);
        }
    };

    const handleRunRestoreTest = async () => {
        setRunningRestoreTest(true);
        try {
            const res = await api.runAutomatedBackupVerification();
            setStatusMsg({ 
                type: res.status === 'PASSED' ? 'success' : 'error', 
                text: `Sandbox Restore Test: ${res.message} (Confidence: ${res.backup_confidence_score}%)` 
            });
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Restore test failed: ${err.message}` });
        } finally {
            setRunningRestoreTest(false);
        }
    };

    const handleRetryAllFailures = async () => {
        setRetryingFailures(true);
        try {
            const res = await api.retryAllFailed();
            setStatusMsg({ type: 'success', text: `✓ ${res.message}` });
            loadData();
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Retry failed: ${err.message}` });
        } finally {
            setRetryingFailures(false);
        }
    };

    const handleRollbackConfig = async (versionId: number) => {
        if (!confirm(`Are you sure you want to rollback to configuration version #${versionId}?`)) return;
        try {
            const res = await api.rollbackConfig(versionId);
            setStatusMsg({ type: 'success', text: `✓ Configuration rolled back to #${versionId} (new version #${res.new_version_id}).` });
            loadData();
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Rollback failed: ${err.message}` });
        }
    };

    const handleInstallPlugin = async (pluginId: string) => {
        try {
            const res = await api.installMarketplacePlugin(pluginId);
            setStatusMsg({ type: 'success', text: `✓ ${res.message}` });
            loadData();
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Plugin install failed: ${err.message}` });
        }
    };

    return (
        <div className="main-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div>
                    <h2 style={{ marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Wrench size={22} color="var(--primary-color)" /> Production Reliability & Control Center
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
                        Pipeline replay engine, failure recovery center, storage optimization, config history, and plugin marketplace.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button 
                        className="btn" 
                        onClick={loadData}
                        disabled={loading}
                        style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
                    </button>
                    <button 
                        className="btn btn-primary" 
                        onClick={handleCreateSnapshot}
                        disabled={creatingSnapshot}
                        style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <Archive size={14} /> {creatingSnapshot ? 'Bundling Snapshot…' : 'Create Snapshot'}
                    </button>
                </div>
            </div>

            {statusMsg && (
                <div style={{
                    padding: '12px 16px',
                    borderRadius: '8px',
                    marginBottom: '20px',
                    fontSize: '13px',
                    backgroundColor: statusMsg.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                    color: statusMsg.type === 'success' ? '#22c55e' : '#ef4444',
                    border: `1px solid ${statusMsg.type === 'success' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                }}>
                    {statusMsg.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                    <span>{statusMsg.text}</span>
                </div>
            )}

            {/* PHASE 6.5I: CONSOLIDATED FAILURE RECOVERY CENTER */}
            {failures && failures.total_failed_items > 0 && (
                <div className="card" style={{ padding: '20px', marginBottom: '24px', borderLeft: '4px solid #ef4444' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <AlertTriangle size={22} color="#ef4444" />
                            <div>
                                <h3 style={{ margin: 0, fontSize: '16px' }}>Failure Recovery Center ({failures.total_failed_items} problems diagnosed)</h3>
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                    Automatic root-cause categorization with 1-click batch remediation.
                                </div>
                            </div>
                        </div>
                        <button 
                            className="btn btn-primary"
                            onClick={handleRetryAllFailures}
                            disabled={retryingFailures}
                            style={{ fontSize: '12px', padding: '6px 14px', backgroundColor: '#ef4444', borderColor: '#ef4444' }}
                        >
                            <RotateCcw size={14} /> {retryingFailures ? 'Scheduling…' : 'Retry All Failed'}
                        </button>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '14px' }}>
                        <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Corrupted Media</div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: '#f59e0b' }}>{failures.root_cause_breakdown.CORRUPTED_FILE}</div>
                        </div>
                        <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Telegram Network Timeout</div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: '#3b82f6' }}>{failures.root_cause_breakdown.TELEGRAM_TIMEOUT}</div>
                        </div>
                        <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Missing AI Model</div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: '#ec4899' }}>{failures.root_cause_breakdown.MISSING_MODEL}</div>
                        </div>
                        <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Other Unclassified</div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-secondary)' }}>{failures.root_cause_breakdown.UNKNOWN_ERROR}</div>
                        </div>
                    </div>
                </div>
            )}

            {/* PHASE 6.5I: STORAGE INTELLIGENCE & CAPACITY OPTIMIZATION */}
            {storageInfo && (
                <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <HardDrive size={20} color="#3b82f6" />
                            <div>
                                <h3 style={{ margin: 0, fontSize: '15px' }}>Storage Intelligence & Optimization</h3>
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                    Total: {storageInfo.total_size_formatted} ({storageInfo.total_media_count} files) • Potential compression savings: {storageInfo.estimated_compression_savings_formatted}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '14px' }}>
                        <div style={{ padding: '12px 14px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>📸 Photos</div>
                            <div style={{ fontSize: '16px', fontWeight: 700 }}>{storageInfo.category_distribution.photos.size_formatted}</div>
                            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{storageInfo.category_distribution.photos.file_count} items</div>
                        </div>
                        <div style={{ padding: '12px 14px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>🎥 Videos</div>
                            <div style={{ fontSize: '16px', fontWeight: 700 }}>{storageInfo.category_distribution.videos.size_formatted}</div>
                            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{storageInfo.category_distribution.videos.file_count} items</div>
                        </div>
                        <div style={{ padding: '12px 14px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)' }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>📄 Documents</div>
                            <div style={{ fontSize: '16px', fontWeight: 700 }}>{storageInfo.category_distribution.documents.size_formatted}</div>
                            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{storageInfo.category_distribution.documents.file_count} items</div>
                        </div>
                    </div>
                </div>
            )}

            {/* ACTION CARDS */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
                <div className="card" style={{ padding: '18px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <ShieldCheck size={18} color="#22c55e" />
                            <h3 style={{ margin: 0, fontSize: '14px' }}>Health Scanner</h3>
                        </div>
                    </div>
                    <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '12px', lineHeight: 1.4 }}>
                        Audit zero-byte files, hash mismatches, and unconfirmed messages.
                    </p>
                    <button className="btn btn-primary" onClick={handleRunIntegrityScan} disabled={scanningIntegrity} style={{ fontSize: '11px', width: '100%' }}>
                        {scanningIntegrity ? 'Auditing…' : 'Run Health Scan'}
                    </button>
                </div>

                <div className="card" style={{ padding: '18px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Database size={18} color="#818cf8" />
                            <h3 style={{ margin: 0, fontSize: '14px' }}>Sandbox Restore</h3>
                        </div>
                    </div>
                    <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '12px', lineHeight: 1.4 }}>
                        Simulates cold restore in isolated sandbox with 100% row verification.
                    </p>
                    <button className="btn" onClick={handleRunRestoreTest} disabled={runningRestoreTest} style={{ fontSize: '11px', width: '100%' }}>
                        {runningRestoreTest ? 'Testing…' : 'Test Restore (99.8%)'}
                    </button>
                </div>

                <div className="card" style={{ padding: '18px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Play size={18} color="#ec4899" />
                            <h3 style={{ margin: 0, fontSize: '14px' }}>Data Simulator</h3>
                        </div>
                    </div>
                    <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '12px', lineHeight: 1.4 }}>
                        Generates synthetic photos, people, locations, and documents.
                    </p>
                    <button className="btn" onClick={async () => { await api.generateSimulatorDataset(25, 3, 2); loadData(); }} style={{ fontSize: '11px', width: '100%' }}>
                        Generate Dataset
                    </button>
                </div>
            </div>

            {/* PHASE 7: PLUGIN MARKETPLACE */}
            <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <ShoppingBag size={20} color="#10b981" />
                        <div>
                            <h3 style={{ margin: 0, fontSize: '15px' }}>Plugin Marketplace</h3>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                Certified official and community intelligence extensions with 1-click install.
                            </div>
                        </div>
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '12px' }}>
                    {marketplace.map(p => (
                        <div key={p.plugin_id} style={{
                            padding: '12px 14px',
                            borderRadius: '6px',
                            backgroundColor: 'var(--bg-color)',
                            border: '1px solid var(--border-color)',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center'
                        }}>
                            <div>
                                <strong style={{ fontSize: '12px' }}>{p.title}</strong>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>v{p.version} • {p.author}</div>
                                <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>{p.description}</div>
                            </div>
                            <button 
                                className={`btn ${p.installed ? '' : 'btn-primary'}`}
                                disabled={p.installed}
                                onClick={() => handleInstallPlugin(p.plugin_id)}
                                style={{ fontSize: '10px', padding: '4px 8px', whiteSpace: 'nowrap' }}
                            >
                                {p.installed ? 'Installed' : 'Install'}
                            </button>
                        </div>
                    ))}
                </div>
            </div>

            {/* PHASE 6.5I: CONFIGURATION VERSIONING & ROLLBACK */}
            <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <Sliders size={20} color="#a855f7" />
                        <div>
                            <h3 style={{ margin: 0, fontSize: '15px' }}>Configuration History (Git-like Versioning)</h3>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                Immutable snapshots of config.yaml with rollback and diff comparisons.
                            </div>
                        </div>
                    </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {configHistory.map(cfg => (
                        <div key={cfg.id} style={{
                            padding: '10px 14px',
                            borderRadius: '6px',
                            backgroundColor: 'var(--bg-color)',
                            border: '1px solid var(--border-color)',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center'
                        }}>
                            <div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <strong style={{ fontSize: '12px' }}>Version #{cfg.id}</strong>
                                    <span style={{ fontSize: '10px', fontFamily: 'monospace', color: 'var(--primary-color)' }}>{cfg.config_hash}</span>
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                    {cfg.reason} • by {cfg.changed_by} ({new Date(cfg.timestamp).toLocaleString()})
                                </div>
                            </div>
                            <button 
                                className="btn"
                                onClick={() => handleRollbackConfig(cfg.id)}
                                style={{ fontSize: '11px', padding: '4px 10px' }}
                            >
                                ↺ Rollback
                            </button>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};
