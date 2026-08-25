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

export interface QueueFileInfo {
    filename: string;
    media_type: string;
    size_bytes: number;
    modified_at: string;
    pipeline_status?: string;
}

export interface QueueStatus {
    images: number;
    videos: number;
    image_files: QueueFileInfo[];
    video_files: QueueFileInfo[];
}

export interface IngestResult {
    filename: string;
    original_filename: string;
    status: 'IMPORT_COMPLETE' | 'ARCHIVE_DUPLICATE' | 'QUEUE_DUPLICATE' | 'INVALID_MEDIA' | 'IMPORT_FAILED';
    size_bytes?: number;
    sha256_prefix?: string;
    destination?: string;
    error?: string;
    existing_media_id?: number;
    existing_state?: string;
    existing_route?: string;
    existing_preview_id?: number;
    existing_original_id?: number;
}

export interface ImportRecord {
    id: string;
    filename: string;
    original_filename: string;
    sha256?: string | null;
    size_bytes?: number | null;
    media_type?: string | null;
    status: string;
    created_at: string;
    completed_at?: string | null;
    destination?: string | null;
    error_code?: string | null;
    error_message?: string | null;
}

export interface FaceDetail {
    name?: string | null;
    decision: string;
    score?: number | null;
    confidence?: number | null;
}

export interface ArchiveStats {
    total: number;
    backed_up: number;
    pending: number;
    analyzing: number;
    ready: number;
    failed: number;
    cleanup_eligible: number;
    by_status: Record<string, number>;
}

export interface ArchiveRecord {
    id: number;
    sha256_prefix: string;
    original_filename: string;
    status: string;
    topic: string | null;
    caption: string | null;
    location_label?: string | null;
    faces: FaceDetail[];
    scenes: string[];
    faces_json: string | null;
    preview_message_id: number | null;
    original_message_id: number | null;
    file_size_bytes: number | null;
    media_type: string | null;
    backed_up_at: string | null;
    created_at: string | null;
}

export interface RuleEvaluation {
    rule_name: string;
    target_topic: string;
    matched: boolean;
    reason: string;
    superseded: boolean;
}

export interface RoutingExplanation {
    media_id: number;
    original_filename: string;
    media_type: string;
    has_gps: boolean;
    location_label?: string | null;
    detected_people: string[];
    scene_labels: string[];
    assigned_topic: string;
    winning_rule: string;
    evaluations: RuleEvaluation[];
    summary_reasons: string[];
}

export interface ReplayAnalysisResult {
    media_id: number;
    analysis_type: string;
    status: string;
    previous_labels: string[];
    new_labels: string[];
    previous_faces: FaceDetail[];
    new_faces: FaceDetail[];
    message: string;
}

export interface TimelineEvent {
    step: string;
    title: string;
    status: string;
    timestamp?: string | null;
    details?: string | null;
}

export interface MediaTimeline {
    media_id: number;
    original_filename: string;
    media_type: string;
    current_state: string;
    events: TimelineEvent[];
}

export interface AIModelStatus {
    id: string;
    name: string;
    category: string;
    path: string;
    version: string;
    backend: string;
    description: string;
    exists: boolean;
    status: string;
    size_bytes: number;
    expected_sha_prefix?: string | null;
}

export interface AIModelVerification {
    id: string;
    name: string;
    sha256?: string;
    sha256_prefix?: string;
    expected_prefix?: string | null;
    verified: boolean;
    status: string;
    error?: string;
}

export interface AIModelBenchmark {
    id: string;
    name: string;
    latency_ms: number;
    status: string;
    benchmark_iterations: number;
    timestamp: number;
}

export interface ConfigDiffItem {
    path: string;
    key: string;
    old_value: any;
    new_value: any;
    change_type: 'MODIFIED' | 'ADDED' | 'REMOVED';
}

export interface ConfigBackup {
    filename: string;
    path: string;
    size_bytes: number;
    created_at: string;
}

export interface SystemSnapshot {
    filename: string;
    path: string;
    size_bytes: number;
    created_at: string;
    manifest: Record<string, any>;
}

export interface NotificationItem {
    id: string;
    level: string;
    title: string;
    message: string;
    created_at: string;
    read: number;
}

export interface HealthCheckItem {
    id: string;
    name: string;
    score: number;
    max_score: number;
    status: 'PASSED' | 'WARNING' | 'FAILED';
    message: string;
}

export interface SystemHealthResponse {
    score: number;
    status: 'HEALTHY' | 'DEGRADED' | 'CRITICAL';
    checks: HealthCheckItem[];
    evaluated_at: string;
}

export interface DiagnosticTestItem {
    name: string;
    status: 'PASSED' | 'WARNING' | 'FAILED';
    details: string[];
}

export interface DiagnosticReport {
    report_id: string;
    timestamp: string;
    diagnostic_version: string;
    overall_status: 'PASSED' | 'WARNING' | 'FAILED';
    system: Record<string, any>;
    tests: DiagnosticTestItem[];
    filename?: string;
}

// Phase 6.5D & 6.5E Intelligence & Memory Interfaces
export interface SimilarMediaItem {
    media_id: number;
    similarity_score: number;
    reasons: string[];
    original_filename: string;
    short_hash: string;
    media_type: string;
    date_taken?: string | null;
    location_label?: string | null;
    labels: string[];
    people: string[];
    topic_id?: number | null;
    preview_message_id?: number | null;
    original_message_id?: number | null;
}

export interface SimilarMediaResponse {
    target_media_id: number;
    target_filename: string;
    total_matches: number;
    similar_items: SimilarMediaItem[];
}

export interface AssistantQueryResponse {
    query: string;
    explanation: string;
    applied_filters: Record<string, any>;
    total_results: number;
    results: any[];
}

export interface SmartCollection {
    id: string;
    title: string;
    category: 'trips' | 'people' | 'documents' | 'screenshots' | 'videos' | 'timeline';
    badge: string;
    description: string;
    count: number;
    cover_media_id?: number | null;
    filter_param?: string;
}

