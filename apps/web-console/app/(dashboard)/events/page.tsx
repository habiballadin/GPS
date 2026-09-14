import { ModulePage } from '@/components/layout/ModulePage'
export default function SafetyEventsPage() { return <ModulePage resourceType="events" eyebrow="Safety" title="Safety events" description="Review speeding, harsh driving, collision, and SOS events." primaryAction="Review event" columns={['Event', 'Vehicle / Driver', 'Severity', 'Occurred', 'Status']} /> }
