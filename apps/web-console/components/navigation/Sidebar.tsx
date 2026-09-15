'use client'

import Link from 'next/link'

const groups = [
  { label: 'Command center', items: [['Dashboard', '/dashboard'], ['Live operations', '/live-map'], ['Alerts', '/alerts'], ['AI copilot', '/ai']] },
  { label: 'Fleet', items: [['Fleet overview', '/fleet'], ['Vehicles', '/vehicles'], ['Assignments', '/fleet/assignments'], ['Inspections', '/fleet/inspections'], ['Vehicle groups', '/fleet/groups'], ['Trailers', '/trailers'], ['Equipment', '/equipment'], ['Devices', '/devices'], ['Geofences', '/geofences']] },
  { label: 'Operations', items: [['Dispatch board', '/dispatch'], ['Trips', '/trips'], ['Orders', '/orders'], ['Routes', '/routes'], ['Stops', '/stops']] },
  { label: 'Control', items: [['Maintenance', '/maintenance'], ['Safety', '/safety'], ['Finance', '/finance'], ['Reports', '/reports'], ['Settings', '/settings']] },
] as const

export function Sidebar() {
  return <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 border-r border-white/10 bg-forest px-5 py-6 text-white lg:block"><Link href="/dashboard" className="mb-10 block"><span className="text-xs font-bold uppercase tracking-[0.24em] text-lime">Fleet OS</span><strong className="mt-2 block text-xl">Operations console</strong></Link>{groups.map((group) => <div key={group.label} className="mb-7"><p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-white/45">{group.label}</p><nav className="space-y-1">{group.items.map(([label, href]) => <Link key={href} href={href} className="block rounded-xl px-3 py-2 text-sm text-white/75 transition hover:bg-white/10 hover:text-white">{label}</Link>)}</nav></div>)}</aside>
}