export interface ArchiveAnalyticsData {
    summary: {
        total_media: number;
        total_size_mb: number;
        images_count: number;
        videos_count: number;
        unique_people_count: number;
        unique_locations_count: number;
    };
    top_people: Array<{ name: string; count: number }>;
    scene_distribution: Array<{ category: string; count: number; percentage: number }>;
    top_locations: Array<{ location: string; count: number }>;
    timeline_activity: Array<{ period: string; count: number }>;
}

export interface MemoryEvent {
    event_id: string;
    title: string;
    category: 'trip' | 'celebration' | 'documents' | 'work_session' | 'casual_memory';
    start_date: string;
    end_date: string;
    media_count: number;
    location: string;
    participants: string[];
    narrative: string;
    event_confidence?: number;
    confidence_reasons?: string[];
    highlight_media_id: number;
    highlight_filename: string;
    media_ids: number[];
}

export interface MemoryHighlightItem {
    media_id: number;
    original_filename: string;
    short_hash: string;
    highlight_score: number;
    reasons: string[];
    date_taken?: string | null;
    location_label?: string | null;
    labels: string[];
    topic_id?: number | null;
    preview_message_id?: number | null;
    original_message_id?: number | null;
}

export interface MemoryChatResponse {
    query: string;
    answer: string;
    interpreted_intent?: {
        query: string;
        detected_time?: string | null;
        detected_people?: string[];
        detected_category?: string;
        confidence?: number;
    };
    relevant_media: Array<{ media_id: number; filename: string; title: string }>;
    suggested_followups: string[];
}

export interface ArchiveQualityMetrics {
    overall_quality_score: number;
    readiness_label?: string;
    metadata_completeness_pct: number;
    scene_coverage_pct: number;
    face_coverage_pct: number;
    location_coverage_pct?: number;
    duplicate_rate_pct: number;
    memory_readiness_pct?: number;
    score_breakdown?: Record<string, number>;
    recommendations?: string[];
    missing_dates_count?: number;
    unclassified_scenes_count?: number;
    total_assets_audited: number;
}

export interface PersonProfile {
    person_id: number;
    display_name: string;
    photo_count: number;
    first_seen: string;
    last_seen: string;
    top_locations: string[];
    sample_media_id?: number;
}

export interface PairwiseRelationship {
    person_1: string;
    person_2: string;
    shared_photos: number;
    first_interaction: string;
    last_interaction: string;
}

export interface RelationshipGraphNode {
    id: string;
    name: string;
    photo_count: number;
}

export interface RelationshipGraphLink {
    source: string;
    target: string;
    weight: number;
    label: string;
}

export interface RelationshipGraphData {
    nodes: RelationshipGraphNode[];
    links: RelationshipGraphLink[];
    pairwise_relationships?: PairwiseRelationship[];
}

// Phase 6.5F Observability, Integrity & Management Interfaces
export interface StageLatency {
    avg_ms: number;
    p50_ms: number;
    p95_ms: number;
}

export interface PipelineMetrics {
    total_processed: number;
    successful: number;
    failed: number;
    in_progress: number;
    success_rate_pct: number;
    stage_latencies: Record<string, StageLatency>;
    total_avg_pipeline_ms: number;
    evaluated_at: string;
}

export interface FailureAnalytics {
    failure_counts: {
        face_failures: number;
        scene_failures: number;
        telegram_upload_failures: number;
        total_failures: number;
    };
    root_causes: Record<string, number>;
    active_retries_count: number;
}

export interface IntegrityIssue {
    media_id: number;
    target: string;
    error_type: string;
    severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
    details: string;
}

export interface IntegrityReport {
    total_files_audited: number;
    valid_files_count: number;
    issues_count: number;
    issues: IntegrityIssue[];
    integrity_score_pct: number;
    status: 'HEALTHY' | 'PROBLEMS_DETECTED';
}

export interface UnknownFaceCluster {
    cluster_id: string;
    title: string;
    appearances_count: number;
    location: string;
    date_period: string;
    sample_faces: Array<{ face_id: number; media_id: number; filename: string; confidence: number }>;
    media_ids: number[];
}

export interface RestoreTestResult {
    test_status: 'PASSED' | 'FAILED';
    backup_source: string;
    backup_size_bytes: number;
    integrity_check: string;
    source_row_counts: Record<string, number>;
    restored_row_counts: Record<string, number>;
    total_discrepancies: number;
    verification_duration_ms: number;
    message: string;
}

export interface ExportResult {
    success: boolean;
    export_filename: string;
    export_path: string;
    media_exported: number;
    people_exported: number;
    file_size_bytes: number;
}

// Phase 6.5G Types: Feedback, Audit, Scheduler, Preferences, Deduplication, Portable Export
export interface AuditEvent {
    id: number;
    actor: string;
    action: string;
    object_type: string;
    object_id: string;
    before_state?: string;
    after_state?: string;
    before_state_parsed?: any;
    after_state_parsed?: any;
    timestamp: string;
}

export interface AuditTimelineResponse {
    total_events: number;
    returned_count: number;
    events: AuditEvent[];
}

export interface SchedulerStatus {
    daily_backup_enabled: boolean;
    integrity_scan_enabled: boolean;
    thumbnail_regen_enabled: boolean;
    retry_flush_enabled: boolean;
    last_run_timestamp?: string;
    status: 'IDLE' | 'RUNNING' | 'ERROR';
}

export interface MediaLifecycleResponse {
    total_media: number;
    lifecycle_stages: {
        IMPORTED: number;
        ANALYZED: number;
        BACKED_UP: number;
        INDEXED: number;
        MEMORY_CREATED: number;
        ARCHIVED: number;
    };
    status_breakdown: {
        complete_and_backed_up: number;
        waiting_or_processing: number;
        failed_quarantined: number;
    };
    completion_rate_pct: number;
}

