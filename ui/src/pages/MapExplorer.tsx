import React, { useEffect, useRef, useState } from 'react';
import { Map as MapLibreMap, NavigationControl, Marker, Popup, LngLatBounds } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { 
    api, 
    type MapPointItem, 
    type LocationStatsItem, 
    type LocationServiceStatus, 
    type LocationHealthScanResponse 
} from '../services/api';
import { 
    MapPin, 
    Compass, 
    RefreshCw, 
    CheckCircle2, 
    AlertTriangle, 
    Search, 
    PlusCircle, 
    Database, 
    Globe, 
    Layers
} from 'lucide-react';

export const MapExplorer: React.FC = () => {
    const mapContainer = useRef<HTMLDivElement>(null);
    const map = useRef<MapLibreMap | null>(null);

    const [points, setPoints] = useState<MapPointItem[]>([]);
    const [stats, setStats] = useState<LocationStatsItem[]>([]);
    const [status, setStatus] = useState<LocationServiceStatus | null>(null);
    const [health, setHealth] = useState<LocationHealthScanResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    // Modal & Interactive states
    const [testLat, setTestLat] = useState('37.8651');
    const [testLon, setTestLon] = useState('-119.5383');
    const [testResult, setTestResult] = useState<any>(null);
    const [testingLookup, setTestingLookup] = useState(false);

    const [aliasLat, setAliasLat] = useState('');
    const [aliasLon, setAliasLon] = useState('');
    const [aliasName, setAliasName] = useState('');
    const [aliasRadius, setAliasRadius] = useState('0.05');
    const [savingAlias, setSavingAlias] = useState(false);
    const [showAliasModal, setShowAliasModal] = useState(false);

    const loadData = async () => {
        setLoading(true);
        try {
            const [pts, st, stat] = await Promise.all([
                api.getMapPoints().catch(() => []),
                api.getLocationStats().catch(() => []),
                api.getLocationStatus().catch(() => null),
            ]);
            setPoints(pts);
            setStats(st);
            setStatus(stat);
        } catch (err: any) {
            console.error('Failed to load map explorer data:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    // Initialize MapLibre GL
    useEffect(() => {
        if (!mapContainer.current) return;
        if (map.current) return;

        try {
            map.current = new MapLibreMap({
                container: mapContainer.current,
                style: 'https://tiles.openfreemap.org/styles/dark',
                center: [-98.5795, 39.8283], // Center on US / World view
                zoom: 2.5,
                attributionControl: false,
            });

            map.current.addControl(new NavigationControl({ showCompass: true, showZoom: true }), 'top-right');
        } catch (err) {
            console.warn('MapLibre style loading error, using fallback:', err);
        }

        return () => {
            if (map.current) {
                map.current.remove();
                map.current = null;
            }
        };
    }, []);

    // Add Markers to MapLibre Map
    useEffect(() => {
        if (!map.current || points.length === 0) return;

        const bounds = new LngLatBounds();
        let validCoordsCount = 0;

        points.forEach(pt => {
            if (pt.lat && pt.lon) {
                validCoordsCount++;
                bounds.extend([pt.lon, pt.lat]);

                // Create custom marker element
                const el = document.createElement('div');
                el.className = 'custom-map-marker';
                el.style.backgroundColor = 'var(--primary-color, #6366f1)';
                el.style.width = '24px';
                el.style.height = '24px';
                el.style.borderRadius = '50%';
                el.style.border = '2px solid white';
                el.style.boxShadow = '0 2px 8px rgba(0,0,0,0.5)';
                el.style.cursor = 'pointer';
                el.style.display = 'flex';
                el.style.alignItems = 'center';
                el.style.justifyContent = 'center';
                el.style.color = 'white';
                el.style.fontSize = '12px';
                el.innerHTML = '📍';

                // Create popup
                const popup = new Popup({ offset: 25 }).setHTML(`
                    <div style="color: #111; padding: 6px; font-family: sans-serif;">
                        <strong style="font-size: 13px;">${pt.title}</strong>
                        <div style="font-size: 11px; color: #555; margin-top: 2px;">
                            ${pt.filename || 'Media #' + pt.id}
                        </div>
                        <div style="font-size: 10px; color: #777; margin-top: 4px;">
                            📅 ${pt.date_taken ? new Date(pt.date_taken).toLocaleDateString() : 'N/A'} • (${pt.lat.toFixed(4)}, ${pt.lon.toFixed(4)})
                        </div>
                    </div>
                `);

                new Marker({ element: el })
                    .setLngLat([pt.lon, pt.lat])
                    .setPopup(popup)
                    .addTo(map.current!);
            }
        });

        if (validCoordsCount > 0 && map.current) {
            try {
                map.current.fitBounds(bounds, { padding: 60, maxZoom: 12 });
            } catch {}
        }
    }, [points]);

    const handleTestLookup = async (e: React.FormEvent) => {
        e.preventDefault();
        setTestingLookup(true);
        setTestResult(null);
        try {
            const res = await api.testGpsLookup(parseFloat(testLat), parseFloat(testLon));
            setTestResult(res);
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Test lookup failed: ${err.message}` });
        } finally {
            setTestingLookup(false);
        }
    };

    const handleSaveAlias = async (e: React.FormEvent) => {
        e.preventDefault();
        setSavingAlias(true);
        try {
            const res = await api.addUserLocationAlias({
                latitude: parseFloat(aliasLat),
                longitude: parseFloat(aliasLon),
                custom_name: aliasName,
                radius: parseFloat(aliasRadius || '0.05')
            });
            setStatusMsg({ type: 'success', text: `✓ Learned alias "${res.custom_name}" around (${res.latitude}, ${res.longitude})` });
            setShowAliasModal(false);
            setAliasName('');
            loadData();
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Failed to save alias: ${err.message}` });
        } finally {
            setSavingAlias(false);
        }
    };

    const handleRebuildCache = async () => {
        try {
            const res = await api.rebuildLocationCache();
            setStatusMsg({ type: 'success', text: `✓ ${res.message}` });
            loadData();
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Failed to rebuild cache: ${err.message}` });
        }
    };

    const handleRunHealthScan = async () => {
        try {
            const res = await api.runLocationHealthScan();
            setHealth(res);
            setStatusMsg({ 
                type: res.status === 'HEALTHY' ? 'success' : 'error', 
                text: `Location Health Scan: ${res.resolution_rate_pct}% resolved (${res.media_resolved_locations}/${res.media_with_gps} GPS media).` 
            });
        } catch (err: any) {
            setStatusMsg({ type: 'error', text: `Health scan failed: ${err.message}` });
        }
    };

    return (
        <div className="main-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div>
                    <h2 style={{ marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Globe size={22} color="var(--primary-color)" /> Location Intelligence & MapLibre Explorer
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
                        Local-first reverse geocoding with OpenStreetMap, GeoNames fallback, user alias learning, and interactive vector maps.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button className="btn" onClick={loadData} disabled={loading} style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
                    </button>
                    <button className="btn btn-primary" onClick={() => setShowAliasModal(true)} style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <PlusCircle size={14} /> Add Location Alias
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

            {/* STATUS & CONTROL BAR */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', marginBottom: '20px' }}>
                <div className="card" style={{ padding: '14px 16px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>OpenStreetMap (Nominatim)</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#10b981', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                        <Globe size={16} /> {status?.openstreetmap || 'ONLINE'}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Provider: OpenStreetMap</div>
                </div>

                <div className="card" style={{ padding: '14px 16px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>GeoNames Offline Gazetteer</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#3b82f6', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                        <Database size={16} /> {status?.geonames || 'READY'}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>{status?.geonames_cities_loaded || 32} cities loaded</div>
                </div>

                <div className="card" style={{ padding: '14px 16px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>SQLite Location Cache</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#8b5cf6', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                        <Layers size={16} /> {status?.cached_locations_count || 0} Places
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>{status?.user_aliases_count || 0} user aliases</div>
                </div>

                <div className="card" style={{ padding: '14px 16px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Actions & Audit</div>
                    <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                        <button className="btn" onClick={handleRebuildCache} style={{ fontSize: '10px', padding: '4px 8px' }}>
                            Rebuild Cache
                        </button>
                        <button className="btn" onClick={handleRunHealthScan} style={{ fontSize: '10px', padding: '4px 8px' }}>
                            Health Scan
                        </button>
                    </div>
                </div>
            </div>

            {/* HEALTH SCAN BANNER IF PRESENT */}
            {health && (
                <div className="card" style={{ padding: '14px 18px', marginBottom: '20px', backgroundColor: 'var(--bg-color)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <strong style={{ fontSize: '13px' }}>Location Health Coverage: {health.resolution_rate_pct}%</strong>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                {health.media_resolved_locations} of {health.media_with_gps} GPS media resolved • {health.cached_unique_locations} cached places • {health.user_aliases_learned} learned aliases
                            </div>
                        </div>
                        <span style={{
                            padding: '4px 10px',
                            borderRadius: '999px',
                            fontSize: '11px',
                            fontWeight: 700,
                            backgroundColor: health.status === 'HEALTHY' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                            color: health.status === 'HEALTHY' ? '#22c55e' : '#ef4444',
                        }}>
                            {health.status}
                        </span>
                    </div>
                </div>
            )}

            {/* MAP & SIDEBAR SPLIT */}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px', marginBottom: '24px' }}>
                {/* MAPLIBRE GL CANVAS */}
                <div className="card" style={{ padding: '12px', minHeight: '520px', display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', padding: '0 4px' }}>
                        <strong style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Compass size={16} color="var(--primary-color)" /> Interactive World Photo Pins ({points.length} locations)
                        </strong>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>MapLibre Vector GL</span>
                    </div>
                    <div 
                        ref={mapContainer} 
                        style={{ 
                            flex: 1, 
                            width: '100%', 
                            minHeight: '460px', 
                            borderRadius: '8px',
                            backgroundColor: '#1a1a2e',
                            overflow: 'hidden'
                        }} 
                    />
                </div>

                {/* LOCATIONS STATS & TEST LOOKUP */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {/* TEST GPS LOOKUP FORM */}
                    <div className="card" style={{ padding: '16px' }}>
                        <h3 style={{ margin: '0 0 10px 0', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Search size={15} /> Test GPS Lookup
                        </h3>
                        <form onSubmit={handleTestLookup} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <input 
                                    type="text" 
                                    placeholder="Latitude" 
                                    value={testLat} 
                                    onChange={e => setTestLat(e.target.value)}
                                    style={{ flex: 1, padding: '6px 10px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '12px' }}
                                />
                                <input 
                                    type="text" 
                                    placeholder="Longitude" 
                                    value={testLon} 
                                    onChange={e => setTestLon(e.target.value)}
                                    style={{ flex: 1, padding: '6px 10px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '12px' }}
                                />
                            </div>
                            <button className="btn btn-primary" type="submit" disabled={testingLookup} style={{ fontSize: '11px', padding: '6px' }}>
                                {testingLookup ? 'Resolving…' : 'Test Reverse Geocode'}
                            </button>
                        </form>

                        {testResult && (
                            <div style={{ marginTop: '12px', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)', fontSize: '11px' }}>
                                <div style={{ fontWeight: 700, color: 'var(--primary-color)', fontSize: '12px' }}>{testResult.place_name}</div>
                                <div style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>
                                    Source: <strong>{testResult.source}</strong> (Confidence: {testResult.confidence}%)
                                </div>
                                <div style={{ color: 'var(--text-secondary)' }}>
                                    {testResult.city}, {testResult.state}, {testResult.country}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* TOP VISITED PLACES RANKING */}
                    <div className="card" style={{ padding: '16px', flex: 1, overflowY: 'auto', maxHeight: '340px' }}>
                        <h3 style={{ margin: '0 0 10px 0', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <MapPin size={15} color="#06b6d4" /> Top Places ({stats.length})
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {stats.length === 0 ? (
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>No location tags yet.</div>
                            ) : (
                                stats.map((st, idx) => (
                                    <div key={idx} style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        padding: '8px 10px',
                                        borderRadius: '6px',
                                        backgroundColor: 'var(--bg-color)',
                                        border: '1px solid var(--border-color)',
                                        fontSize: '11px'
                                    }}>
                                        <span style={{ fontWeight: 600 }}>📍 {st.name}</span>
                                        <span style={{ color: '#06b6d4', fontWeight: 700 }}>{st.count} photos</span>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* USER ALIAS MODAL */}
            {showAliasModal && (
                <div style={{
                    position: 'fixed',
                    top: 0, left: 0, right: 0, bottom: 0,
                    backgroundColor: 'rgba(0,0,0,0.6)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1000
                }}>
                    <div className="card" style={{ width: '420px', padding: '24px', position: 'relative' }}>
                        <h3 style={{ margin: '0 0 8px 0', fontSize: '15px' }}>Learn Custom Location Alias</h3>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '0 0 16px 0' }}>
                            Teach the system your personalized place name (e.g. "Disney World" or "Home") for GPS coordinates.
                        </p>
                        <form onSubmit={handleSaveAlias} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Custom Name (e.g. Disney World)</label>
                                <input 
                                    type="text" 
                                    required 
                                    placeholder="e.g. Disney World" 
                                    value={aliasName} 
                                    onChange={e => setAliasName(e.target.value)}
                                    style={{ width: '100%', padding: '8px 12px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '12px' }}
                                />
                            </div>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Latitude</label>
                                    <input 
                                        type="text" 
                                        required 
                                        placeholder="28.3772" 
                                        value={aliasLat} 
                                        onChange={e => setAliasLat(e.target.value)}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '12px' }}
                                    />
                                </div>
                                <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Longitude</label>
                                    <input 
                                        type="text" 
                                        required 
                                        placeholder="-81.5707" 
                                        value={aliasLon} 
                                        onChange={e => setAliasLon(e.target.value)}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '12px' }}
                                    />
                                </div>
                            </div>
                            <div>
                                <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Radius (in degrees, ~0.05 is ~5km)</label>
                                <input 
                                    type="text" 
                                    placeholder="0.05" 
                                    value={aliasRadius} 
                                    onChange={e => setAliasRadius(e.target.value)}
                                    style={{ width: '100%', padding: '6px 10px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)', fontSize: '12px' }}
                                />
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                                <button className="btn" type="button" onClick={() => setShowAliasModal(false)}>Cancel</button>
                                <button className="btn btn-primary" type="submit" disabled={savingAlias}>
                                    {savingAlias ? 'Saving…' : 'Save & Learn Alias'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};
