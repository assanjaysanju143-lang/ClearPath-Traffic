import { useState, useCallback, useEffect } from 'react'
import MapView from './components/MapView'
import Navigation from './components/Navigation'
import MLDetector from './components/MLDetector'
import StatsBar from './components/StatsBar'
import RouteLoadBar from './components/RouteLoadBar'
import IncidentsPanel from './components/IncidentsPanel'
import { fetchIncidents } from './api'
import styles from './App.module.css'

// Bengaluru bounding box used to poll for incidents when no route is active yet
const BLR_BBOX = { minLat: 12.83, minLon: 77.46, maxLat: 13.10, maxLon: 77.78 }

export default function App() {
  const [routeData, setRouteData]   = useState(null)
  const [routeLoads, setRouteLoads] = useState([])
  const [userLocation, setUserLocation] = useState(null)
  const [selectedRoute, setSelectedRoute] = useState(0)
  const [activeTab, setActiveTab] = useState('navigate') // 'navigate' | 'detect'
  const [incidents, setIncidents] = useState([])
  const [panelsOpen, setPanelsOpen] = useState(false)
  const [incidentsOpen, setIncidentsOpen] = useState(false)

  const handleRouteAssigned = useCallback((data) => {
    // Build routeData shape MapView expects
    setRouteData({
      routes: data.all_routes,
      assigned_route: data.assigned_route,
    })
    setRouteLoads(data.route_loads || [])
    const idx = data.all_routes.findIndex(r => r.route_id === data.assigned_route.route_id)
    setSelectedRoute(idx >= 0 ? idx : 0)
  }, [])

  const handleLocationUpdate = useCallback((loc) => {
    setUserLocation(loc)
  }, [])

  // Poll live incidents so the map/panel reflect current road conditions
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await fetchIncidents(BLR_BBOX.minLat, BLR_BBOX.minLon, BLR_BBOX.maxLat, BLR_BBOX.maxLon)
        if (!cancelled) setIncidents(data.incidents || [])
      } catch {
        // Silently keep previous incidents if a poll fails
      }
    }
    load()
    const id = setInterval(load, 60000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return (
    <div className={styles.app}>
      {/* Sidebar */}
      <div className={styles.sidebar}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.logo}>
            <span className={styles.logoIcon}>⬡</span>
            <span className={styles.logoText}>ClearPath</span>
          </div>
          <p className={styles.tagline}>Smart routing. Less traffic. Every drive.</p>
        </div>

        {/* Tab switcher */}
        <div style={{ display: 'flex', gap: 6, padding: '0 28px', marginTop: 4 }}>
          {[
            { key: 'navigate', label: '🧭 Navigate' },
            { key: 'detect', label: '🚗 Vehicle Detection' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                flex: 1, padding: '10px 12px', borderRadius: 6, cursor: 'pointer',
                fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700,
                letterSpacing: '0.06em',
                background: activeTab === tab.key ? 'var(--primary-dim)' : 'var(--bg3)',
                border: `1px solid ${activeTab === tab.key ? 'var(--primary)' : 'var(--border)'}`,
                color: activeTab === tab.key ? 'var(--primary)' : 'var(--text3)',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Navigation — main feature */}
        {activeTab === 'navigate' && (
          <Navigation
            onRouteAssigned={handleRouteAssigned}
            onLocationUpdate={handleLocationUpdate}
          />
        )}

        {/* ML vehicle detection panel */}
        {activeTab === 'detect' && <MLDetector />}
      </div>

      {/* Map */}
      <div className={styles.mapArea}>
        <MapView
          routes={routeData?.routes}
          selectedRoute={selectedRoute}
          userLocation={userLocation}
          incidents={incidents}
        />
        {!routeData && (
          <div className={styles.mapOverlay}>
            <span>Tap "Start Navigation" to begin</span>
          </div>
        )}
        {routeData && (
          <>
            <div className={styles.topPanels}>
              <button className={styles.panelToggle} onClick={() => setPanelsOpen(o => !o)}>
                📊 Route info {panelsOpen ? '▲' : '▼'}
              </button>
              {panelsOpen && (
                <div className={styles.panelStack}>
                  <StatsBar data={routeData} />
                  <RouteLoadBar routes={routeData.routes} routeLoads={routeLoads} />
                </div>
              )}
            </div>
            <div className={styles.legend}>
              <span style={{ color: '#17803d', fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 600 }}>— Your route</span>
              <span style={{ color: '#b45309', fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 600 }}>— Alternate</span>
              <span style={{ color: '#c0292a', fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 600 }}>— Heavy traffic</span>
            </div>
          </>
        )}
        {incidents.length > 0 && (
          <div className={styles.incidentsOverlay}>
            <button className={styles.panelToggle} onClick={() => setIncidentsOpen(o => !o)}>
              ⚠ {incidents.length} incident{incidents.length === 1 ? '' : 's'} {incidentsOpen ? '▲' : '▼'}
            </button>
            {incidentsOpen && <IncidentsPanel incidents={incidents} />}
          </div>
        )}
      </div>
    </div>
  )
}
