'use client'

import { useEffect, useRef, useState, useMemo } from 'react'
import type { Map as LeafletMap, Marker, Polyline } from 'leaflet'
// Leaflet's stylesheet is processed by Next.js; its package does not expose TypeScript declarations.
// @ts-ignore -- intentional side-effect import for Leaflet's runtime styles
import 'leaflet/dist/leaflet.css'

export type ReplayPoint = { recorded_at: string; latitude: number; longitude: number; speed_kph: number }

function speedColor(speed: number, max: number): string {
  const t = max > 0 ? Math.min(speed / max, 1) : 0
  // green #22c55e → yellow #eab308 → red #ef4444
  if (t < 0.5) {
    const u = t * 2
    const r = Math.round(0x22 + u * (0xea - 0x22))
    const g = Math.round(0xc5 + u * (0xb3 - 0xc5))
    const b = Math.round(0x5e + u * (0x08 - 0x5e))
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
  }
  const u = (t - 0.5) * 2
  const r = Math.round(0xea + u * (0xef - 0xea))
  const g = Math.round(0xb3 + u * (0x44 - 0xb3))
  const b = Math.round(0x08 + u * (0x44 - 0x08))
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

function haversineM(a: ReplayPoint, b: ReplayPoint): number {
  const R = 6_371_000
  const dLat = ((b.latitude - a.latitude) * Math.PI) / 180
  const dLon = ((b.longitude - a.longitude) * Math.PI) / 180
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.latitude * Math.PI) / 180) *
      Math.cos((b.latitude * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2
  return R * 2 * Math.asin(Math.sqrt(s))
}

export function RouteReplay({ points, overspeedKph = 120 }: { points: ReplayPoint[]; overspeedKph?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<LeafletMap | null>(null)
  const segments = useRef<Polyline[]>([])
  const marker = useRef<Marker | null>(null)
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)

  const stats = useMemo(() => {
    if (points.length < 2) return null
    let dist = 0
    let maxSpd = 0
    let sumSpd = 0
    for (let i = 1; i < points.length; i++) {
      const seg = haversineM(points[i - 1], points[i])
      if (seg < 50_000) dist += seg
      maxSpd = Math.max(maxSpd, points[i].speed_kph)
      sumSpd += points[i].speed_kph
    }
    const durationMs = new Date(points[points.length - 1].recorded_at).getTime() - new Date(points[0].recorded_at).getTime()
    const avgSpd = sumSpd / (points.length - 1)
    return { dist, maxSpd, avgSpd, durationMs }
  }, [points])

  const maxSpeed = stats?.maxSpd ?? overspeedKph

  // Init map
  useEffect(() => {
    let disposed = false
    void import('leaflet').then(L => {
      if (disposed || !el.current || map.current) return
      map.current = L.map(el.current).setView([20.5937, 78.9629], 5)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map.current)
    })
    return () => { disposed = true; map.current?.remove(); map.current = null }
  }, [])

  // Draw gradient segments + start/end markers when points change
  useEffect(() => {
    void import('leaflet').then(L => {
      if (!map.current || !points.length) return
      segments.current.forEach(s => s.remove())
      segments.current = []
      marker.current?.remove()

      if (points.length < 2) return

      for (let i = 1; i < points.length; i++) {
        const color = speedColor(points[i].speed_kph, maxSpeed)
        const seg = L.polyline(
          [[points[i - 1].latitude, points[i - 1].longitude], [points[i].latitude, points[i].longitude]],
          { color, weight: 5, opacity: 0.85 }
        ).addTo(map.current!)
        segments.current.push(seg)
      }

      // Start pin (green) and end pin (red)
      const startIcon = L.divIcon({ className: '', html: '<div style="width:12px;height:12px;border-radius:50%;background:#22c55e;border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,.4)"></div>', iconAnchor: [6, 6] })
      const endIcon = L.divIcon({ className: '', html: '<div style="width:12px;height:12px;border-radius:50%;background:#ef4444;border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,.4)"></div>', iconAnchor: [6, 6] })
      L.marker([points[0].latitude, points[0].longitude], { icon: startIcon }).bindTooltip('Start').addTo(map.current!)
      L.marker([points[points.length - 1].latitude, points[points.length - 1].longitude], { icon: endIcon }).bindTooltip('End').addTo(map.current!)

      // Moving marker
      const movingIcon = L.divIcon({ className: '', html: '<div style="width:14px;height:14px;border-radius:50%;background:#174b3c;border:2px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.5)"></div>', iconAnchor: [7, 7] })
      marker.current = L.marker([points[0].latitude, points[0].longitude], { icon: movingIcon }).addTo(map.current!)

      const coords = points.map(p => [p.latitude, p.longitude] as [number, number])
      map.current!.fitBounds(L.latLngBounds(coords), { padding: [24, 24] })
      setIndex(0)
      setPlaying(false)
    })
  }, [points, maxSpeed])

  // Playback timer
  useEffect(() => {
    if (!playing || points.length < 2) return
    const timer = window.setInterval(() => {
      setIndex(v => {
        if (v >= points.length - 1) { setPlaying(false); return v }
        return v + 1
      })
    }, 600)
    return () => window.clearInterval(timer)
  }, [playing, points.length])

  // Move marker to current index
  useEffect(() => {
    if (!marker.current || !points[index]) return
    const p = points[index]
    marker.current.setLatLng([p.latitude, p.longitude])
      .bindTooltip(`${new Date(p.recorded_at).toLocaleString()} · ${p.speed_kph.toFixed(0)} km/h`, { permanent: false })
  }, [index, points])

  const cur = points[index]

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div ref={el} className="min-h-[460px] w-full" />

      {points.length > 0 && (
        <>
          {/* Speed gradient legend */}
          <div className="flex items-center gap-2 border-t border-slate-100 px-4 pt-3 pb-1">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Speed</span>
            <div className="h-2 flex-1 rounded-full" style={{ background: 'linear-gradient(to right, #22c55e, #eab308, #ef4444)' }} />
            <span className="text-[10px] text-slate-400">0</span>
            <span className="text-[10px] text-slate-400">→</span>
            <span className="text-[10px] text-slate-400">{maxSpeed.toFixed(0)} km/h</span>
          </div>

          {/* Controls */}
          <div className="flex flex-wrap items-center gap-3 px-4 py-3">
            <button
              className="rounded-xl bg-forest px-4 py-2 text-sm font-bold text-white"
              onClick={() => setPlaying(v => !v)}
            >
              {playing ? 'Pause' : 'Play'}
            </button>
            <button
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600"
              onClick={() => { setPlaying(false); setIndex(0) }}
            >
              Reset
            </button>
            <input
              className="min-w-[180px] flex-1"
              type="range" min={0} max={points.length - 1} value={index}
              onChange={e => { setPlaying(false); setIndex(Number(e.target.value)) }}
            />
            <span className="text-xs text-slate-400 tabular-nums">{index + 1} / {points.length}</span>
          </div>

          {/* Current point info */}
          {cur && (
            <div className="flex flex-wrap gap-4 border-t border-slate-100 px-4 py-3 text-xs text-slate-600">
              <span><span className="font-semibold">Time:</span> {new Date(cur.recorded_at).toLocaleString()}</span>
              <span><span className="font-semibold">Speed:</span> {cur.speed_kph.toFixed(0)} km/h</span>
              <span><span className="font-semibold">Lat:</span> {cur.latitude.toFixed(5)}</span>
              <span><span className="font-semibold">Lon:</span> {cur.longitude.toFixed(5)}</span>
            </div>
          )}
        </>
      )}

      {points.length === 0 && (
        <p className="p-6 text-sm text-slate-400">No historical positions available for replay.</p>
      )}
    </div>
  )
}
