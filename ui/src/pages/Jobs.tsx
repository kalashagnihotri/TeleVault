import React, { useEffect, useState } from 'react';
import { api, type JobSummary } from '../services/api';
import { Play, RotateCw, Copy, Download, Info } from 'lucide-react';
import { useJobContext } from '../contexts/JobContext';

export const Jobs: React.FC = () => {
    const [jobs, setJobs] = useState<JobSummary[]>([]);
    const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
    const { startJob, viewHistoricalJob } = useJobContext();

    useEffect(() => {
        let isMounted = true;
        const fetchJobs = () => {
            api.getJobs().then(res => {
                if(isMounted) setJobs(res);
            }).catch(console.error);
        };
        fetchJobs();
        const interval = setInterval(fetchJobs, 5000);
        return () => { isMounted = false; clearInterval(interval); };
    }, []);

    const handleCopyFailure = async (job: JobSummary) => {
        try {
            const log = await api.getJobLog(job.id);
            const context = `Job ID: ${job.id}\nProfile: ${job.profile_id}\nStatus: ${job.status}\nExit Code: ${job.exit_code}\nDuration: ${job.duration?.toFixed(1)}s\n\n--- Error Summary ---\n${job.error_summary || 'N/A'}\n\n--- Last 100 lines ---\n${log.split('\n').slice(-100).join('\n')}`;
            navigator.clipboard.writeText(context);
            alert('Failure context copied to clipboard.');
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div className="main-content">
            <h2>Job History</h2>
            <div className="card">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Profile</th>
                            <th>Status</th>
                            <th>Started</th>
                            <th>Duration (s)</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {jobs.map(j => (
                            <React.Fragment key={j.id}>
                                <tr>
                                    <td style={{fontFamily: 'monospace'}}>{j.id.split('-')[1]}</td>
                                    <td>{j.profile_id}</td>
                                    <td><span className={`status-chip ${j.status}`}>{j.status}</span></td>
                                    <td>{j.started_at ? new Date(j.started_at).toLocaleString() : '-'}</td>
                                    <td>{j.duration ? j.duration.toFixed(1) : '-'}</td>
                                    <td>
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <button className="btn" onClick={() => viewHistoricalJob(j)} title="Open Log">
                                                <Play size={12} /> Log
                                            </button>
                                            <button className="btn" onClick={() => setExpandedJobId(expandedJobId === j.id ? null : j.id)} title="Details">
                                                <Info size={12} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                                {expandedJobId === j.id && (
                                    <tr>
                                        <td colSpan={6} style={{ backgroundColor: 'rgba(0,0,0,0.2)', padding: '16px' }}>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                                <div style={{ display: 'flex', gap: '24px' }}>
                                                    <div>
                                                        <div className="stat-label">Full ID</div>
                                                        <div>{j.id}</div>
                                                    </div>
                                                    <div>
                                                        <div className="stat-label">Created</div>
                                                        <div>{new Date(j.created_at || '').toLocaleString()}</div>
                                                    </div>
                                                    <div>
                                                        <div className="stat-label">Exit Code</div>
                                                        <div>{j.exit_code ?? 'N/A'}</div>
                                                    </div>
                                                </div>
                                                <div style={{ display: 'flex', gap: '8px' }}>
                                                    <button className="btn" onClick={() => startJob(j.profile_id)} title="Rerun Profile">
                                                        <RotateCw size={12} /> Rerun
                                                    </button>
                                                    <button className="btn" onClick={() => window.open(`/api/jobs/${j.id}/log`, '_blank')} title="Download Log">
                                                        <Download size={12} /> Download Log
                                                    </button>
                                                    {j.status === 'FAILED' && (
                                                        <button className="btn btn-danger" onClick={() => handleCopyFailure(j)} title="Copy Redacted Failure">
                                                            <Copy size={12} /> Copy Failure Context
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        ))}
                        {jobs.length === 0 && <tr><td colSpan={6}>No jobs found.</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