export interface UserPreferencesProfile {
    top_favorites: Array<{ category: string; label: string; affinity_score: number }>;
    all_preferences: Array<{ category: string; label: string; affinity_score: number; interaction_count: number }>;
}

export interface NearDuplicateCluster {
    cluster_id: string;
    primary_media_id: number;
    primary_filename: string;
    total_similar_photos: number;
    photos: Array<{ media_id: number; filename: string; size_bytes: number; date_taken: string; similarity_pct?: number }>;
    suggested_action: string;
}

export interface NearDuplicateScanResponse {
    total_images_scanned: number;
    near_duplicate_clusters_count: number;
    clusters: NearDuplicateCluster[];
}

export interface PortableArchiveExportResponse {
    success: boolean;
    bundle_filename: string;
    bundle_path: string;
    media_count: number;
    people_count: number;
    memories_count: number;
    photos_copied: number;
    videos_copied: number;
    file_size_bytes: number;
}

export interface MemoryQualityEvaluationResponse {
    total_memories_evaluated: number;
    archive_average_memory_score: number;
    dimension_averages: {
        naming_accuracy: number;
        grouping_cohesion: number;
        story_narrative: number;
        representative_diversity: number;
    };
    memories: Array<{
        memory_id: string;
        title: string;
        overall_score: number;
        dimensions: Record<string, number>;
        status: string;
    }>;
    recommendations: string[];
}

export interface RankedSearchResult {
    result_type: 'MEMORY_STORY' | 'MEDIA_ASSET';
    id: string;
    title: string;
    description?: string;
    date_taken?: string;
    location?: string;
    people?: string[];
    labels?: string[];
    relevance_pct: number;
    factors: Record<string, number>;
}

// Phase 6.5H Types
export interface SemanticSearchResult {
    media_id: number;
    filename: string;
    date_taken?: string;
    location?: string;
    labels?: string[];
    people?: string[];
    similarity_score: number;
    similarity_pct: number;
}

export interface PersonSummaryItem {
    person_id: number;
    person_slug: string;
    display_name: string;
    photo_count: number;
    avg_confidence_pct: number;
    first_seen?: string;
    last_seen?: string;
}

export interface PersonTimelineYear {
    year: string;
    photo_count: number;
    months: Record<string, { month: string; count: number }>;
    sample_media_ids: number[];
}

export interface PersonTimelineData {
    person_id: number;
    display_name: string;
    total_photos: number;
    years: PersonTimelineYear[];
}

export interface SmartNotificationFeedItem {
    id: string;
    category: string;
    level: 'SUCCESS' | 'WARNING' | 'INFO';
    title: string;
    message: string;
    action_label?: string;
    action_route?: string;
    timestamp: string;
}

export interface AiRecommendationItem {
    id: string;
    priority: 'HIGH' | 'MEDIUM' | 'LOW';
    title: string;
    description: string;
    impact: string;
    estimated_time_str: string;
    action_key: string;
}

export interface VideoIntelligenceItem {
    media_id: number;
    duration_seconds: number;
    duration_formatted: string;
    fps: number;
    resolution: string;
    video_codec: string;
    audio_codec: string;
    storyboard: Array<{ frame_index: number; timestamp_sec: number; description: string }>;
}

export interface TimelineSection {
    year: string;
    month: string;
    items_count: number;
    items: Array<{
        id: number;
        filename: string;
        media_type: string;
        size_bytes: number;
        date_taken?: string;
        location?: string;
        labels: string[];
        people: string[];
    }>;
}

export interface TimelineStreamResponse {
    page: number;
    page_size: number;
    total_items: number;
    has_more: boolean;
    sections: TimelineSection[];
}

export interface FleetNodeItem {
    worker_id: string;
    node_name: string;
    ip_address: string;
    capabilities: string[];
    status: 'ONLINE' | 'BUSY' | 'OFFLINE';
    last_heartbeat_at: string;
    current_job_id?: string;
    processed_tasks_count: number;
}

export interface FleetStatusResponse {
    total_nodes: number;
    online_nodes_count: number;
    nodes: FleetNodeItem[];
}

export interface PluginRegistryItem {
    plugin_name: string;
    version: string;
    description: string;
    enabled: boolean;
    installed_at: string;
}

export interface DocumentItem {
    media_id: number;
    filename: string;
    merchant_name?: string;
    amount?: number;
    currency?: string;
    document_date?: string;
    category?: string;
    extracted_text: string;
}

export interface SecurityScorecardResponse {
    security_score: number;
    rating: string;
    evaluated_at: string;
    dimension_scores: {
        credential_isolation: number;
        api_network_guard: number;
        media_sanitization: number;
        storage_encryption: number;
    };
    checks: Array<{ category: string; title: string; status: string; points: number; details: string }>;
}

// Phase 6.5I, 6.5J, Phase 7 Types
export interface PipelineHistoryItem {
    id: number;
    media_id: number;
    stage: string;
    model_version: string;
    config_hash: string;
    result: Record<string, any>;
    status: string;
    timestamp: string;
}

export interface ModelRegistryItem {
    model_name: string;
    version: string;
    category: string;
    sha256?: string;
    description: string;
    active: number;
    registered_at: string;
}

export interface ConfigVersionItem {
    id: number;
    config_hash: string;
    changed_by: string;
    reason: string;
    timestamp: string;
    size_bytes: number;
}

export interface PriorityQueueStats {
    summary: {
        queued: number;
        running: number;
        completed: number;
        failed: number;
        priority_1: number;
        priority_2: number;
        priority_3: number;
    };
    recent_jobs: Array<Record<string, any>>;
}

export interface FailureOverviewResponse {
    total_failed_items: number;
    root_cause_breakdown: {
        CORRUPTED_FILE: number;
        TELEGRAM_TIMEOUT: number;
        MISSING_MODEL: number;
        UNKNOWN_ERROR: number;
    };
    items: Array<{
        media_id: number;
        filename: string;
        path: string;
        media_type: string;
        state: string;
        error_message: string;
        diagnosed_cause: string;
        failed_at: string;
    }>;
}

