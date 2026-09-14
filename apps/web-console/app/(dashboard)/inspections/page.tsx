import { ModulePage } from '@/components/layout/ModulePage'
export default function InspectionsPage() { return <ModulePage resourceType="inspections" eyebrow="Maintenance" title="Inspections" description="Review vehicle inspections, findings, and sign-off status." primaryAction="Start inspection" columns={['Vehicle', 'Inspector', 'Result', 'Submitted', 'Actions']} /> }
