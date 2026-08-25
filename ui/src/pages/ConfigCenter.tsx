import React, { useEffect, useState } from 'react';
import { api, type ConfigBackup, type ConfigDiffItem } from '../services/api';
import { Settings, Save, CheckCircle2, AlertCircle, History, RotateCcw, ShieldCheck, ArrowRight, Layers } from 'lucide-react';

export const ConfigCenter: React.FC = () => {
    const [config, setConfig] = useState<Record<string, any> | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [validating, setValidating] = useState(false);
    const [diffItems, setDiffItems] = useState<ConfigDiffItem[]>([]);
    const [showDiffModal, setShowDiffModal] = useState(false);
    const [validationErrors, setValidationErrors] = useState<string[]>([]);
    const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
    const [backups, setBackups] = useState<ConfigBackup[]>([]);
    const [showBackupsModal, setShowBackupsModal] = useState(false);
    const [activeSection, setActiveSection] = useState<'telegram' | 'faces' | 'scenes' | 'cleanup' | 'queue'>('telegram');

    const loadConfig = async () => {
        setLoading(true);
        try {
            const data = await api.getConfig();
            setConfig(data);
            setStatusMsg(null);
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Failed to load config: ${err.message}` });
        } finally {
            setLoading(false);
        }
    };

    const loadBackups = async () => {
        try {
            const b = await api.getConfigBackups();
            setBackups(b);
        } catch (err) {
            console.error('Failed to load config backups:', err);
        }
    };

    useEffect(() => {
        loadConfig();
    }, []);

    const updateField = (section: string, field: string, val: any) => {
        if (!config) return;
        setConfig(prev => ({
            ...prev,
            [section]: {
                ...(prev?.[section] || {}),
                [field]: val
            }
        }));
    };

    const updateNestedTopic = (topic: string, val: number) => {
        if (!config) return;
        setConfig(prev => ({
            ...prev,
            telegram: {
                ...(prev?.telegram || {}),
                topics: {
                    ...(prev?.telegram?.topics || {}),
                    [topic]: val
                }
            }
        }));
    };

    const handleValidate = async () => {
        if (!config) return;
        setValidating(true);
        setValidationErrors([]);
        setStatusMsg(null);
        try {
            const res = await api.validateConfig(config);
            if (res.valid) {
                setStatusMsg({ type: 'success', text: '✓ Configuration is valid and ready to apply.' });
            } else {
                setValidationErrors(res.errors);
                setStatusMsg({ type: 'error', text: 'Validation failed. Please resolve errors before saving.' });
            }
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Validation request failed: ${err.message}` });
        } finally {
            setValidating(false);
        }
    };

    const handleReviewAndSave = async () => {
        if (!config) return;
        setValidating(true);
        setValidationErrors([]);
        setStatusMsg(null);
        try {
            const valRes = await api.validateConfig(config);
            if (!valRes.valid) {
                setValidationErrors(valRes.errors);
                setStatusMsg({ type: 'error', text: 'Validation failed. Fix issues before saving.' });
                setValidating(false);
                return;
            }

            const diffs = await api.computeConfigDiff(config);
            if (diffs.length === 0) {
                setStatusMsg({ type: 'success', text: 'No modifications detected compared to active config.' });
                setValidating(false);
                return;
            }

            setDiffItems(diffs);
            setShowDiffModal(true);
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Failed to review changes: ${err.message}` });
        } finally {
            setValidating(false);
        }
    };

    const handleConfirmSave = async () => {
        if (!config) return;
        setSaving(true);
        setStatusMsg(null);
        setValidationErrors([]);
        try {
            const res = await api.saveConfig(config);
            if (res.success) {
                setShowDiffModal(false);
                setStatusMsg({ type: 'success', text: '✓ Configuration saved, backed up, and applied successfully!' });
                loadBackups();
            } else {
                setValidationErrors(res.errors);
                setStatusMsg({ type: 'error', text: `Save failed: ${res.message}` });
            }
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Save request failed: ${err.message}` });
        } finally {
            setSaving(false);
        }
    };

    const handleRestore = async (filename: string) => {
        try {
            await api.restoreConfigBackup(filename);
            setShowBackupsModal(false);
            setStatusMsg({ type: 'success', text: `✓ Restored configuration from ${filename}` });
            loadConfig();
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Restore failed: ${err.message}` });
        }
    };

    if (loading || !config) {
        return (
            <div className="main-content" style={{ textAlign: 'center', padding: '48px', color: 'var(--text-secondary)' }}>
                Loading configuration…
            </div>
        );
    }

    return (
        <div className="main-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div>
                    <h2 style={{ marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Settings size={22} color="var(--primary-color)" /> Config Center
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
                        Safely configure Telegram topics, AI models, cleanup policies, and ingestion queues.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button 
                        className="btn" 
                        onClick={() => { loadBackups(); setShowBackupsModal(true); }}
                        style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <History size={14} /> Backups & Rollback
                    </button>
                    <button 
                        className="btn" 
                        onClick={handleValidate}
                        disabled={validating || saving}
                        style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <ShieldCheck size={14} /> Validate
                    </button>
                    <button 
                        className="btn btn-primary" 
                        onClick={handleReviewAndSave}
                        disabled={saving || validating}
                        style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <Save size={14} /> Save & Apply
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
                    {statusMsg.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                    <span>{statusMsg.text}</span>
                </div>
            )}

            {validationErrors.length > 0 && (
                <div style={{
                    padding: '12px 16px',
                    borderRadius: '8px',
                    marginBottom: '20px',
                    fontSize: '13px',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#ef4444'
                }}>
                    <strong style={{ display: 'block', marginBottom: '6px' }}>Configuration Issues Found:</strong>
                    <ul style={{ margin: 0, paddingLeft: '20px' }}>
                        {validationErrors.map((e, idx) => (
                            <li key={idx}>{e}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Navigation Tabs */}
            <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '24px' }}>
                {(['telegram', 'faces', 'scenes', 'cleanup', 'queue'] as const).map(sec => (
                    <button
                        key={sec}
                        onClick={() => setActiveSection(sec)}
                        style={{
                            padding: '8px 16px',
                            border: 'none',
                            background: 'none',
                            borderBottom: activeSection === sec ? '2px solid var(--primary-color)' : '2px solid transparent',
                            color: activeSection === sec ? 'var(--text-primary)' : 'var(--text-secondary)',
                            fontWeight: activeSection === sec ? 600 : 400,
                            cursor: 'pointer',
                            fontSize: '13px',
                            textTransform: 'capitalize'
                        }}
                    >
                        {sec === 'telegram' ? '✈️ Telegram' :
                         sec === 'faces' ? '👤 Face Analysis' :
                         sec === 'scenes' ? '🌄 Scene Analysis' :
                         sec === 'cleanup' ? '🧹 Cleanup Policy' : '📥 Queue & Paths'}
                    </button>
                ))}
            </div>

            {/* 1. Telegram Section */}
            {activeSection === 'telegram' && (
                <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <h3 style={{ margin: 0, fontSize: '15px' }}>Telegram Routing & Group Settings</h3>
                    
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Telegram Group ID
                            </label>
                            <input
                                type="text"
                                value={config.telegram?.group_id || ''}
                                onChange={e => updateField('telegram', 'group_id', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Caption Max Length (Chars)
                            </label>
                            <input
                                type="number"
                                value={config.telegram?.caption_max_length || 900}
                                onChange={e => updateField('telegram', 'caption_max_length', parseInt(e.target.value, 10))}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                    </div>

                    <h4 style={{ margin: '8px 0 0 0', fontSize: '13px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Topic Thread IDs
                    </h4>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                        {['people', 'family_groups', 'travel_nature', 'everyday', 'screenshots_documents', 'videos', 'misc'].map(t => (
                            <div key={t}>
                                <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', textTransform: 'capitalize' }}>
                                    {t.replace('_', ' ')}
                                </label>
                                <input
                                    type="number"
                                    value={config.telegram?.topics?.[t] ?? 0}
                                    onChange={e => updateNestedTopic(t, parseInt(e.target.value, 10) || 0)}
                                    style={{ width: '100%', padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                                />
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* 2. Face Analysis Section */}
            {activeSection === 'faces' && (
                <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h3 style={{ margin: 0, fontSize: '15px' }}>Face Recognition Configuration</h3>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.faces?.enabled ?? true}
                                onChange={e => updateField('faces', 'enabled', e.target.checked)}
                            />
                            <strong>Enabled</strong>
                        </label>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Detector Confidence (0.0 - 1.0)
                            </label>
                            <input
                                type="number"
                                step="0.05"
                                min="0"
                                max="1"
                                value={config.faces?.detector_confidence || 0.85}
                                onChange={e => updateField('faces', 'detector_confidence', parseFloat(e.target.value))}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Minimum Face Size (px)
                            </label>
                            <input
                                type="number"
                                value={config.faces?.minimum_face_size_px || 96}
                                onChange={e => updateField('faces', 'minimum_face_size_px', parseInt(e.target.value, 10))}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Detector Model File
                            </label>
                            <input
                                type="text"
                                value={config.faces?.detector_model || ''}
                                onChange={e => updateField('faces', 'detector_model', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Recognizer Model File
                            </label>
                            <input
                                type="text"
                                value={config.faces?.recognizer_model || ''}
                                onChange={e => updateField('faces', 'recognizer_model', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                    </div>

                    <div style={{ display: 'flex', gap: '24px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.faces?.use_for_routing ?? true}
                                onChange={e => updateField('faces', 'use_for_routing', e.target.checked)}
                            />
                            Use for Topic Routing
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.faces?.include_names_in_captions ?? true}
                                onChange={e => updateField('faces', 'include_names_in_captions', e.target.checked)}
                            />
                            Include Names in Telegram Captions
                        </label>
                    </div>
                </div>
            )}

            {/* 3. Scene Analysis Section */}
            {activeSection === 'scenes' && (
                <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h3 style={{ margin: 0, fontSize: '15px' }}>Scene & Environment Analysis</h3>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.scenes?.enabled ?? true}
                                onChange={e => updateField('scenes', 'enabled', e.target.checked)}
                            />
                            <strong>Enabled</strong>
                        </label>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Minimum Scene Confidence
                            </label>
                            <input
                                type="number"
                                step="0.05"
                                min="0"
                                max="1"
                                value={config.scenes?.minimum_confidence || 0.25}
                                onChange={e => updateField('scenes', 'minimum_confidence', parseFloat(e.target.value))}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Max Scene Labels to Keep
                            </label>
                            <input
                                type="number"
                                value={config.scenes?.max_labels || 3}
                                onChange={e => updateField('scenes', 'max_labels', parseInt(e.target.value, 10))}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                    </div>

                    <div style={{ display: 'flex', gap: '24px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.scenes?.enable_screenshot_heuristics ?? true}
                                onChange={e => updateField('scenes', 'enable_screenshot_heuristics', e.target.checked)}
                            />
                            Enable Screenshot Heuristics
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.scenes?.enable_document_heuristics ?? true}
                                onChange={e => updateField('scenes', 'enable_document_heuristics', e.target.checked)}
                            />
                            Enable Document Heuristics
                        </label>
                    </div>
                </div>
            )}

            {/* 4. Cleanup Section */}
            {activeSection === 'cleanup' && (
                <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h3 style={{ margin: 0, fontSize: '15px' }}>Archive Cleanup Policy</h3>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.cleanup?.enabled ?? true}
                                onChange={e => updateField('cleanup', 'enabled', e.target.checked)}
                            />
                            <strong>Enabled</strong>
                        </label>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Cleanup Mode
                            </label>
                            <select
                                value={config.cleanup?.mode || 'move'}
                                onChange={e => updateField('cleanup', 'mode', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            >
                                <option value="move">Move to Completed</option>
                                <option value="delete">Permanent Delete</option>
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Backup Safety Grace Period (Days)
                            </label>
                            <input
                                type="number"
                                value={config.cleanup?.backup_safety_days || 7}
                                onChange={e => updateField('cleanup', 'backup_safety_days', parseInt(e.target.value, 10))}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                    </div>

                    <div>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                            <input
                                type="checkbox"
                                checked={config.cleanup?.verify_hash_before_cleanup ?? true}
                                onChange={e => updateField('cleanup', 'verify_hash_before_cleanup', e.target.checked)}
                            />
                            Verify Full SHA-256 Hash Before Cleanup Action
                        </label>
                    </div>
                </div>
            )}

            {/* 5. Queue Section */}
            {activeSection === 'queue' && (
                <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <h3 style={{ margin: 0, fontSize: '15px' }}>Ingestion Queue & Directories</h3>
                    
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Incoming Images Directory
                            </label>
                            <input
                                type="text"
                                value={config.queue?.incoming_images || ''}
                                onChange={e => updateField('queue', 'incoming_images', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Incoming Videos Directory
                            </label>
                            <input
                                type="text"
                                value={config.queue?.incoming_videos || ''}
                                onChange={e => updateField('queue', 'incoming_videos', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Completed Directory
                            </label>
                            <input
                                type="text"
                                value={config.queue?.completed || ''}
                                onChange={e => updateField('queue', 'completed', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                Failed Directory
                            </label>
                            <input
                                type="text"
                                value={config.queue?.failed || ''}
                                onChange={e => updateField('queue', 'failed', e.target.value)}
                                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '13px' }}
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Configuration Change Review Diff Modal */}
            {showDiffModal && (
                <div className="modal-overlay" onClick={() => setShowDiffModal(false)}>
                    <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '580px', maxHeight: '85vh', overflowY: 'auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                            <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Layers size={18} color="var(--primary-color)" /> Review Configuration Changes
                            </h3>
                            <button onClick={() => setShowDiffModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '18px' }}>✕</button>
                        </div>

                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                            The following modifications will be committed to <code style={{ backgroundColor: 'var(--bg-color)', padding: '2px 6px', borderRadius: '4px' }}>config/config.yaml</code>. An automated backup will be created prior to applying.
                        </p>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '24px' }}>
                            {diffItems.map((d, i) => (
                                <div key={i} style={{
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    backgroundColor: 'var(--bg-color)',
                                    border: '1px solid var(--border-color)',
                                    fontSize: '12px'
                                }}>
                                    <div style={{ fontWeight: 600, fontFamily: 'monospace', color: 'var(--primary-color)', marginBottom: '6px' }}>
                                        {d.path}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px' }}>
                                        <span style={{ color: '#ef4444', textDecoration: 'line-through', fontFamily: 'monospace' }}>
                                            {JSON.stringify(d.old_value)}
                                        </span>
                                        <ArrowRight size={14} color="var(--text-secondary)" />
                                        <span style={{ color: '#22c55e', fontWeight: 600, fontFamily: 'monospace' }}>
                                            {JSON.stringify(d.new_value)}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                            <button className="btn" onClick={() => setShowDiffModal(false)}>Cancel</button>
                            <button 
                                className="btn btn-primary" 
                                onClick={handleConfirmSave}
                                disabled={saving}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                            >
                                <Save size={14} /> {saving ? 'Applying Changes…' : 'Confirm & Apply Changes'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Backups & Restore Modal */}
            {showBackupsModal && (
                <div className="modal-overlay" onClick={() => setShowBackupsModal(false)}>
                    <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '540px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                            <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <History size={18} /> Configuration Backups
                            </h3>
                            <button onClick={() => setShowBackupsModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '18px' }}>✕</button>
                        </div>

                        {backups.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                                No backups recorded yet. Backups are created automatically before every save.
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '350px', overflowY: 'auto' }}>
                                {backups.map((b, i) => (
                                    <div key={i} style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        padding: '10px 14px',
                                        borderRadius: '6px',
                                        backgroundColor: 'var(--bg-color)',
                                        border: '1px solid var(--border-color)',
                                        fontSize: '12px'
                                    }}>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{b.filename}</div>
                                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                                {new Date(b.created_at).toLocaleString()} ({b.size_bytes} bytes)
                                            </div>
                                        </div>
                                        <button
                                            className="btn"
                                            onClick={() => handleRestore(b.filename)}
                                            style={{ fontSize: '11px', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                                        >
                                            <RotateCcw size={12} /> Restore
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};
