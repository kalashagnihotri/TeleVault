import { useEffect, useState } from 'react';
import { api, type CommandProfile } from '../services/api';
import { useJobContext } from '../contexts/JobContext';

export const RunCenter: React.FC = () => {
    const [profiles, setProfiles] = useState<CommandProfile[]>([]);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const { startJob } = useJobContext();
    
    useEffect(() => {
        api.getProfiles().then(setProfiles).catch(console.error);
    }, []);

    const handleRun = async (profileId: string) => {
        try {
            setErrorMsg(null);
            await startJob(profileId);
        } catch (e: any) {
            setErrorMsg(e.message || "Another job is already running.");
        }
    };

    const grouped = profiles.reduce((acc, p) => {
        const cat = p.category || 'OTHER';
        if (!acc[cat]) acc[cat] = [];
        acc[cat].push(p);
        return acc;
    }, {} as Record<string, CommandProfile[]>);

    return (
        <div className="main-content">
            <h2>Run Center</h2>
            {errorMsg && (
                <div style={{ padding: '16px', backgroundColor: 'rgba(218, 54, 51, 0.1)', border: '1px solid var(--error-color)', borderRadius: '6px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--error-color)', fontWeight: 500 }}>{errorMsg}</span>
                </div>
            )}
            
            {Object.entries(grouped).map(([category, prols]) => (
                <div key={category} style={{ marginBottom: '32px' }}>
                    <h3 style={{ marginBottom: '16px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontSize: '12px' }}>{category}</h3>
                    <div className="grid">
                        {prols.map(p => (
                            <div className="card" key={p.id}>
                                <h3>{p.display_name} <span className="badge" style={{float: 'right', backgroundColor: 'var(--success-color)'}}>{p.risk_level}</span></h3>
                                <p style={{marginBottom: '16px', color: 'var(--text-secondary)'}}>{p.description}</p>
                                <button className="btn btn-primary" onClick={() => handleRun(p.id)}>
                                    Run Job
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    );
};
