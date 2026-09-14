import { ModulePage } from '@/components/layout/ModulePage'
export default function AvailabilityPage() { return <ModulePage resourceType="availability" eyebrow="Workforce" title="Availability" description="See driver availability and assignment readiness." primaryAction="Set availability" columns={['Driver', 'Team', 'Availability', 'Next shift', 'Actions']} /> }
