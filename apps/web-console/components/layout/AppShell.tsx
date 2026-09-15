'use client'

import { Sidebar } from '@/components/navigation/Sidebar'
import { TopBar } from '@/components/navigation/TopBar'

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className="min-h-screen bg-mist"><Sidebar /><div className="lg:pl-64"><TopBar /><main className="motion-page p-5 lg:p-8">{children}</main></div></div>
}
