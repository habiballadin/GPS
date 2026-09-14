import { ModulePage } from '@/components/layout/ModulePage'
export default function RoutesPage() { return <ModulePage resourceType="routes" eyebrow="Operations" title="Routes" description="Plan routes, compare ETAs, and review route performance." primaryAction="Plan route" columns={['Route', 'Stops', 'ETA', 'Status', 'Actions']} /> }
