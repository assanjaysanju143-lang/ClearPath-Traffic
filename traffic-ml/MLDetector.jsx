/**
 * MLDetector.jsx
 * Drop this into your traffic-frontend/src/components/ folder.
 * Lets users upload a road image OR use webcam → sends to ML API → shows annotated result.
 */

import { useState, useRef, useCallback } from 'react'

const ML_API = '/ml'

const LEVEL_COLORS = {
  LOW:      { color: '#00e676', bg: '#00e67618' },
  MODERATE: { color: '#ffab00', bg: '#ffab0018' },
  HIGH:     { color: '#ff3d3d', bg: '#ff3d3d18' },
}

export default function MLDetector() {
  const [mode, setMode]             = useState('upload')  // upload | webcam
  const [loading, setLoading]       = useState(false)
  const [result, setResult]         = useState(null)
  const [error, setError]           = useState(null)
  const [preview, setPreview]       = useState(null)
  const [webcamActive, setWebcamActive] = useState(false)

  const fileRef    = useRef()
  const videoRef   = useRef()
  const canvasRef  = useRef()
  const streamRef  = useRef()
  const intervalRef = useRef()

  const sendToML = useCallback(async (b64) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${ML_API}/detect/base64`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: b64, return_image: true }),
      })
      if (!res.ok) throw new Error(`ML API error: ${res.status}`)
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError('ML API not running. Start it with: py -3.12 run.py --server')
    } finally {
      setLoading(false)
    }
  }, [])

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

      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: 6 }}>
        {['upload', 'webcam'].map(m => (
          <button key={m} onClick={() => { setMode(m); setResult(null); setError(null) }}
            style={{
              flex: 1, padding: '8px 12px', borderRadius: 6, cursor: 'pointer',
              fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700,
              letterSpacing: '0.06em', textTransform: 'uppercase',
              background: mode === m ? 'var(--green-dim)' : 'var(--bg3)',
              border: `1px solid ${mode === m ? 'var(--green)' : 'var(--border)'}`,
              color: mode === m ? 'var(--green)' : 'var(--text3)',
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
            ? <button onClick={startWebcam} style={{ padding: '10px', background: 'var(--green)', color: '#000', border: 'none', borderRadius: 6, fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Start Camera</button>
            : <button onClick={stopWebcam} style={{ padding: '10px', background: 'var(--red-dim)', color: 'var(--red)', border: '1px solid var(--red)', borderRadius: 6, fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Stop Camera</button>
          }
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '12px', fontSize: 12, color: 'var(--text3)' }}>
          <span style={{ display: 'inline-block', width: 16, height: 16, border: '2px solid var(--border2)', borderTopColor: 'var(--green)', borderRadius: '50%', animation: 'spin 0.7s linear infinite', marginRight: 8, verticalAlign: 'middle' }} />
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
