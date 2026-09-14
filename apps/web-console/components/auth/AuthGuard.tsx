'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/components/providers/AuthProvider'

export function AuthGuard({ children }: Readonly<{ children: React.ReactNode }>) {
  const { ready, token } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  useEffect(() => { if (ready && !token && pathname !== '/login') router.replace('/login') }, [pathname, ready, router, token])
  if (!ready || !token) return <div className="grid min-h-screen place-items-center text-sm text-slate-500">Loading workspace…</div>
  return children
}
