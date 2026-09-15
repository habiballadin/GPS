'use client'

import { useAuth } from '@/components/providers/AuthProvider'

export function TopBar() {
  const { logout } = useAuth()
  return <header className="sticky top-0 z-10 flex h-20 items-center justify-between border-b border-slate-200 bg-mist/90 px-5 backdrop-blur lg:px-8"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Workspace</p><p className="font-semibold">Fleet pilot · India</p></div><div className="flex items-center gap-3"><button className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 shadow-sm hover:border-forest/30 hover:shadow-md">Search ⌘K</button><button className="live-pulse rounded-xl border border-slate-200 bg-white px-3 py-2" aria-label="Notifications">🔔</button><button className="grid h-9 w-9 place-items-center rounded-full bg-lime font-bold text-forest shadow-sm hover:shadow-md" onClick={logout} title="Sign out">A</button></div></header>
}
