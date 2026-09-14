import { ModulePage } from '@/components/layout/ModulePage'
export default function ExportsPage() { return <ModulePage resourceType="exports" eyebrow="Reporting" title="Exports" description="Download operational data and monitor generated files." primaryAction="Create export" columns={['Export', 'Format', 'Requested', 'Status', 'Actions']} /> }
