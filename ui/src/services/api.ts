const isDev = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost';
const API_BASE = isDev ? 'http://127.0.0.1:8000/api' : '/api';
export const WS_BASE = isDev ? 'ws://127.0.0.1:8000/api' : `ws://${window.location.host}/api`;

export interface JobSummary {
    id: string;
    profile_id: string;
    status: string;
    created_at: string;
    started_at: string;
    finished_at: string;
    exit_code: number | null;
    duration: number | null;
    error_summary?: string;
}

export interface CommandProfile {
    id: string;
    display_name: string;
    description: string;
    risk_level: string;
    category: string;
}

export const api = {
    async getHealth() {
        const res = await fetch(`${API_BASE}/health`);
        return res.json();
    },
    async getSystem() {
        const res = await fetch(`${API_BASE}/system`);
        return res.json();
    },
    async getDashboard() {
        const res = await fetch(`${API_BASE}/dashboard`);
        return res.json();
    },
    async getJobs(): Promise<JobSummary[]> {
        const res = await fetch(`${API_BASE}/jobs`);
        return res.json();
    },
    async getCurrentJob(): Promise<JobSummary | null> {
        const res = await fetch(`${API_BASE}/jobs/current`);
        return res.json();
    },
    async getProfiles(): Promise<CommandProfile[]> {
        const res = await fetch(`${API_BASE}/jobs/profiles`);
        return res.json();
    },
    async startJob(profile_id: string): Promise<JobSummary> {
        const res = await fetch(`${API_BASE}/jobs/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_id })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail?.message || 'Failed to start job');
        }
        return res.json();
    },
    async cancelJob(job_id: string): Promise<JobSummary> {
        const res = await fetch(`${API_BASE}/jobs/${job_id}/cancel`, { method: 'POST' });
        return res.json();
    },
    async getJobLog(job_id: string): Promise<string> {
        const res = await fetch(`${API_BASE}/jobs/${job_id}/log`);
        if (!res.ok) return '';
        return res.text();
    }
};
