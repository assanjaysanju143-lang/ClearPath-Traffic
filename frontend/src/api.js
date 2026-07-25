import axios from 'axios'

// In local dev, Vite proxies /api and /ml to localhost:8000/8001 (see vite.config.js),
// so relative paths work with no config. In production (frontend and backend on
// different domains), set VITE_API_URL / VITE_ML_API_URL in the frontend's
// environment (e.g. Vercel project settings) to the deployed backend URLs.
export const API_BASE = import.meta.env.VITE_API_URL || '/api'
export const ML_API_BASE = import.meta.env.VITE_ML_API_URL || '/ml'

const api = axios.create({ baseURL: API_BASE })

export async function fetchRoutes(origin, destination, mode = 'car') {
  const { data } = await api.get('/routes', {
    params: { origin, destination, mode, alternatives: 3 }
  })
  return data
}

export async function fetchTrafficRatio(lat, lon) {
  const { data } = await api.get('/traffic/ratio', { params: { lat, lon } })
  return data
}

export async function fetchIncidents(minLat, minLon, maxLat, maxLon) {
  const { data } = await api.get('/incidents', {
    params: { min_lat: minLat, min_lon: minLon, max_lat: maxLat, max_lon: maxLon }
  })
  return data
}
