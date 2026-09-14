import { ModulePage } from '@/components/layout/ModulePage'
export default function CertificationsPage() { return <ModulePage resourceType="certifications" eyebrow="Workforce" title="Certifications" description="Track licenses, endorsements, expiry dates, and compliance." primaryAction="Add certification" columns={['Driver', 'Certification', 'Expires', 'Status', 'Actions']} /> }
