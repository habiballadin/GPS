'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type Vehicle = { id: number; name: string; imei: string; protocol: string; last_seen_at?: string }
type Position = { vehicle_id: number; device_imei: string; recorded_at: string; latitude: number; longitude: number; speed_kph: number; heading: number; ignition: boolean; satellites: number }

export function LiveFleet() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [connected, setConnected] = useState(false)
  useEffect(() => {
    if (!token) return
    void fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } }).then(async (response) => { if (response.ok) setVehicles(await response.json()) })
    const base = process.env.NEXT_PUBLIC_WS_URL ?? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
    const socket = new WebSocket(`${base}/api/v1/ws/live?token=${encodeURIComponent(token)}`)
    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)
    socket.onmessage = (event) => { const payload = JSON.parse(event.data) as { data?: Position[] }; setPositions(payload.data ?? []) }
    return () => socket.close()
  }, [token])
  const byVehicle = useMemo(() => new Map(positions.map((position) => [position.vehicle_id, position])), [positions])
  return <section><div className="mb-8 flex items-end justify-between"><div><p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Telemetry</p><h1 className="text-3xl font-bold tracking-tight">Live operations</h1><p className="mt-2 text-slate-500">Current positions delivered by the custom TCP gateway.</p></div><span className={`rounded-full px-3 py-2 text-xs font-bold ${connected ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-500'}`}>{connected ? '● Live stream connected' : '○ Waiting for stream'}</span></div><div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]"><div className="relative min-h-[520px] overflow-hidden rounded-2xl bg-[#dfe9dc] shadow-panel"><div className="absolute inset-0 opacity-40" style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '48px 48px' }} />{positions.map((position) => <div key={`${position.vehicle_id}-${position.recorded_at}`} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${Math.min(92, Math.max(8, ((position.longitude + 180) / 360) * 100))}%`, top: `${Math.min(88, Math.max(12, ((90 - position.latitude) / 180) * 100))}%` }}><div className="grid h-9 w-9 place-items-center rounded-full border-4 border-white bg-forest text-sm text-lime shadow-lg">●</div><span className="mt-1 block rounded bg-white px-2 py-1 text-[10px] font-bold shadow">{vehicles.find((vehicle) => vehicle.id === position.vehicle_id)?.name ?? position.device_imei}</span></div>)}{positions.length === 0 && <div className="absolute inset-0 grid place-items-center text-center"><div><p className="text-5xl text-forest/30">◎</p><p className="mt-3 font-bold text-forest">No live positions yet</p><p className="mt-1 text-sm text-forest/60">Register a device and point it to TCP 5001 or 5002.</p></div></div>}</div><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><div className="flex items-center justify-between"><h2 className="text-lg font-bold">Vehicle signal</h2><span className="text-xs text-slate-400">{positions.length} live</span></div><div className="mt-4 space-y-3">{vehicles.map((vehicle) => { const position = byVehicle.get(vehicle.id); return <div className="rounded-xl bg-mist p-4" key={vehicle.id}><div className="flex items-center justify-between"><strong>{vehicle.name}</strong><span className={`text-xs font-bold ${position ? 'text-green-700' : 'text-slate-400'}`}>{position ? 'ONLINE' : 'OFFLINE'}</span></div><p className="mt-1 text-xs text-slate-500">{position ? `${position.speed_kph.toFixed(0)} km/h · ${position.satellites} satellites` : vehicle.imei}</p></div> })}{vehicles.length === 0 && <p className="py-8 text-center text-sm text-slate-400">No registered vehicles.</p>}</div></div></div></section>
}
