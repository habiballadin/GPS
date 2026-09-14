import { ModulePage } from '@/components/layout/ModulePage'
export default function StopsPage() { return <ModulePage resourceType="stops" eyebrow="Operations" title="Stops" description="Coordinate stop sequence, arrival windows, and proof of delivery." primaryAction="Add stop" columns={['Stop', 'Trip', 'Window', 'Status', 'Actions']} /> }