export interface StorageBreakdownResponse {
    total_media_count: number;
    total_size_bytes: number;
    total_size_formatted: string;
    category_distribution: {
        photos: { file_count: number; size_bytes: number; size_formatted: string };
        videos: { file_count: number; size_bytes: number; size_formatted: string };
        documents: { file_count: number; size_bytes: number; size_formatted: string };
        audio: { file_count: number; size_bytes: number; size_formatted: string };
        other: { file_count: number; size_bytes: number; size_formatted: string };
    };
    largest_files: Array<{
        media_id: number;
        filename: string;
        media_type: string;
        size_bytes: number;
        size_formatted: string;
        date_taken?: string;
    }>;
    estimated_compression_savings_bytes: number;
    estimated_compression_savings_formatted: string;
    cold_storage_candidate_count: number;
}

export interface AutomatedBackupVerificationResponse {
    status: string;
    backup_confidence_score: number;
    verification_duration_ms: number;
    verified_at: string;
    reconciliation: Record<string, string>;
    sqlite_integrity: string;
    message: string;
}

export interface AIChatResponse {
    user_prompt: string;
    understood_intent: Record<string, any>;
    ai_response: string;
    relevant_assets: Array<{
        media_id: number;
        filename: string;
        date_taken?: string;
        location?: string;
        relevance_score: number;
    }>;
    suggested_followups: string[];
}

export interface AutobiographyResponse {
    year: string;
    book_title: string;
    executive_summary: string;
    total_photos_in_year: number;
    total_locations_visited: number;
    key_people: string[];
    chapters: Array<{
        month_number: number;
        month_name: string;
        chapter_title: string;
        narrative: string;
        photo_count: number;
        sample_photos: string[];
    }>;
}

export interface CalendarEventItem {
    id: string;
    title: string;
    start_date: string;
    end_date: string;
    location?: string;
    description?: string;
    matched_media_count: number;
}

export interface LocationHierarchyResponse {
    total_places_visited: number;
    top_visited_cities: Array<{
        raw_label: string;
        city: string;
        country: string;
        photo_count: number;
        first_visit?: string;
        last_visit?: string;
        estimated_trips_count: number;
    }>;
    all_destinations: Array<any>;
}

export interface MarketplacePluginItem {
    plugin_id: string;
    title: string;
    version: string;
    author: string;
    description: string;
    icon: string;
    category: string;
    installed: boolean;
}

export interface ApiTokenItem {
    token_id: string;
    name: string;
    scopes_json: string;
    created_at: string;
    last_used_at?: string;
    active: number;
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
    async getSystemMode(): Promise<{ mode: string }> {
        const res = await fetch(`${API_BASE}/system/mode`);
        return res.json();
    },
    async setSystemMode(mode: 'safe' | 'production'): Promise<{ mode: string; status: string }> {
        const res = await fetch(`${API_BASE}/system/mode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode })
        });
        if (!res.ok) throw new Error('Failed to update system mode');
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
            throw new Error(err.detail?.message || err.detail || 'Failed to start job');
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
    },

    // Health & Diagnostics
    async getHealthScore(): Promise<SystemHealthResponse> {
        const res = await fetch(`${API_BASE}/system/health_score`);
        if (!res.ok) throw new Error('Failed to fetch system health score');
        return res.json();
    },
    async runDiagnostic(): Promise<DiagnosticReport> {
        const res = await fetch(`${API_BASE}/system/run_diagnostic`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to run diagnostic');
        return res.json();
    },
    async getDiagnosticReports(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/system/diagnostic_reports`);
        return res.json();
    },

    // Queue & Ingest
    async getQueueStatus(): Promise<QueueStatus> {
        const res = await fetch(`${API_BASE}/queue/status`);
        if (!res.ok) throw new Error('Failed to get queue status');
        return res.json();
    },
    async ingestFiles(files: File[]): Promise<IngestResult[]> {
        const form = new FormData();
        for (const f of files) form.append('files', f);
        const res = await fetch(`${API_BASE}/queue/ingest`, {
            method: 'POST',
            body: form,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail || 'Upload failed');
        }
        return res.json();
    },
    async getImports(limit = 50, offset = 0): Promise<ImportRecord[]> {
        const res = await fetch(`${API_BASE}/queue/imports?limit=${limit}&offset=${offset}`);
        if (!res.ok) throw new Error('Failed to fetch import history');
        return res.json();
    },

