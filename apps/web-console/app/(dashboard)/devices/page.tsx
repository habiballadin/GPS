import { ModulePage } from '@/components/layout/ModulePage'
export default function DevicesPage() { return <ModulePage resourceType="devices" eyebrow="Telematics" title="Devices" description="Enroll trackers, view protocol health, and manage device assignments." primaryAction="Register device" columns={['Device / IMEI', 'Protocol', 'Vehicle', 'Last seen', 'Actions']} /> }
