export type VehicleStatus = 'active' | 'available' | 'assigned' | 'maintenance' | 'out_of_service' | 'retired'
export type DeviceProtocol = 'teltonika' | 'gt06'

export interface Vehicle { id: number; organizationId: number; name: string; imei: string; protocol: DeviceProtocol; status: VehicleStatus; lastSeenAt?: string }
export interface Position { vehicleId: number; occurredAt: string; latitude: number; longitude: number; speedKph: number; headingDeg: number; ignitionOn: boolean }
export interface FleetEvent<T = unknown> { eventId: string; eventType: string; occurredAt: string; organizationId: number; aggregateId: string; schemaVersion: number; data: T }
