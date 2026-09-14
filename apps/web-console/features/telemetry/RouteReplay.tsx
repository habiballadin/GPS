'use client'
import { useEffect, useRef, useState } from 'react'
import type { Map as LeafletMap, Marker, Polyline } from 'leaflet'
import 'leaflet/dist/leaflet.css'

type Point = { recorded_at: string; latitude: number; longitude: number; speed_kph: number }

export function RouteReplay({ points }: { points: Point[] }) {
  const element = useRef<HTMLDivElement>(null); const map = useRef<LeafletMap | null>(null); const line = useRef<Polyline | null>(null); const marker = useRef<Marker | null>(null); const [index, setIndex] = useState(0); const [playing, setPlaying] = useState(false)
  useEffect(() => { let disposed = false; void import('leaflet').then(L => { if (disposed || !element.current || map.current) return; map.current = L.map(element.current).setView([20.5937, 78.9629], 5); L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map.current) }); return () => { disposed = true; map.current?.remove(); map.current = null } }, [])
  useEffect(() => { void import('leaflet').then(L => { if (!map.current || !points.length) return; line.current?.remove(); marker.current?.remove(); const coords = points.map(p => [p.latitude, p.longitude] as [number, number]); line.current = L.polyline(coords, { color: '#174b3c', weight: 4 }).addTo(map.current); marker.current = L.marker(coords[index]).addTo(map.current); map.current.fitBounds(L.latLngBounds(coords), { padding: [24, 24] }) }) }, [points])
  useEffect(() => { if (!playing || points.length < 2) return; const timer = window.setInterval(() => setIndex(value => { if (value >= points.length - 1) { setPlaying(false); return value } return value + 1 }), 700); return () => window.clearInterval(timer) }, [playing, points.length])
  useEffect(() => { if (!marker.current || !points[index]) return; marker.current.setLatLng([points[index].latitude, points[index].longitude]).bindTooltip(`${new Date(points[index].recorded_at).toLocaleString()} · ${points[index].speed_kph.toFixed(0)} km/h`) }, [index, points])
  return <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel"><div ref={element} className="min-h-[420px] w-full" />{points.length > 0 && <div className="flex flex-wrap items-center gap-3 p-4"><button className="rounded-xl bg-forest px-4 py-2 text-sm font-bold text-white" onClick={() => setPlaying(value => !value)}>{playing ? 'Pause' : 'Play route'}</button><input className="min-w-[220px] flex-1" type="range" min={0} max={points.length - 1} value={index} onChange={e => { setPlaying(false); setIndex(Number(e.target.value)) }} /><span className="text-xs text-slate-500">{index + 1} / {points.length}</span></div>}{points.length === 0 && <p className="p-6 text-sm text-slate-400">No historical positions available for replay.</p>}</div>
}
