/**
 * MLDetector.jsx
 * Drop this into your traffic-frontend/src/components/ folder.
 * Lets users upload a road image OR use webcam → sends to ML API → shows annotated result.
 */

import { useState, useRef, useCallback } from 'react'
import { ML_API_BASE, API_BASE } from '../api'

const ML_API = ML_API_BASE

const LEVEL_COLORS = {
  LOW:      { color: '#17803d', bg: '#17803d18' },
  MODERATE: { color: '#b45309', bg: '#b4530918' },
  HIGH:     { color: '#c0292a', bg: '#c0292a18' },
}

export default function MLDetector() {
  const [mode, setMode]             = useState('upload')  // upload | webcam
  const [loading, setLoading]       = useState(false)
  const [result, setResult]         = useState(null)
  const [error, setError]           = useState(null)
  const [preview, setPreview]       = useState(null)
  const [webcamActive, setWebcamActive] = useState(false)
  const [locationName, setLocationName] = useState('')
  const [forecast, setForecast] = useState(null)

  const fileRef    = useRef()
  const videoRef   = useRef()
  const canvasRef  = useRef()
  const streamRef  = useRef()
  const intervalRef = useRef()

  const sendToML = useCallback(async (b64) => {
    setLoading(true)
    setError(null)
    setForecast(null)
    try {
      const res = await fetch(`${ML_API}/detect/base64`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: b64, return_image: true, location_name: locationName.trim() || null }),
      })
      if (!res.ok) throw new Error(`ML API error: ${res.status}`)
      const data = await res.json()
      setResult(data)

      // If this reading was tied to a named location, check whether we now
      // have enough history at that spot to say if it's trending worse.
      if (data.reported_to_backend && locationName.trim()) {
        fetch(`${API_BASE}/traffic/forecast?location_name=${encodeURIComponent(locationName.trim())}`)
          .then(r => r.json())
          .then(setForecast)
          .catch(() => {})
      }
    } catch (e) {
      setError('ML API not running. Start it with: py -3.12 run.py --server')
    } finally {
      setLoading(false)
    }
  }, [locationName])

  const handleFileChange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async (ev) => {
      const b64 = ev.target.result
      setPreview(b64)
      await sendToML(b64)
    }
    reader.readAsDataURL(file)
  }

  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true })
      streamRef.current = stream
      videoRef.current.srcObject = stream
      await videoRef.current.play()
      setWebcamActive(true)

      // Capture and detect every 2 seconds
      intervalRef.current = setInterval(() => {
        const canvas = canvasRef.current
        const video  = videoRef.current
        if (!canvas || !video) return
        canvas.width  = video.videoWidth
        canvas.height = video.videoHeight
        canvas.getContext('2d').drawImage(video, 0, 0)
        const b64 = canvas.toDataURL('image/jpeg', 0.8)
        sendToML(b64)
      }, 2000)
    } catch {
      setError('Could not access webcam.')
    }
  }

  const stopWebcam = () => {
    clearInterval(intervalRef.current)
    streamRef.current?.getTracks().forEach(t => t.stop())
    setWebcamActive(false)
  }

  const colors = result ? (LEVEL_COLORS[result.density_level] || LEVEL_COLORS.LOW) : null

  return (
    <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--text3)', fontFamily: 'var(--font-display)' }}>
        ML VEHICLE DETECTION
      </div>

      {/* Location name — ties this camera's reading to a point on the route graph */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-display)', letterSpacing: '0.06em' }}>
          CAMERA LOCATION (OPTIONAL)
        </label>
        <input
          value={locationName}
          onChange={e => setLocationName(e.target.value)}
          placeholder="e.g. Outer Ring Road, Marathahalli Bridge"
          style={{
            padding: '9px 12px', borderRadius: 6, background: 'var(--bg3)',
            border: '1px solid var(--border2)', color: 'var(--text)', fontSize: 12,
            fontFamily: 'var(--font-body)',
          }}
        />
        <span style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 1.5 }}>
          Naming a location feeds this reading straight into route scoring — matching routes get re-ranked using what the camera actually sees.
        </span>
      </div>

      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: 6 }}>
        {['upload', 'webcam'].map(m => (
          <button key={m} onClick={() => { setMode(m); setResult(null); setError(null) }}
            style={{
              flex: 1, padding: '8px 12px', borderRadius: 6, cursor: 'pointer',
              fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700,
              letterSpacing: '0.06em', textTransform: 'uppercase',
              background: mode === m ? 'var(--primary-dim)' : 'var(--bg3)',
              border: `1px solid ${mode === m ? 'var(--primary)' : 'var(--border)'}`,
              color: mode === m ? 'var(--primary)' : 'var(--text3)',
            }}>
            {m === 'upload' ? '📁 Upload Image' : '📷 Live Webcam'}
          </button>
        ))}
      </div>

      {/* Upload mode */}
      {mode === 'upload' && (
        <div
          onClick={() => fileRef.current.click()}
          style={{
            border: '1px dashed var(--border2)', borderRadius: 8, padding: '24px',
            textAlign: 'center', cursor: 'pointer', background: 'var(--bg3)',
            transition: 'border-color 0.2s',
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 8 }}>🚗</div>
          <div style={{ fontSize: 13, color: 'var(--text2)' }}>Click to upload road image</div>
          <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>JPG, PNG supported</div>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleFileChange} />
        </div>
      )}

      {/* Webcam mode */}
      {mode === 'webcam' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <video ref={videoRef} style={{ width: '100%', borderRadius: 8, background: '#000', display: webcamActive ? 'block' : 'none' }} muted />
          <canvas ref={canvasRef} style={{ display: 'none' }} />
          {!webcamActive
            ? <button onClick={startWebcam} style={{ padding: '10px', background: 'var(--primary)', color: 'var(--primary-text)', border: 'none', borderRadius: 6, fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Start Camera</button>
            : <button onClick={stopWebcam} style={{ padding: '10px', background: 'var(--red-dim)', color: 'var(--red)', border: '1px solid var(--red)', borderRadius: 6, fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Stop Camera</button>
          }
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '12px', fontSize: 12, color: 'var(--text3)' }}>
          <span style={{ display: 'inline-block', width: 16, height: 16, border: '2px solid var(--border2)', borderTopColor: 'var(--primary)', borderRadius: '50%', animation: 'spin 0.7s linear infinite', marginRight: 8, verticalAlign: 'middle' }} />
          Detecting vehicles...
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ padding: '10px 12px', background: 'var(--red-dim)', border: '1px solid var(--red)', borderRadius: 6, fontSize: 12, color: 'var(--red)', lineHeight: 1.6 }}>
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, animation: 'fadeUp 0.3s ease' }}>
          {result.reported_to_backend && (
            <div style={{ padding: '8px 12px', background: 'var(--green-dim)', border: '1px solid var(--green)', borderRadius: 6, fontSize: 11, color: 'var(--green)', fontFamily: 'var(--font-display)', fontWeight: 600 }}>
              ✓ Reported to routing engine — routes near "{locationName}" now reflect this reading
            </div>
          )}
          {forecast && forecast.status === 'ok' && (
            <div style={{
              padding: '8px 12px', borderRadius: 6, fontSize: 11, lineHeight: 1.6,
              background: forecast.trend === 'worsening' ? 'var(--red-dim)' : forecast.trend === 'improving' ? 'var(--green-dim)' : 'var(--bg3)',
              border: `1px solid ${forecast.trend === 'worsening' ? 'var(--red)' : forecast.trend === 'improving' ? 'var(--green)' : 'var(--border2)'}`,
              color: forecast.trend === 'worsening' ? 'var(--red)' : forecast.trend === 'improving' ? 'var(--green)' : 'var(--text2)',
            }}>
              {forecast.trend === 'worsening' && '📈 Trending worse'}
              {forecast.trend === 'improving' && '📉 Trending better'}
              {forecast.trend === 'steady' && '➡ Holding steady'}
              {forecast.minutes_until_high_congestion != null && (
                <> — expected to hit HIGH congestion in ~{forecast.minutes_until_high_congestion} min</>
              )}
              <div style={{ fontSize: 10, opacity: 0.75, marginTop: 2 }}>
                based on {forecast.points_available} readings at this location over the last few minutes
              </div>
            </div>
          )}
          {forecast && forecast.status === 'insufficient_data' && (
            <div style={{ padding: '8px 12px', background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 6, fontSize: 11, color: 'var(--text3)' }}>
              Not enough history at "{locationName}" yet to predict a trend — report a few more readings here over the next few minutes.
            </div>
          )}
          {!result.reported_to_backend && locationName.trim() && (
            <div style={{ padding: '8px 12px', background: 'var(--amber-dim)', border: '1px solid var(--amber)', borderRadius: 6, fontSize: 11, color: 'var(--amber)' }}>
              Detected, but couldn't reach the routing backend to report it. Make sure it's running on port 8000.
            </div>
          )}
          {/* Annotated image */}
          {result.annotated_image_b64 && (
            <img
              src={`data:image/jpeg;base64,${result.annotated_image_b64}`}
              alt="Detection result"
              style={{ width: '100%', borderRadius: 8, border: '1px solid var(--border)' }}
            />
          )}

          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { label: 'Total Vehicles', val: result.total_vehicles, color: colors.color },
              { label: 'Traffic Ratio',  val: `${Math.round(result.traffic_ratio * 100)}%`, color: colors.color },
              { label: 'Density Score',  val: result.weighted_density.toFixed(1), color: 'var(--text)' },
              { label: 'Level',          val: result.density_level, color: colors.color },
            ].map(({ label, val, color }) => (
              <div key={label} style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-display)', fontWeight: 700, letterSpacing: '0.08em', marginBottom: 4 }}>{label.toUpperCase()}</div>
                <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-display)', color }}>{val}</div>
              </div>
            ))}
          </div>

          {/* Vehicle breakdown */}
          {Object.keys(result.vehicle_counts).length > 0 && (
            <div style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 14px' }}>
              <div style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-display)', fontWeight: 700, letterSpacing: '0.08em', marginBottom: 10 }}>VEHICLE BREAKDOWN</div>
              {Object.entries(result.vehicle_counts).map(([type, count]) => (
                <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: 'var(--text2)', width: 80, fontFamily: 'var(--font-display)', textTransform: 'capitalize' }}>{type}</span>
                  <div style={{ flex: 1, height: 4, background: 'var(--bg4)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.min((count / result.total_vehicles) * 100, 100)}%`, background: 'var(--green)', borderRadius: 2 }} />
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-display)', color: 'var(--text)', width: 20, textAlign: 'right' }}>{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
