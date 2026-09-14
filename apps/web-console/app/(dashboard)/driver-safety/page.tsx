import { ModulePage } from '@/components/layout/ModulePage'
export default function DriverSafetyPage() { return <ModulePage resourceType="driver-safety" eyebrow="Safety" title="Driver safety" description="Compare driver risk patterns and coaching priorities." primaryAction="Create coaching plan" columns={['Driver', 'Safety score', 'Events', 'Trend', 'Actions']} /> }