    // Archive
    async getArchiveStats(): Promise<ArchiveStats> {
        const res = await fetch(`${API_BASE}/archive/stats`);
        if (!res.ok) throw new Error('Failed to get archive stats');
        return res.json();
    },
    async getArchiveRecent(limit = 50): Promise<ArchiveRecord[]> {
        const res = await fetch(`${API_BASE}/archive/recent?limit=${limit}`);
        if (!res.ok) throw new Error('Failed to get recent records');
        return res.json();
    },
    async getArchivePending(limit = 50): Promise<ArchiveRecord[]> {
        const res = await fetch(`${API_BASE}/archive/pending?limit=${limit}`);
        if (!res.ok) throw new Error('Failed to get pending records');
        return res.json();
    },
    async searchArchive(q: string, limit = 50): Promise<ArchiveRecord[]> {
        const res = await fetch(`${API_BASE}/archive/search?q=${encodeURIComponent(q)}&limit=${limit}`);
        if (!res.ok) throw new Error('Search failed');
        return res.json();
    },
    async explainRouting(mediaId: number): Promise<RoutingExplanation> {
        const res = await fetch(`${API_BASE}/archive/${mediaId}/explain_routing`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Failed to explain routing' }));
            throw new Error(err.detail || 'Failed to explain routing');
        }
        return res.json();
    },
    async replayAnalysis(mediaId: number, analysisType: 'scene' | 'face' | 'all' = 'scene'): Promise<ReplayAnalysisResult> {
        const res = await fetch(`${API_BASE}/archive/${mediaId}/replay_analysis?analysis_type=${analysisType}`, {
            method: 'POST'
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Replay analysis failed' }));
            throw new Error(err.detail || 'Replay analysis failed');
        }
        return res.json();
    },
    async getMediaTimeline(mediaId: number): Promise<MediaTimeline> {
        const res = await fetch(`${API_BASE}/archive/${mediaId}/timeline`);
        if (!res.ok) throw new Error('Failed to fetch media timeline');
        return res.json();
    },

    // Phase 6.5D Intelligence APIs
    async getSimilarMedia(mediaId: number, limit = 10): Promise<SimilarMediaResponse> {
        const res = await fetch(`${API_BASE}/archive/${mediaId}/similar?limit=${limit}`);
        if (!res.ok) throw new Error('Failed to fetch similar media');
        return res.json();
    },
    async queryAssistant(query: string): Promise<AssistantQueryResponse> {
        const res = await fetch(`${API_BASE}/archive/assistant`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });
        if (!res.ok) throw new Error('Assistant query failed');
        return res.json();
    },
    async getSmartCollections(): Promise<SmartCollection[]> {
        const res = await fetch(`${API_BASE}/archive/collections`);
        if (!res.ok) throw new Error('Failed to fetch smart collections');
        return res.json();
    },
    async getSmartCollectionItems(collectionId: string): Promise<ArchiveRecord[]> {
        const res = await fetch(`${API_BASE}/archive/collections/${collectionId}`);
        if (!res.ok) throw new Error('Failed to fetch collection items');
        return res.json();
    },
    async getArchiveAnalytics(): Promise<ArchiveAnalyticsData> {
        const res = await fetch(`${API_BASE}/archive/analytics`);
        if (!res.ok) throw new Error('Failed to fetch archive analytics');
        return res.json();
    },

