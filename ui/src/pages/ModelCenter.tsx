import React, { useEffect, useState } from 'react';
import { api, type AIModelStatus, type AIModelVerification, type AIModelBenchmark } from '../services/api';
import { Cpu, ShieldCheck, Zap, RefreshCw, CheckCircle2, XCircle } from 'lucide-react';

export const ModelCenter: React.FC = () => {
    const [models, setModels] = useState<AIModelStatus[]>([]);
    const [verifications, setVerifications] = useState<Record<string, AIModelVerification>>({});
    const [benchmarks, setBenchmarks] = useState<Record<string, AIModelBenchmark>>({});
    const [loading, setLoading] = useState(true);
    const [verifying, setVerifying] = useState(false);
    const [benchmarkingId, setBenchmarkingId] = useState<string | null>(null);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    const loadModels = async () => {
        setLoading(true);
        setErrorMsg(null);
        try {
            const data = await api.getModels();
            setModels(data);
        } catch (err: any) {
            setErrorMsg(`Failed to load AI models: ${err.message}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadModels();
    }, []);

    const handleVerifyAll = async () => {
        setVerifying(true);
        try {
            const results = await api.verifyModels();
            const map: Record<string, AIModelVerification> = {};
            for (const r of results) {
                map[r.id] = r;
            }
            setVerifications(map);
        } catch (err: any) {
            setErrorMsg(`Verification failed: ${err.message}`);
        } finally {
            setVerifying(false);
        }
    };

    const handleBenchmark = async (modelId: string) => {
        setBenchmarkingId(modelId);
        try {
            const res = await api.benchmarkModel(modelId);
            setBenchmarks(prev => ({ ...prev, [modelId]: res }));
        } catch (err: any) {
            setErrorMsg(`Benchmark failed for ${modelId}: ${err.message}`);
        } finally {
            setBenchmarkingId(null);
        }
    };

    const fmtSize = (bytes: number) => {
        if (!bytes) return '0 B';
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    };

    return (
        <div className="main-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div>
                    <h2 style={{ marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Cpu size={22} color="var(--primary-color)" /> AI Model Management
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
                        Inspect ONNX neural models, verify cryptographic SHA-256 signatures, and test inference latencies.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button 
                        className="btn" 
                        onClick={loadModels}
                        disabled={loading}
                        style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
                    </button>
                    <button 
                        className="btn btn-primary" 
                        onClick={handleVerifyAll}
                        disabled={verifying}
                        style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <ShieldCheck size={14} /> Verify Model Signatures
                    </button>
                </div>
            </div>

            {errorMsg && (
                <div style={{
                    padding: '12px 16px',
                    borderRadius: '8px',
                    marginBottom: '20px',
                    fontSize: '13px',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    color: '#ef4444',
                    border: '1px solid rgba(239, 68, 68, 0.3)'
                }}>
                    {errorMsg}
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px' }}>
                {models.map(m => {
                    const ver = verifications[m.id];
                    const bm = benchmarks[m.id];
                    const isBenchmarking = benchmarkingId === m.id;

                    return (
                        <div key={m.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <div>
                                    <h3 style={{ margin: '0 0 4px 0', fontSize: '15px' }}>{m.name}</h3>
                                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', gap: '8px', alignItems: 'center' }}>
                                        <span style={{
                                            padding: '1px 6px',
                                            borderRadius: '4px',
                                            backgroundColor: 'rgba(255,255,255,0.08)',
                                            fontWeight: 600
                                        }}>
                                            {m.category}
                                        </span>
                                        <span>v{m.version}</span>
                                        <span>•</span>
                                        <span>{m.backend}</span>
                                    </div>
                                </div>
                                <div>
                                    {m.exists ? (
                                        <span style={{ fontSize: '11px', fontWeight: 600, padding: '3px 8px', borderRadius: '999px', backgroundColor: 'rgba(34, 197, 94, 0.15)', color: '#22c55e' }}>
                                            READY
                                        </span>
                                    ) : (
                                        <span style={{ fontSize: '11px', fontWeight: 600, padding: '3px 8px', borderRadius: '999px', backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#ef4444' }}>
                                            MISSING
                                        </span>
                                    )}
                                </div>
                            </div>

                            <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                                {m.description}
                            </p>

                            <div style={{
                                backgroundColor: 'var(--bg-color)',
                                padding: '10px 12px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '6px'
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ color: 'var(--text-secondary)' }}>File Path:</span>
                                    <span style={{ fontFamily: 'monospace' }}>{m.path}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ color: 'var(--text-secondary)' }}>File Size:</span>
                                    <span>{fmtSize(m.size_bytes)}</span>
                                </div>
                                {m.expected_sha_prefix && (
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: 'var(--text-secondary)' }}>Expected SHA Prefix:</span>
                                        <span style={{ fontFamily: 'monospace' }}>{m.expected_sha_prefix}...</span>
                                    </div>
                                )}
                            </div>

                            {/* Verification Result */}
                            {ver && (
                                <div style={{
                                    padding: '8px 12px',
                                    borderRadius: '6px',
                                    fontSize: '12px',
                                    backgroundColor: ver.verified ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                    color: ver.verified ? '#22c55e' : '#ef4444',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between'
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                        {ver.verified ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                                        <span>{ver.verified ? 'Cryptographic Hash Verified' : 'Hash Mismatch'}</span>
                                    </div>
                                    <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>
                                        {ver.sha256_prefix ? `${ver.sha256_prefix}...` : ''}
                                    </span>
                                </div>
                            )}

                            {/* Benchmark Result */}
                            {bm && (
                                <div style={{
                                    padding: '8px 12px',
                                    borderRadius: '6px',
                                    fontSize: '12px',
                                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                    color: '#3b82f6',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between'
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                        <Zap size={14} />
                                        <span>Average Inference Latency:</span>
                                    </div>
                                    <strong style={{ fontSize: '13px' }}>{bm.latency_ms} ms</strong>
                                </div>
                            )}

                            <div style={{ marginTop: 'auto', paddingTop: '8px' }}>
                                <button
                                    className="btn"
                                    onClick={() => handleBenchmark(m.id)}
                                    disabled={!m.exists || isBenchmarking}
                                    style={{
                                        width: '100%',
                                        fontSize: '12px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: '6px'
                                    }}
                                >
                                    <Zap size={14} /> {isBenchmarking ? 'Running Forward Pass Benchmark…' : 'Test Inference Latency'}
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
