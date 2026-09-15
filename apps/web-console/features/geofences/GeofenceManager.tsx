'use client'

import { useEffect, useRef, useState } from 'react'
import type { Map as LeafletMap, LayerGroup, Circle, Marker } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useAuth } from '@/components/providers/AuthProvider'

type Geofence = { id: number; name: string; latitude: number; longitude: number; radius_m: number; active: boolean }

function GeofenceMap({
  fences,
  pickedLatLon,
  onPick,
}: {
  fences: Geofence[]
  pickedLatLon: [number, number] | null
  onPick: (lat: number, lon: number) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<LeafletMap | null>(null)
  const fenceLayer = useRef<LayerGroup | null>(null)
  const pinMarker = useRef<Marker | null>(null)

  useEffect(() => {
    let disposed = false
    void import('leaflet').then(L => {
      if (disposed || !el.current || map.current) return
      map.current = L.map(el.current).setView([20.5937, 78.9629], 5)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map.current)
      fenceLayer.current = L.layerGroup().addTo(map.current)
      map.current.on('click', (e) => onPick(e.latlng.lat, e.latlng.lng))
    })
    return () => { disposed = true; map.current?.remove(); map.current = null }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Redraw fences
  useEffect(() => {
    void import('leaflet').then(L => {
      if (!fenceLayer.current) return
      fenceLayer.current.clearLayers()
      fences.forEach(f => {
        L.circle([f.latitude, f.longitude], {
          radius: f.radius_m,
          color: '#174b3c',
          fillColor: '#b7e35f',
          fillOpacity: 0.25,
          weight: 2,
        }).bindTooltip(`${f.name} (${f.radius_m}m)`).addTo(fenceLayer.current!)
      })
    })
  }, [fences])

  // Move pin marker
  useEffect(() => {
    void import('leaflet').then(L => {
      if (!map.current) return
      pinMarker.current?.remove()
      if (!pickedLatLon) return
      pinMarker.current = L.marker(pickedLatLon, {
        icon: L.divIcon({ className: '', html: '<div style="width:14px;height:14px;border-radius:50%;background:#ef4444;border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,.4)"></div>', iconAnchor: [7, 7] }),
      }).addTo(map.current)
      map.current.setView(pickedLatLon, Math.max(map.current.getZoom(), 13))
    })
  }, [pickedLatLon]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} className="min-h-[420px] w-full" />
}

export function GeofenceManager() {
  const { token } = useAuth()
  const [fences, setFences] = useState<Geofence[]>([])
  const [picked, setPicked] = useState<[number, number] | null>(null)
  const [form, setForm] = useState({ name: '', radius_m: '500' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const load = async () => {
    if (!token) return
    setLoading(true)
    try {
      const r = await fetch('/api/v1/geofences', { headers: { Authorization: `Bearer ${token}` } })
      const data = await r.json().catch(() => null)
      if (r.ok) setFences(data ?? [])
      else setError(typeof data?.detail === 'string' ? data.detail : `Could not load geofences (${r.status})`)
    } catch {
      setError('Could not reach the fleet API. Check the connection and try again.')
    } finally { setLoading(false) }
  }

  useEffect(() => { if (token) void load() }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    if (!picked || !form.name.trim()) { setError('Click the map to pick a center, then enter a name.'); return }
    const radius = parseFloat(form.radius_m)
    if (!radius || radius < 10) { setError('Radius must be at least 10 m.'); return }
    setSaving(true); setError('')
    const r = await fetch('/api/v1/geofences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ name: form.name.trim(), latitude: picked[0], longitude: picked[1], radius_m: radius }),
    })
    if (r.ok) {
      setForm({ name: '', radius_m: '500' }); setPicked(null); await load()
    } else {
      const data = await r.json().catch(() => null)
      setError(typeof data?.detail === 'string' ? data.detail : `Failed to create geofence (${r.status}).`)
    }
    setSaving(false)
  }

  const remove = async (id: number) => {
    await fetch(`/api/v1/geofences/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
    setFences(prev => prev.filter(f => f.id !== id))
  }

  return (
    <section>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Operations</p>
        <h1 className="text-3xl font-bold tracking-tight">Geofences</h1>
        <p className="mt-2 text-slate-500">Click the map to place a fence center, set a radius, and save. Entry/exit alerts fire automatically.</p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
        <div className="overflow-hidden rounded-2xl bg-[#dfe9dc] shadow-panel">
          <GeofenceMap fences={fences} pickedLatLon={picked} onPick={(lat, lon) => setPicked([lat, lon])} />
          <p className="p-3 text-xs text-slate-500">
            {picked ? `Selected: ${picked[0].toFixed(5)}, ${picked[1].toFixed(5)}` : 'Click anywhere on the map to set the fence center.'}
          </p>
        </div>

        <div className="space-y-4">
          {/* Create form */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
            <h2 className="text-lg font-bold">New geofence</h2>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold text-slate-600">
                Name
                <input
                  className="mt-1 w-full rounded-xl border border-slate-200 p-2.5"
                  placeholder="e.g. Depot A"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                />
              </label>
              <label className="block text-xs font-semibold text-slate-600">
                Radius (metres)
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-200 p-2.5"
                  min={10}
                  value={form.radius_m}
                  onChange={e => setForm(f => ({ ...f, radius_m: e.target.value }))}
                />
              </label>
              {picked && (
                <p className="rounded-xl bg-mist px-3 py-2 text-xs text-forest font-semibold">
                  Center: {picked[0].toFixed(5)}, {picked[1].toFixed(5)}
                </p>
              )}
              {error && <p className="text-xs text-red-600">{error}</p>}
              <button
                className="w-full rounded-xl bg-forest py-2.5 text-sm font-bold text-white disabled:opacity-50"
                disabled={saving}
                onClick={() => void create()}
              >
                {saving ? 'Saving…' : 'Create geofence'}
              </button>
            </div>
          </div>

          {/* Fence list */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Active fences</h2>
              <span className="rounded-full bg-mist px-3 py-1 text-xs font-bold text-forest">{loading ? '…' : fences.length}</span>
            </div>
            <div className="mt-4 max-h-80 space-y-2 overflow-y-auto">
              {fences.length === 0 && <p className="py-8 text-center text-sm text-slate-400">{loading ? 'Loading geofences…' : 'No geofences yet.'}</p>}
              {fences.map(f => (
                <div key={f.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3">
                  <div>
                    <p className="text-sm font-semibold">{f.name}</p>
                    <p className="text-xs text-slate-400">{f.latitude.toFixed(5)}, {f.longitude.toFixed(5)} · r={f.radius_m}m</p>
                  </div>
                  <button
                    className="text-xs font-bold text-red-400 hover:text-red-600"
                    onClick={() => void remove(f.id)}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