    // Phase 6.5E Memory Engine APIs
    async getMemories(): Promise<MemoryEvent[]> {
        const res = await fetch(`${API_BASE}/archive/memories`);
        if (!res.ok) throw new Error('Failed to fetch memories');
        return res.json();
    },
    async getHighlights(person?: string, year?: number, limit = 12): Promise<MemoryHighlightItem[]> {
        const params = new URLSearchParams();
        if (person) params.set('person', person);
        if (year) params.set('year', String(year));
        params.set('limit', String(limit));
        const res = await fetch(`${API_BASE}/archive/highlights?${params.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch highlights');
        return res.json();
    },
    async chatWithMemory(prompt: string): Promise<MemoryChatResponse> {
        const res = await fetch(`${API_BASE}/archive/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
        });
        if (!res.ok) throw new Error('Memory chat query failed');
        return res.json();
    },
    async getArchiveQuality(): Promise<ArchiveQualityMetrics> {
        const res = await fetch(`${API_BASE}/archive/quality`);
        if (!res.ok) throw new Error('Failed to fetch archive quality');
        return res.json();
    },
    async getRelationships(): Promise<RelationshipGraphData> {
        const res = await fetch(`${API_BASE}/archive/relationships`);
        if (!res.ok) throw new Error('Failed to fetch relationships');
        return res.json();
    },
    async getPeopleProfiles(): Promise<PersonProfile[]> {
        const res = await fetch(`${API_BASE}/archive/people_profiles`);
        if (!res.ok) throw new Error('Failed to fetch people profiles');
        return res.json();
    },

    // Config Center (Phase 6.5C)
    async getConfig(): Promise<Record<string, any>> {
        const res = await fetch(`${API_BASE}/config`);
        if (!res.ok) throw new Error('Failed to fetch config');
        return res.json();
    },
    async validateConfig(config: Record<string, any>): Promise<{ valid: boolean; errors: string[] }> {
        const res = await fetch(`${API_BASE}/config/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config })
        });
        return res.json();
    },
    async computeConfigDiff(config: Record<string, any>): Promise<ConfigDiffItem[]> {
        const res = await fetch(`${API_BASE}/config/diff`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config })
        });
        if (!res.ok) throw new Error('Failed to compute config diff');
        return res.json();
    },
    async saveConfig(config: Record<string, any>): Promise<{ success: boolean; message: string; errors: string[] }> {
        const res = await fetch(`${API_BASE}/config/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config })
        });
        return res.json();
    },
    async getConfigBackups(): Promise<ConfigBackup[]> {
        const res = await fetch(`${API_BASE}/config/backups`);
        return res.json();
    },
    async restoreConfigBackup(filename: string): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/config/restore`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Restore failed');
        }
        return res.json();
    },

    // Models Center
    async getModels(): Promise<AIModelStatus[]> {
        const res = await fetch(`${API_BASE}/models`);
        return res.json();
    },
    async verifyModels(): Promise<AIModelVerification[]> {
        const res = await fetch(`${API_BASE}/models/verify`, { method: 'POST' });
        return res.json();
    },
    async benchmarkModel(model_id: string): Promise<AIModelBenchmark> {
        const res = await fetch(`${API_BASE}/models/benchmark`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_id })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Benchmark failed');
        }
        return res.json();
    },

    // Maintenance & Snapshots
    async getSnapshots(): Promise<SystemSnapshot[]> {
        const res = await fetch(`${API_BASE}/maintenance/snapshots`);
        return res.json();
    },
    async createSnapshot(): Promise<SystemSnapshot> {
        const res = await fetch(`${API_BASE}/maintenance/snapshots/create`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to create snapshot');
        return res.json();
    },
    async getNotifications(): Promise<NotificationItem[]> {
        const res = await fetch(`${API_BASE}/notifications`);
        return res.json();
    },
    async markNotificationRead(id: string): Promise<void> {
        await fetch(`${API_BASE}/notifications/${id}/read`, { method: 'POST' });
    },
    async markAllNotificationsRead(): Promise<void> {
        await fetch(`${API_BASE}/notifications/read_all`, { method: 'POST' });
    },

    // Phase 6.5F Observability & Metrics
    async getPipelineMetrics(): Promise<PipelineMetrics> {
        const res = await fetch(`${API_BASE}/metrics/pipeline`);
        if (!res.ok) throw new Error('Failed to fetch pipeline metrics');
        return res.json();
    },
    async getFailureAnalytics(): Promise<FailureAnalytics> {
        const res = await fetch(`${API_BASE}/metrics/failures`);
        if (!res.ok) throw new Error('Failed to fetch failure analytics');
        return res.json();
    },
    async getRetryQueue(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/metrics/retries`);
        if (!res.ok) throw new Error('Failed to fetch retry queue');
        return res.json();
    },

    // Phase 6.5F Data Integrity Scanner
    async runIntegrityScan(): Promise<IntegrityReport> {
        const res = await fetch(`${API_BASE}/integrity/scan`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to run integrity scan');
        return res.json();
    },
    async getIntegrityReport(): Promise<IntegrityReport> {
        const res = await fetch(`${API_BASE}/integrity/report`);
        if (!res.ok) throw new Error('Failed to fetch integrity report');
        return res.json();
    },

    // Phase 6.5F Face Management
    async getUnknownFaceClusters(): Promise<UnknownFaceCluster[]> {
        const res = await fetch(`${API_BASE}/faces/unknown_clusters`);
        if (!res.ok) throw new Error('Failed to fetch unknown face clusters');
        return res.json();
    },
    async createPersonFromCluster(cluster_id: string, display_name: string): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/faces/clusters/create_person`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cluster_id, display_name })
        });
        if (!res.ok) throw new Error('Failed to enroll identity');
        return res.json();
    },
    async mergeIdentities(source_person_id: number, target_person_id: number): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/faces/merge_identities`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_person_id, target_person_id })
        });
        if (!res.ok) throw new Error('Failed to merge identities');
        return res.json();
    },

    // Phase 6.5F Scene Reprocessing
    async getSceneReprocessQueue(): Promise<{ pending_count: number; failed_count: number; completed_count: number }> {
        const res = await fetch(`${API_BASE}/scenes/reprocess_queue`);
        if (!res.ok) throw new Error('Failed to fetch scene reprocess queue');
        return res.json();
    },
    async reprocessScenes(mode = 'failed', media_ids?: number[]): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/scenes/reprocess`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, media_ids })
        });
        if (!res.ok) throw new Error('Failed to reprocess scenes');
        return res.json();
    },

    // Phase 6.5F Disaster Recovery & Export
    async testBackupRestore(backup_filename?: string): Promise<RestoreTestResult> {
        const res = await fetch(`${API_BASE}/maintenance/restore/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ backup_filename })
        });
        if (!res.ok) throw new Error('Restore test failed');
        return res.json();
    },
    async exportArchiveManifest(): Promise<ExportResult> {
        const res = await fetch(`${API_BASE}/maintenance/export`, { method: 'POST' });
        if (!res.ok) throw new Error('Export failed');
        return res.json();
    },

    // Phase 6.5F Manual Queue Actions
    async performQueueAction(action: 'retry' | 'delete' | 'move' | 'cancel', filename: string, media_type = 'image'): Promise<{ status: string; message: string }> {
        const res = await fetch(`${API_BASE}/queue/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, filename, media_type })
        });
        if (!res.ok) throw new Error(`Queue action '${action}' failed`);
        return res.json();
    },

    // Phase 6.5G Human Feedback & Audit
    async submitFaceFeedback(data: { media_id: number; action: string; new_identity?: string; face_id?: number; person_id?: number; notes?: string }): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/feedback/face`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Failed to submit face feedback');
        return res.json();
    },
    async submitSceneFeedback(data: { media_id: number; new_label: string; confidence?: number; notes?: string }): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/feedback/scene`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Failed to submit scene feedback');
        return res.json();
    },
    async getAuditTimeline(limit = 50, offset = 0, action?: string): Promise<AuditTimelineResponse> {
        let url = `${API_BASE}/audit/timeline?limit=${limit}&offset=${offset}`;
        if (action) url += `&action=${encodeURIComponent(action)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('Failed to fetch audit timeline');
        return res.json();
    },

    // Phase 6.5G Automation, Scheduler & Lifecycle
    async getSchedulerStatus(): Promise<SchedulerStatus> {
        const res = await fetch(`${API_BASE}/automation/scheduler/status`);
        if (!res.ok) throw new Error('Failed to fetch scheduler status');
        return res.json();
    },
    async toggleSchedulerTask(task_name: string, enabled: boolean): Promise<SchedulerStatus> {
        const res = await fetch(`${API_BASE}/automation/scheduler/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_name, enabled })
        });
        if (!res.ok) throw new Error('Failed to toggle scheduler task');
        return res.json();
    },
    async runMaintenanceCycle(): Promise<any> {
        const res = await fetch(`${API_BASE}/automation/maintenance/run`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to trigger maintenance cycle');
        return res.json();
    },
    async processRetries(): Promise<any> {
        const res = await fetch(`${API_BASE}/automation/retries/process`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to process retries');
        return res.json();
    },
    async getMediaLifecycle(): Promise<MediaLifecycleResponse> {
        const res = await fetch(`${API_BASE}/automation/lifecycle`);
        if (!res.ok) throw new Error('Failed to fetch media lifecycle');
        return res.json();
    },
    async getUserPreferences(): Promise<UserPreferencesProfile> {
        const res = await fetch(`${API_BASE}/automation/preferences`);
        if (!res.ok) throw new Error('Failed to fetch user preferences');
        return res.json();
    },
    async recordPreferenceInteraction(category: string, increment = 1.0): Promise<void> {
        await fetch(`${API_BASE}/automation/preferences/interact`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category, increment })
        });
    },

    // Phase 6.5G Near-Deduplication
    async scanNearDuplicates(distance_threshold = 5): Promise<NearDuplicateScanResponse> {
        const res = await fetch(`${API_BASE}/deduplication/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ distance_threshold })
        });
        if (!res.ok) throw new Error('Failed to scan near duplicates');
        return res.json();
    },

    // Phase 6.5G Portable Archive Export
    async exportPortableArchive(): Promise<PortableArchiveExportResponse> {
        const res = await fetch(`${API_BASE}/portable_archive/export`, { method: 'POST' });
        if (!res.ok) throw new Error('Portable export failed');
        return res.json();
    },

    // Phase 6.5G Memory Quality & Ranked Search
    async getMemoryQualityEvaluation(): Promise<MemoryQualityEvaluationResponse> {
        const res = await fetch(`${API_BASE}/memories/quality_evaluation`);
        if (!res.ok) throw new Error('Failed to fetch memory quality evaluation');
        return res.json();
    },
    async getRankedSearch(query: string, limit = 20): Promise<RankedSearchResult[]> {
        const res = await fetch(`${API_BASE}/archive/ranked_search?q=${encodeURIComponent(query)}&limit=${limit}`);
        if (!res.ok) throw new Error('Ranked search failed');
        return res.json();
    },

    // Phase 6.5H Semantic Visual Search
    async searchSemanticVision(query: string, limit = 20): Promise<SemanticSearchResult[]> {
        const res = await fetch(`${API_BASE}/archive/semantic_search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, limit })
        });
        if (!res.ok) throw new Error('Semantic vision search failed');
        return res.json();
    },

    // Phase 6.5H People Manager & Identity Timeline
    async getPeopleSummaries(): Promise<PersonSummaryItem[]> {
        const res = await fetch(`${API_BASE}/people/summaries`);
        if (!res.ok) throw new Error('Failed to fetch people summaries');
        return res.json();
    },
    async getPersonTimeline(personId: number): Promise<PersonTimelineData> {
        const res = await fetch(`${API_BASE}/people/${personId}/timeline`);
        if (!res.ok) throw new Error('Failed to fetch person timeline');
        return res.json();
    },
    async renamePerson(personId: number, new_display_name: string): Promise<{ success: boolean; new_name: string }> {
        const res = await fetch(`${API_BASE}/people/${personId}/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_display_name })
        });
        if (!res.ok) throw new Error('Failed to rename person');
        return res.json();
    },
    async deletePerson(personId: number): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/people/${personId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete person');
        return res.json();
    },

    // Phase 6.5H Memory Overrides
    async getMemoryOverrides(): Promise<Record<string, any>> {
        const res = await fetch(`${API_BASE}/memories/overrides`);
        if (!res.ok) throw new Error('Failed to fetch memory overrides');
        return res.json();
    },
    async saveMemoryOverride(memoryId: string, data: { original_ai_title: string; user_title?: string; user_description?: string; is_pinned?: boolean }): Promise<{ success: boolean; active_title: string }> {
        const res = await fetch(`${API_BASE}/memories/${memoryId}/override`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Failed to save memory override');
        return res.json();
    },

    // Phase 6.5H Smart Notifications & AI Recommendations
    async getSmartNotificationsFeed(): Promise<SmartNotificationFeedItem[]> {
        const res = await fetch(`${API_BASE}/notifications/smart_feed`);
        if (!res.ok) throw new Error('Failed to fetch smart notifications feed');
        return res.json();
    },
    async getMaintenanceRecommendations(): Promise<AiRecommendationItem[]> {
        const res = await fetch(`${API_BASE}/maintenance/recommendations`);
        if (!res.ok) throw new Error('Failed to fetch maintenance recommendations');
        return res.json();
    },
    async executeMaintenanceRecommendation(action_key: string): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/maintenance/recommendations/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action_key })
        });
        if (!res.ok) throw new Error('Failed to execute recommendation');
        return res.json();
    },

    // Phase 6.5H Video Intelligence & Voice Query
    async getVideoIntelligence(mediaId: number): Promise<VideoIntelligenceItem> {
        const res = await fetch(`${API_BASE}/media/${mediaId}/video_intelligence`);
        if (!res.ok) throw new Error('Failed to fetch video intelligence');
        return res.json();
    },
    async executeVoiceQuery(transcript: string): Promise<any> {
        const res = await fetch(`${API_BASE}/archive/voice_query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript })
        });
        if (!res.ok) throw new Error('Voice query failed');
        return res.json();
    },

    // Phase 6.5H Infinite Timeline Stream
    async getTimelineStream(page = 1, page_size = 50): Promise<TimelineStreamResponse> {
        const res = await fetch(`${API_BASE}/archive/timeline_stream?page=${page}&page_size=${page_size}`);
        if (!res.ok) throw new Error('Failed to fetch timeline stream');
        return res.json();
    },

    // Phase 6.5H Fleet Status & Plugins
    async getFleetStatus(): Promise<FleetStatusResponse> {
        const res = await fetch(`${API_BASE}/fleet/status`);
        if (!res.ok) throw new Error('Failed to fetch fleet status');
        return res.json();
    },
    async getPluginsList(): Promise<PluginRegistryItem[]> {
        const res = await fetch(`${API_BASE}/plugins/list`);
        if (!res.ok) throw new Error('Failed to fetch plugins list');
        return res.json();
    },
    async togglePlugin(plugin_name: string, enabled: boolean): Promise<{ success: boolean; enabled: boolean }> {
        const res = await fetch(`${API_BASE}/plugins/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plugin_name, enabled })
        });
        if (!res.ok) throw new Error('Failed to toggle plugin');
        return res.json();
    },

    // Phase 6.5H Document OCR Search & Security Scorecard
    async searchDocuments(query: string, limit = 20): Promise<DocumentItem[]> {
        const res = await fetch(`${API_BASE}/documents/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, limit })
        });
        if (!res.ok) throw new Error('Document search failed');
        return res.json();
    },
    async getSecurityScorecard(): Promise<SecurityScorecardResponse> {
        const res = await fetch(`${API_BASE}/security/scorecard`);
        if (!res.ok) throw new Error('Failed to fetch security scorecard');
        return res.json();
    },
    async generateSimulatorDataset(photo_count = 50, people_count = 5, locations_count = 3): Promise<any> {
        const res = await fetch(`${API_BASE}/simulator/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ photo_count, people_count, locations_count })
        });
        if (!res.ok) throw new Error('Dataset generation failed');
        return res.json();
    },

    // Phase 6.5I Pipeline Replay & Model Registry
    async getPipelineHistory(mediaId: number): Promise<PipelineHistoryItem[]> {
        const res = await fetch(`${API_BASE}/pipeline/history/${mediaId}`);
        if (!res.ok) throw new Error('Failed to fetch pipeline history');
        return res.json();
    },
    async replayPipeline(mediaId: number, stageFilter?: string): Promise<any> {
        const res = await fetch(`${API_BASE}/pipeline/replay`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ media_id: mediaId, stage_filter: stageFilter })
        });
        if (!res.ok) throw new Error('Pipeline replay failed');
        return res.json();
    },
    async getRegisteredModels(): Promise<ModelRegistryItem[]> {
        const res = await fetch(`${API_BASE}/models/list`);
        if (!res.ok) throw new Error('Failed to fetch registered models');
        return res.json();
    },

    // Phase 6.5I Config Versioning & Priority Queue
    async getConfigHistory(): Promise<ConfigVersionItem[]> {
        const res = await fetch(`${API_BASE}/config/history`);
        if (!res.ok) throw new Error('Failed to fetch config history');
        return res.json();
    },
    async compareConfigVersions(vOld: number, vNew: number): Promise<{ v_old_id: number; v_new_id: number; diff_text: string; lines_changed: number }> {
        const res = await fetch(`${API_BASE}/config/compare?v_old=${vOld}&v_new=${vNew}`);
        if (!res.ok) throw new Error('Failed to compare config versions');
        return res.json();
    },
    async rollbackConfig(versionId: number): Promise<{ success: boolean; new_version_id: number }> {
        const res = await fetch(`${API_BASE}/config/rollback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version_id: versionId })
        });
        if (!res.ok) throw new Error('Config rollback failed');
        return res.json();
    },
    async getPriorityQueueStats(): Promise<PriorityQueueStats> {
        const res = await fetch(`${API_BASE}/queue/stats`);
        if (!res.ok) throw new Error('Failed to fetch queue stats');
        return res.json();
    },

    // Phase 6.5I Failure Recovery Center & Storage Intelligence
    async getFailureOverview(): Promise<FailureOverviewResponse> {
        const res = await fetch(`${API_BASE}/recovery/overview`);
        if (!res.ok) throw new Error('Failed to fetch failure overview');
        return res.json();
    },
    async retryAllFailed(): Promise<{ success: boolean; reset_count: number; message: string }> {
        const res = await fetch(`${API_BASE}/recovery/retry_all`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to retry all failed items');
        return res.json();
    },
    async ignoreFailure(mediaId: number): Promise<{ success: boolean; media_id: number }> {
        const res = await fetch(`${API_BASE}/recovery/ignore/${mediaId}`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to ignore failure');
        return res.json();
    },
    async getStorageBreakdown(): Promise<StorageBreakdownResponse> {
        const res = await fetch(`${API_BASE}/storage/breakdown`);
        if (!res.ok) throw new Error('Failed to fetch storage breakdown');
        return res.json();
    },
    async runAutomatedBackupVerification(): Promise<AutomatedBackupVerificationResponse> {
        const res = await fetch(`${API_BASE}/backup/automated_verification`, { method: 'POST' });
        if (!res.ok) throw new Error('Backup verification failed');
        return res.json();
    },

    // Phase 6.5J Personal AI Experience
    async queryAIChat(prompt: string): Promise<AIChatResponse> {
        const res = await fetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
        });
        if (!res.ok) throw new Error('AI Chat query failed');
        return res.json();
    },
    async getAutobiography(year = '2026'): Promise<AutobiographyResponse> {
        const res = await fetch(`${API_BASE}/ai/autobiography/${year}`);
        if (!res.ok) throw new Error('Failed to fetch autobiography');
        return res.json();
    },
    async getMediaMood(mediaId: number): Promise<any> {
        const res = await fetch(`${API_BASE}/ai/mood/${mediaId}`);
        if (!res.ok) throw new Error('Failed to fetch media mood');
        return res.json();
    },
    async getMoodCollections(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/ai/mood/collections`);
        if (!res.ok) throw new Error('Failed to fetch mood collections');
        return res.json();
    },
    async listCalendarEvents(): Promise<CalendarEventItem[]> {
        const res = await fetch(`${API_BASE}/calendar/events`);
        if (!res.ok) throw new Error('Failed to fetch calendar events');
        return res.json();
    },
    async getLocationsHierarchy(): Promise<LocationHierarchyResponse> {
        const res = await fetch(`${API_BASE}/locations/hierarchy`);
        if (!res.ok) throw new Error('Failed to fetch locations hierarchy');
        return res.json();
    },

    // Phase 7 Architecture Evolution
    async listMarketplacePlugins(): Promise<MarketplacePluginItem[]> {
        const res = await fetch(`${API_BASE}/marketplace/list`);
        if (!res.ok) throw new Error('Failed to fetch marketplace plugins');
        return res.json();
    },
    async installMarketplacePlugin(plugin_id: string): Promise<{ success: boolean; message: string }> {
        const res = await fetch(`${API_BASE}/marketplace/install`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plugin_id })
        });
        if (!res.ok) throw new Error('Failed to install marketplace plugin');
        return res.json();
    },
    async listApiTokens(): Promise<ApiTokenItem[]> {
        const res = await fetch(`${API_BASE}/v1/tokens`);
        if (!res.ok) throw new Error('Failed to fetch API tokens');
        return res.json();
    },
    async createApiToken(name: string): Promise<{ token_id: string; name: string; raw_token: string }> {
        const res = await fetch(`${API_BASE}/v1/tokens`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!res.ok) throw new Error('Failed to create API token');
        return res.json();
    },
};
