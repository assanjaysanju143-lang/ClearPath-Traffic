import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Bangalore center default
const DEFAULT_CENTER = [12.9716, 77.5946]
const ROUTE_COLORS = ['#17803d', '#b45309', '#c0292a']

export default function MapView({ routes, selectedRoute, incidents, userLocation }) {
  const mapRef = useRef(null)
  const instanceRef = useRef(null)
  const layersRef = useRef([])
  const userMarkerRef = useRef(null)

  useEffect(() => {
    if (instanceRef.current) return
    instanceRef.current = L.map(mapRef.current, {
      center: DEFAULT_CENTER,
      zoom: 12,
      zoomControl: true,
      attributionControl: false,
    })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(instanceRef.current)
  }, [])

  useEffect(() => {
    const map = instanceRef.current
    if (!map) return

    // Clear previous layers
    layersRef.current.forEach(l => map.removeLayer(l))
    layersRef.current = []

    if (!routes || routes.length === 0) return

    const allCoords = []

    routes.forEach((route, i) => {
      const isSelected = selectedRoute === i
      const color = ROUTE_COLORS[i] || '#888'
      const weight = isSelected ? 6 : 3
      const opacity = isSelected ? 1 : 0.35

      // Generate mock path between Bangalore landmarks if no real polyline
      const mockPaths = [
        // Route 1: ORR path
        [[12.9716, 77.5946], [12.9750, 77.6200], [12.9780, 77.6600], [12.9698, 77.7499]],
        // Route 2: Sarjapur
        [[12.9716, 77.5946], [12.9200, 77.6100], [12.9350, 77.6800], [12.9698, 77.7499]],
        // Route 3: Inner city
        [[12.9716, 77.5946], [12.9900, 77.6200], [12.9850, 77.6700], [12.9698, 77.7499]],
      ]

      const coords = mockPaths[i] || mockPaths[0]
      allCoords.push(...coords)

      const polyline = L.polyline(coords, {
        color,
        weight,
        opacity,
        lineCap: 'round',
        lineJoin: 'round',
      }).addTo(map)

      layersRef.current.push(polyline)

      // Start & end markers only for selected
      if (isSelected) {
        const startIcon = L.divIcon({
          html: `<div style="width:14px;height:14px;background:${color};border-radius:50%;border:2px solid #ffffff;box-shadow:0 0 0 3px ${color}44"></div>`,
          className: '', iconAnchor: [7, 7]
        })
        const endIcon = L.divIcon({
          html: `<div style="width:14px;height:14px;background:${color};border-radius:2px;border:2px solid #ffffff;transform:rotate(45deg);box-shadow:0 0 0 3px ${color}44"></div>`,
          className: '', iconAnchor: [7, 7]
        })

        const sm = L.marker(coords[0], { icon: startIcon }).addTo(map)
        const em = L.marker(coords[coords.length - 1], { icon: endIcon }).addTo(map)
        layersRef.current.push(sm, em)
      }
    })

    // Add incident markers
    if (incidents && incidents.length > 0) {
      incidents.forEach(inc => {
        const incIcon = L.divIcon({
          html: `<div style="width:10px;height:10px;background:#c0292a;border-radius:50%;border:1.5px solid #ffffff;animation:pulse 2s infinite"></div>`,
          className: '', iconAnchor: [5, 5]
        })
        const m = L.marker([inc.latitude, inc.longitude], { icon: incIcon })
          .bindPopup(`<b style="font-family:sans-serif;font-size:12px">${inc.type}</b><br/><span style="font-size:11px">${inc.description}</span>`)
          .addTo(map)
        layersRef.current.push(m)
      })
    }

    // Fit map to routes
    if (allCoords.length > 0) {
      map.fitBounds(L.latLngBounds(allCoords), { padding: [40, 40] })
    }
  }, [routes, selectedRoute, incidents])

  // Live user location blue dot
  useEffect(() => {
    const map = instanceRef.current
    if (!map || !userLocation) return

    const icon = L.divIcon({
      html: `<div style="width:16px;height:16px;background:#2979ff;border-radius:50%;border:3px solid white;box-shadow:0 0 0 4px #2979ff44"></div>`,
      className: '', iconAnchor: [8, 8]
    })

    if (userMarkerRef.current) {
      userMarkerRef.current.setLatLng([userLocation.lat, userLocation.lon])
    } else {
      userMarkerRef.current = L.marker([userLocation.lat, userLocation.lon], { icon }).addTo(map)
      map.setView([userLocation.lat, userLocation.lon], 14)
    }
  }, [userLocation])

  return (
    <div
      ref={mapRef}
      style={{ width: '100%', height: '100%', borderRadius: 'var(--radius-lg)' }}
    />
  )
}
