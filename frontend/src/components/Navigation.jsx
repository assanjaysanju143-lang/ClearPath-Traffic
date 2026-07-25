import { useState, useEffect, useRef, useCallback } from 'react'
import styles from './Navigation.module.css'
import { API_BASE } from '../api'

const LEVEL_COLOR = { LOW: '#17803d', MODERATE: '#b45309', HIGH: '#c0292a' }

// Voice instruction using Web Speech API
function speak(text) {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 0.95
  u.pitch = 1
  u.volume = 1
  window.speechSynthesis.speak(u)
}

// Generate user ID once per session
function getUserId() {
  let id = sessionStorage.getItem('clearpath_uid')
  if (!id) { id = Math.random().toString(36).slice(2, 10); sessionStorage.setItem('clearpath_uid', id) }
  return id
}

export default function Navigation({ onRouteAssigned, onLocationUpdate }) {
  const [phase, setPhase]           = useState('idle')    // idle | locating | destination | navigating | arrived | manualForm | manualResults
  const [location, setLocation]     = useState(null)
  const [destination, setDestination] = useState('')
  const [originText, setOriginText] = useState('')
  const [nlQuery, setNlQuery]       = useState('')
  const [assignment, setAssignment] = useState(null)
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError]           = useState(null)
  const [loading, setLoading]       = useState(false)
  const [voiceOn, setVoiceOn]       = useState(true)
  const [distTravelled, setDistTravelled] = useState(0)
  const [speed, setSpeed]           = useState(0)

  const watchRef    = useRef(null)
  const prevPos     = useRef(null)
  const userId      = useRef(getUserId())
  const navStartTime = useRef(null)
  const destInputRef = useRef()

  // ── Manual lookup: type both places, no GPS involved ──────
  // Uses a throwaway user id so "just checking" never occupies a real
  // driver's slot in the load-balancer — that's only for people who tap
  // "Start Navigation" and actually drive the route.
  const fetchRouteManual = useCallback(async () => {
    if (!originText.trim() || !destination.trim()) return
    setLoading(true)
    setError(null)
    const lookupId = `lookup_${Math.random().toString(36).slice(2, 10)}`

    try {
      const res = await fetch(
        `${API_BASE}/routes?origin=${encodeURIComponent(originText)}&destination=${encodeURIComponent(destination)}&user_id=${lookupId}`
      )
      if (!res.ok) throw new Error('Backend error')
      const data = await res.json()

      setAssignment(data)
      onRouteAssigned?.(data)
      setPhase('manualResults')

      // This was just a lookup, not a real drive — free the slot right away
      // so it doesn't skew live route-load numbers for actual drivers.
      fetch(`${API_BASE}/routes/release?user_id=${lookupId}`, { method: 'DELETE' }).catch(() => {})
    } catch (e) {
      setError('Could not fetch route. Make sure backend is running.')
    } finally {
      setLoading(false)
    }
  }, [originText, destination, onRouteAssigned])

  // ── Natural-language lookup: one free-text box, parsed server-side ──
  // Also a throwaway lookup (not a committed drive), same reasoning as above.
  const fetchRouteNL = useCallback(async () => {
    if (!nlQuery.trim()) return
    setLoading(true)
    setError(null)
    const lookupId = `nl_${Math.random().toString(36).slice(2, 10)}`

    // Best-effort GPS fallback in case the query doesn't mention an origin
    // (e.g. "take me to Whitefield"). Not required — /smart will 400 with a
    // clear message if there's truly no origin to work with.
    const tryGetLocation = () => new Promise((resolve) => {
      if (!navigator.geolocation) return resolve(null)
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(`${pos.coords.latitude},${pos.coords.longitude}`),
        () => resolve(null),
        { timeout: 3000 }
      )
    })

    try {
      const fallback = await tryGetLocation()
      let url = `${API_BASE}/routes/smart?query=${encodeURIComponent(nlQuery)}&user_id=${lookupId}`
      if (fallback) url += `&origin_fallback=${encodeURIComponent(fallback)}`

      const res = await fetch(url)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || 'Backend error')
      }
      const data = await res.json()

      setAssignment(data)
      onRouteAssigned?.(data)
      setPhase('nlResults')

      fetch(`${API_BASE}/routes/release?user_id=${lookupId}`, { method: 'DELETE' }).catch(() => {})
    } catch (e) {
      setError(e.message || 'Could not fetch route. Make sure backend is running.')
    } finally {
      setLoading(false)
    }
  }, [nlQuery, onRouteAssigned])

  // ── Step 1: Get GPS location ─────────────────────────────
  const startLocating = useCallback(() => {
    setPhase('locating')
    setError(null)
    if (!navigator.geolocation) {
      setError('GPS not supported on this browser.')
      setPhase('idle')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const loc = { lat: pos.coords.latitude, lon: pos.coords.longitude }
        setLocation(loc)
        onLocationUpdate?.(loc)
        setPhase('destination')
        setTimeout(() => destInputRef.current?.focus(), 300)
      },
      (err) => {
        setError('Could not get your location. Please allow GPS access.')
        setPhase('idle')
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }, [onLocationUpdate])

  // ── Step 2: Fetch smart route assignment ─────────────────
  const fetchRoute = useCallback(async () => {
    if (!destination.trim() || !location) return
    setLoading(true)
    setError(null)

    try {
      const origin = `${location.lat},${location.lon}`
      const res = await fetch(
        `${API_BASE}/routes?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&user_id=${userId.current}`
      )
      if (!res.ok) throw new Error('Backend error')
      const data = await res.json()

      setAssignment(data)
      onRouteAssigned?.(data)
      setPhase('navigating')
      setCurrentStep(0)
      navStartTime.current = Date.now()

      if (voiceOn) {
        const route = data.assigned_route
        speak(`Starting navigation. ${data.reason} Your route is ${route.label}. Estimated ${route.eta_minutes} minutes.`)
      }

      // Start GPS tracking
      startTracking()
    } catch (e) {
      setError('Could not fetch route. Make sure backend is running.')
    } finally {
      setLoading(false)
    }
  }, [destination, location, voiceOn, onRouteAssigned])

  // ── Step 3: Live GPS tracking while driving ───────────────
  const startTracking = useCallback(() => {
    if (watchRef.current) return
    watchRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        const loc = { lat: pos.coords.latitude, lon: pos.coords.longitude }
        setLocation(loc)
        onLocationUpdate?.(loc)

        // Calculate speed from GPS
        if (pos.coords.speed != null) {
          setSpeed(Math.round(pos.coords.speed * 3.6)) // m/s → km/h
        }

        // Calculate distance travelled
        if (prevPos.current) {
          const d = haversine(prevPos.current, loc)
          setDistTravelled(prev => prev + d)
        }
        prevPos.current = loc

        // Auto-advance steps based on distance
        if (assignment?.assigned_route?.steps) {
          const steps = assignment.assigned_route.steps
          if (currentStep < steps.length - 1) {
            const stepDist = steps[currentStep]?.distance_m || 500
            if (distTravelled * 1000 > stepDist * 0.9) {
              const next = currentStep + 1
              setCurrentStep(next)
              if (voiceOn && steps[next]) {
                speak(steps[next].instruction)
              }
            }
          }
        }
      },
      (err) => console.warn('GPS watch error', err),
      { enableHighAccuracy: true, maximumAge: 3000, timeout: 10000 }
    )
  }, [assignment, currentStep, distTravelled, voiceOn, onLocationUpdate])

  const stopTracking = useCallback(() => {
    if (watchRef.current) {
      navigator.geolocation.clearWatch(watchRef.current)
      watchRef.current = null
    }
  }, [])

  const arriveDestination = useCallback(() => {
    stopTracking()
    const actualMinutes = navStartTime.current
      ? Math.round((Date.now() - navStartTime.current) / 60000 * 10) / 10
      : null
    let url = `${API_BASE}/routes/release?user_id=${userId.current}`
    if (actualMinutes !== null) url += `&actual_minutes=${actualMinutes}`
    fetch(url, { method: 'DELETE' }).catch(() => {})
    setPhase('arrived')
    if (voiceOn) speak('You have arrived at your destination!')
  }, [stopTracking, voiceOn])

  const reset = useCallback(() => {
    stopTracking()
    setPhase('idle')
    setAssignment(null)
    setDestination('')
    setOriginText('')
    setNlQuery('')
    setCurrentStep(0)
    setDistTravelled(0)
    setSpeed(0)
    prevPos.current = null
  }, [stopTracking])

  useEffect(() => () => stopTracking(), [stopTracking])

  const route  = assignment?.assigned_route
  const steps  = route?.steps || []
  const step   = steps[currentStep]
  const lcolor = LEVEL_COLOR[route?.congestion_level] || '#17803d'

  // ── Render ───────────────────────────────────────────────
  return (
    <div className={styles.nav}>

      {/* IDLE */}
      {phase === 'idle' && (
        <div className={styles.idle}>
          <div className={styles.idleIcon}>◎</div>
          <p className={styles.idleText}>Driving right now, or just checking traffic?</p>
          <button className={styles.startBtn} onClick={startLocating}>
            🚗 Start Navigation (uses GPS)
          </button>
          <button
            className={styles.startBtn}
            style={{ background: 'transparent', border: '1px solid var(--border2)', color: 'var(--text)', marginTop: 10 }}
            onClick={() => setPhase('manualForm')}
          >
            🔍 Check Traffic — Type Both Places
          </button>
          <button
            className={styles.startBtn}
            style={{ background: 'transparent', border: '1px solid var(--border2)', color: 'var(--text)', marginTop: 10 }}
            onClick={() => setPhase('nlForm')}
          >
            🗣️ Just Type What You Want
          </button>
        </div>
      )}

      {/* NATURAL LANGUAGE FORM — one free-text box, parsed server-side */}
      {phase === 'nlForm' && (
        <div className={styles.destPhase}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 4 }}>
            <label style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-display)', letterSpacing: '0.06em' }}>
              TYPE YOUR REQUEST
            </label>
            <textarea
              className={styles.destInput}
              style={{ minHeight: 70, resize: 'vertical', fontFamily: 'var(--font-body)' }}
              placeholder="e.g. fastest way to Whitefield from Koramangala avoiding Sarjapur Road"
              value={nlQuery}
              onChange={e => setNlQuery(e.target.value)}
            />
            <span style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 1.5 }}>
              You can mention both places and anything to avoid — e.g. tolls, a specific road. If you leave out "from", your current GPS location is used instead.
            </span>
          </div>
          <button
            className={styles.goBtn}
            onClick={fetchRouteNL}
            disabled={loading || !nlQuery.trim()}
          >
            {loading ? <span className={styles.spinner} /> : 'Find My Route →'}
          </button>
          <button
            className={styles.secondaryBtn}
            style={{ marginTop: 8 }}
            onClick={() => { setPhase('idle'); setError(null) }}
          >
            ← Back
          </button>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}

      {/* NATURAL LANGUAGE RESULTS */}
      {phase === 'nlResults' && route && (
        <div className={styles.navigating}>
          <div className={styles.assignBanner} style={{ borderColor: lcolor, background: lcolor + '12' }}>
            <div className={styles.assignTop}>
              <span className={styles.assignLabel}>{assignment.origin} → {assignment.destination}</span>
              <span className={styles.assignBadge} style={{ color: lcolor, borderColor: lcolor + '55' }}>
                {route.congestion_level}
              </span>
            </div>
            <div className={styles.assignName}>{route.label}</div>
            {route.avoided_because && (
              <div style={{ fontSize: 11, color: 'var(--amber)', marginTop: 4 }}>
                ⚠ This route passes through "{route.avoided_because}" — the thing you asked to avoid. Showing it anyway since alternatives were worse.
              </div>
            )}
            <div className={styles.assignReason}>{assignment.reason}</div>
            <div className={styles.assignMeta}>
              <span style={{ color: lcolor }}>⏱ {route.eta_minutes} min</span>
              <span>📍 {route.distance_km} km</span>
            </div>
            {assignment.parsed_query?.avoid?.length > 0 && (
              <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 6 }}>
                Avoiding: {assignment.parsed_query.avoid.join(', ')}
              </div>
            )}
          </div>

          <div className={styles.allSteps}>
            {steps.map((s, i) => (
              <div key={i} className={styles.stepRow}>
                <div className={styles.stepDot} style={{ background: lcolor }} />
                <span>{s.instruction}</span>
              </div>
            ))}
          </div>

          <div className={styles.controls}>
            <button className={styles.secondaryBtn} style={{ flex: 1 }} onClick={() => setPhase('nlForm')}>← New Search</button>
          </div>
        </div>
      )}

      {/* MANUAL FORM — no GPS, type any origin + destination */}
      {phase === 'manualForm' && (
        <div className={styles.destPhase}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 4 }}>
            <label style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-display)', letterSpacing: '0.06em' }}>FROM</label>
            <input
              className={styles.destInput}
              placeholder="e.g. Koramangala"
              value={originText}
              onChange={e => setOriginText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && fetchRouteManual()}
              autoFocus
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 4 }}>
            <label style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-display)', letterSpacing: '0.06em' }}>TO</label>
            <input
              className={styles.destInput}
              placeholder="e.g. Whitefield"
              value={destination}
              onChange={e => setDestination(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && fetchRouteManual()}
            />
          </div>
          <button
            className={styles.goBtn}
            onClick={fetchRouteManual}
            disabled={loading || !originText.trim() || !destination.trim()}
          >
            {loading ? <span className={styles.spinner} /> : 'Check Routes →'}
          </button>
          <button
            className={styles.secondaryBtn}
            style={{ marginTop: 8 }}
            onClick={() => { setPhase('idle'); setError(null) }}
          >
            ← Back
          </button>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}

      {/* MANUAL RESULTS — static lookup, no live tracking, no GPS */}
      {phase === 'manualResults' && route && (
        <div className={styles.navigating}>
          <div className={styles.assignBanner} style={{ borderColor: lcolor, background: lcolor + '12' }}>
            <div className={styles.assignTop}>
              <span className={styles.assignLabel}>{originText} → {destination}</span>
              <span className={styles.assignBadge} style={{ color: lcolor, borderColor: lcolor + '55' }}>
                {route.congestion_level}
              </span>
            </div>
            <div className={styles.assignName}>{route.label}</div>
            <div className={styles.assignReason}>{assignment.reason}</div>
            <div className={styles.assignMeta}>
              <span style={{ color: lcolor }}>⏱ {route.eta_minutes} min</span>
              <span>📍 {route.distance_km} km</span>
            </div>
          </div>

          <div className={styles.allSteps}>
            {steps.map((s, i) => (
              <div key={i} className={styles.stepRow}>
                <div className={styles.stepDot} style={{ background: lcolor }} />
                <span>{s.instruction}</span>
              </div>
            ))}
          </div>

          <div className={styles.controls}>
            <button className={styles.secondaryBtn} style={{ flex: 1 }} onClick={() => setPhase('manualForm')}>← New Search</button>
          </div>
        </div>
      )}

      {/* LOCATING */}
      {phase === 'locating' && (
        <div className={styles.locating}>
          <div className={styles.spinner} />
          <p>Getting your location...</p>
        </div>
      )}

      {/* DESTINATION INPUT */}
      {phase === 'destination' && (
        <div className={styles.destPhase}>
          <div className={styles.gpsConfirm}>
            <span className={styles.gpsDot} />
            <span>GPS locked — {location?.lat.toFixed(4)}, {location?.lon.toFixed(4)}</span>
          </div>
          <input
            ref={destInputRef}
            className={styles.destInput}
            placeholder="Where are you going?"
            value={destination}
            onChange={e => setDestination(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && fetchRoute()}
          />
          <button className={styles.goBtn} onClick={fetchRoute} disabled={loading || !destination.trim()}>
            {loading ? <span className={styles.spinner} /> : 'Find Best Route →'}
          </button>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}

      {/* NAVIGATING */}
      {phase === 'navigating' && route && (
        <div className={styles.navigating}>

          {/* Route assignment banner */}
          <div className={styles.assignBanner} style={{ borderColor: lcolor, background: lcolor + '12' }}>
            <div className={styles.assignTop}>
              <span className={styles.assignLabel}>YOUR ROUTE</span>
              <span className={styles.assignBadge} style={{ color: lcolor, borderColor: lcolor + '55' }}>
                {route.congestion_level}
              </span>
            </div>
            <div className={styles.assignName}>{route.label}</div>
            <div className={styles.assignReason}>{assignment.reason}</div>
            <div className={styles.assignMeta}>
              <span style={{ color: lcolor }}>⏱ {route.eta_minutes} min</span>
              <span>📍 {route.distance_km} km</span>
              <span>👥 {assignment.active_users_on_route} users on this route</span>
            </div>
          </div>

          {/* Live HUD */}
          <div className={styles.hud}>
            <div className={styles.hudItem}>
              <span className={styles.hudLabel}>SPEED</span>
              <span className={styles.hudVal}>{speed}<small>km/h</small></span>
            </div>
            <div className={styles.hudItem}>
              <span className={styles.hudLabel}>ETA</span>
              <span className={styles.hudVal} style={{ color: lcolor }}>{route.eta_minutes}<small>min</small></span>
            </div>
            <div className={styles.hudItem}>
              <span className={styles.hudLabel}>DIST</span>
              <span className={styles.hudVal}>{route.distance_km}<small>km</small></span>
            </div>
          </div>

          {/* Current instruction */}
          {step && (
            <div className={styles.instruction}>
              <div className={styles.stepNum}>{currentStep + 1}/{steps.length}</div>
              <div className={styles.stepText}>{step.instruction}</div>
              {step.distance_m > 0 && (
                <div className={styles.stepDist}>in {(step.distance_m / 1000).toFixed(1)} km</div>
              )}
            </div>
          )}

          {/* All steps */}
          <div className={styles.allSteps}>
            {steps.map((s, i) => (
              <div key={i} className={`${styles.stepRow} ${i === currentStep ? styles.activeStep : ''} ${i < currentStep ? styles.doneStep : ''}`}>
                <div className={styles.stepDot} style={{ background: i <= currentStep ? lcolor : 'var(--border2)' }} />
                <span>{s.instruction}</span>
              </div>
            ))}
          </div>

          {/* Controls */}
          <div className={styles.controls}>
            <button
              className={styles.voiceBtn}
              onClick={() => { setVoiceOn(v => !v); speak(voiceOn ? '' : 'Voice on') }}
              style={{ borderColor: voiceOn ? lcolor : 'var(--border)', color: voiceOn ? lcolor : 'var(--text3)' }}
            >
              {voiceOn ? '🔊 Voice On' : '🔇 Voice Off'}
            </button>
            <button className={styles.arrivedBtn} onClick={arriveDestination}>
              ✓ I've Arrived
            </button>
            <button className={styles.stopBtn} onClick={reset}>✕</button>
          </div>
        </div>
      )}

      {/* ARRIVED */}
      {phase === 'arrived' && (
        <div className={styles.arrived}>
          <div className={styles.arrivedIcon}>✓</div>
          <p className={styles.arrivedText}>You've arrived!</p>
          <p className={styles.arrivedSub}>Route slot released — helping balance traffic for others.</p>
          <button className={styles.startBtn} onClick={reset}>New Navigation</button>
        </div>
      )}
    </div>
  )
}

// Haversine distance in km
function haversine(a, b) {
  const R = 6371
  const dLat = (b.lat - a.lat) * Math.PI / 180
  const dLon = (b.lon - a.lon) * Math.PI / 180
  const x = Math.sin(dLat/2) ** 2 + Math.cos(a.lat * Math.PI/180) * Math.cos(b.lat * Math.PI/180) * Math.sin(dLon/2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1-x))
}
