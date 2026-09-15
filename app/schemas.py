from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RegisterIn(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    email: str
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    expires_in: int | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=8)


class InvitationAccept(BaseModel):
    token: str
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    organization_id: int
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: Literal["admin", "manager", "operator", "viewer"] = "operator"


class UserRolePatch(BaseModel):
    role: Literal["admin", "manager", "operator", "viewer"]


class InvitationCreate(BaseModel):
    email: str
    role: Literal["admin", "manager", "operator", "viewer"] = "operator"


VEHICLE_TYPES = Literal[
    "bicycle", "motorcycle", "scooter", "atv",
    "car", "suv", "pickup", "van", "minibus",
    "bus", "truck", "semi_truck", "tanker", "tipper",
    "trailer", "tractor", "forklift", "excavator", "crane"
]


class VehicleIn(BaseModel):
    name: str
    imei: str = Field(min_length=8, max_length=32)
    license_plate: str | None = None
    protocol: str = "teltonika"
    vehicle_type: str = "car"
    device_profile: str | None = None
    device_profile_config: dict[str, Any] | None = None


class VehicleOut(VehicleIn):
    id: int
    active: bool
    last_seen_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class VehiclePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    license_plate: str | None = None
    protocol: str | None = None
    active: bool | None = None
    vehicle_type: str | None = None
    device_profile: str | None = None
    device_profile_config: dict[str, Any] | None = None


class FleetAssetIn(BaseModel):
    asset_tag: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    asset_type: Literal["trailer", "equipment", "container"] = "equipment"
    serial_number: str | None = None
    vin: str | None = None
    ownership: Literal["owned", "leased", "rented"] = "owned"
    purchase_date: datetime | None = None
    acquisition_cost: float | None = Field(default=None, ge=0)


class FleetAssetOut(FleetAssetIn):
    id: int
    status: str
    disposed_at: datetime | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AssetAttachmentOut(BaseModel):
    id: int
    asset_id: int
    vehicle_id: int | None = None
    attached_at: datetime
    detached_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class DeviceIn(BaseModel):
    imei: str = Field(min_length=8, max_length=32)
    protocol: Literal["teltonika", "gt06"] = "teltonika"
    model: str | None = None
    firmware_version: str | None = None


class DeviceOut(DeviceIn):
    id: int
    status: str
    last_seen_at: datetime | None = None
    created_at: datetime
    vehicle_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class DeviceBindingOut(BaseModel):
    id: int
    device_id: int
    vehicle_id: int
    bound_at: datetime
    unbound_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class DeviceHealthOut(BaseModel):
    device_id: int
    imei: str
    status: str
    last_seen_at: datetime | None = None
    freshness_seconds: float | None = None
    health: Literal["online", "stale", "offline", "never_seen"]
    vehicle_id: int | None = None


class DeviceCommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class DeviceCommandOut(DeviceCommandIn):
    id: int
    device_id: int
    status: str
    response: str | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class VehicleProfileIn(BaseModel):
    profile: str = Field(default="standard", min_length=1, max_length=40)
    config: dict[str, Any] = Field(default_factory=dict)


class VehicleProfileOut(VehicleProfileIn):
    vehicle_id: int
    model_config = ConfigDict(from_attributes=True)


class AssignmentIn(BaseModel):
    driver_id: int


class AssignmentOut(AssignmentIn):
    id: int
    vehicle_id: int
    assigned_at: datetime
    ended_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class MaintenanceIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    status: str = "planned"
    description: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PositionOut(BaseModel):
    vehicle_id: int
    device_imei: str
    recorded_at: datetime
    latitude: float
    longitude: float
    speed_kph: float
    heading: float
    ignition: bool
    satellites: int
    harsh_braking: bool = False
    harsh_acceleration: bool = False
    harsh_cornering: bool = False
    towing: bool = False
    jamming: bool = False
    sos: bool = False
    crash: bool = False
    door_open: bool = False
    ext_voltage_mv: int = 0
    battery_mv: int = 0
    fuel_level: int = 0
    model_config = ConfigDict(from_attributes=True)


class OdometerOut(BaseModel):
    vehicle_id: int
    total_distance_m: float
    engine_hours_s: float
    model_config = ConfigDict(from_attributes=True)


class FuelTransactionIn(BaseModel):
    vehicle_id: int
    driver_id: int | None = None
    occurred_at: datetime | None = None
    liters: float = Field(gt=0)
    total_cost: float = Field(ge=0)
    odometer_m: float | None = Field(default=None, ge=0)
    provider: str | None = None
    card_reference: str | None = None


class FuelTransactionOut(FuelTransactionIn):
    id: int
    occurred_at: datetime
    anomaly: bool
    model_config = ConfigDict(from_attributes=True)


class FuelSummaryOut(BaseModel):
    vehicle_id: int
    transactions: int
    liters: float
    total_cost: float
    cost_per_liter: float
    distance_m: float
    liters_per_100km: float | None = None
    anomaly_count: int


class VehicleCostRollupOut(BaseModel):
    vehicle_id: int
    distance_m: float
    fuel_cost: float
    maintenance_cost: float
    downtime_seconds: float
    total_cost: float
    cost_per_km: float | None = None
    utilization_percent: float | None = None


class FleetKpiOut(BaseModel):
    vehicles_total: int
    vehicles_active: int
    drivers_active: int
    devices_offline: int
    open_alerts: int
    open_incidents: int
    open_maintenance_orders: int
    delivery_orders_in_progress: int
    fuel_cost: float
    maintenance_cost: float
    distance_m: float


class AIFleetInsightOut(BaseModel):
    vehicle_id: int
    vehicle_name: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    factors: list[str]
    recommended_actions: list[str]
    generated_at: datetime


class MaintenancePredictionOut(BaseModel):
    vehicle_id: int
    vehicle_name: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high", "critical"]
    predicted_failure_window_days: int | None = None
    maintenance_due: bool
    factors: list[str]
    recommended_actions: list[str]
    data_points: int
    generated_at: datetime


class FleetExceptionOut(BaseModel):
    id: str
    category: str
    severity: Literal["low", "medium", "high", "critical"]
    title: str
    detail: str
    created_at: datetime
    next_action: str
    href: str


class TelemetryEventOut(BaseModel):
    id: int
    vehicle_id: int
    device_imei: str
    source_protocol: str
    event_key: str
    event_type: str
    recorded_at: datetime
    latitude: float
    longitude: float
    payload: dict[str, Any]
    model_config = ConfigDict(from_attributes=True)


class SIMCardIn(BaseModel):
    iccid: str = Field(min_length=6, max_length=32)
    imsi: str | None = None
    msisdn: str | None = None
    operator: str | None = None
    apn: str | None = None
    plan_name: str | None = None
    data_limit_mb: float | None = Field(default=None, ge=0)
    data_used_mb: float = Field(default=0, ge=0)
    status: Literal["active", "suspended", "expired", "lost", "provisioning"] = "active"
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    last_seen_at: datetime | None = None


class SIMCardOut(SIMCardIn):
    id: int
    organization_id: int
    device_id: int | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class IncidentIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    vehicle_id: int | None = None
    driver_id: int | None = None
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    description: str | None = Field(default=None, max_length=5000)
    evidence_urls: list[str] = Field(default_factory=list)
    evidence_file_ids: list[int] = Field(default_factory=list)


class IncidentPatch(BaseModel):
    status: Literal["open", "investigating", "resolved", "closed"] | None = None
    root_cause: str | None = None
    owner_id: int | None = None


class IncidentOut(IncidentIn):
    id: int
    status: str
    root_cause: str | None = None
    owner_id: int | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class CorrectiveActionIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    owner_id: int | None = None
    due_at: datetime | None = None


class CorrectiveActionOut(CorrectiveActionIn):
    id: int
    incident_id: int
    status: str
    completed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class AutoTripOut(BaseModel):
    id: int
    vehicle_id: int
    started_at: datetime
    ended_at: datetime | None = None
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    distance_m: float
    max_speed_kph: float
    harsh_events: int
    idle_seconds: int = 0
    driver_score: float
    model_config = ConfigDict(from_attributes=True)


class MaintenanceReminderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    odometer_threshold_m: float | None = None
    engine_hours_threshold_s: float | None = None


class MaintenanceReminderOut(MaintenanceReminderIn):
    id: int
    vehicle_id: int
    triggered: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InspectionIn(BaseModel):
    vehicle_id: int
    inspector_id: int | None = None
    template_id: int | None = None
    inspection_type: Literal["pre_trip", "post_trip", "periodic"] = "pre_trip"
    notes: str | None = Field(default=None, max_length=5000)
    checklist_results: dict[str, Any] = Field(default_factory=dict)
    evidence_urls: list[str] = Field(default_factory=list)
    signature_name: str | None = Field(default=None, max_length=160)
    evidence_file_ids: list[int] = Field(default_factory=list)
    signature_file_id: int | None = None
    defects: list["DefectIn"] = Field(default_factory=list)


class InspectionOut(BaseModel):
    id: int
    vehicle_id: int
    inspector_id: int | None = None
    template_id: int | None = None
    inspection_type: str
    status: str
    notes: str | None = None
    checklist_results: dict[str, Any] = Field(default_factory=dict)
    evidence_urls: list[str] = Field(default_factory=list)
    signature_name: str | None = None
    signed_at: datetime | None = None
    evidence_file_ids: list[int] = Field(default_factory=list)
    signature_file_id: int | None = None
    submitted_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InspectionTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    inspection_type: Literal["pre_trip", "post_trip", "periodic"] = "pre_trip"
    items: list[str] = Field(min_length=1, max_length=100)


class InspectionTemplateOut(InspectionTemplateIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


class DefectIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    severity: Literal["minor", "major", "critical"] = "minor"


class DefectOut(DefectIn):
    id: int
    vehicle_id: int
    inspection_id: int | None = None


class EvidenceFileOut(BaseModel):
    id: int
    purpose: str
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DriverDutyLogIn(BaseModel):
    status: Literal["off_duty", "sleeper", "on_duty", "driving"] = "driving"
    started_at: datetime
    ended_at: datetime | None = None
    source: Literal["manual", "telematics", "import"] = "manual"
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.ended_at and self.ended_at <= self.started_at:
            raise ValueError("Duty end must be after start")
        return self


class DriverDutyLogOut(DriverDutyLogIn):
    id: int
    driver_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DriverHoursOut(BaseModel):
    driver_id: int
    window_start: datetime
    on_duty_seconds: int
    driving_seconds: int
    remaining_on_duty_seconds: int
    remaining_driving_seconds: int
    compliant: bool


class ReportScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    report_type: Literal["fleet-kpis", "fleet-registry"] = "fleet-kpis"
    recipients: list[str] = Field(default_factory=list, max_length=20)
    cron: str = Field(min_length=5, max_length=120)
    timezone: str = "UTC"
    active: bool = True


class ReportScheduleOut(ReportScheduleIn):
    id: int
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ExternalImportIn(BaseModel):
    provider: Literal["fuel-card", "telematics", "maintenance", "generic"]
    resource_type: str = Field(min_length=1, max_length=60)
    source_reference: str | None = Field(default=None, max_length=500)


class ExternalImportOut(ExternalImportIn):
    id: int
    status: str
    rows_imported: int
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)
    status: str
    reported_at: datetime
    resolved_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ServicePlanIn(BaseModel):
    vehicle_id: int
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    interval_distance_m: float | None = Field(default=None, gt=0)
    interval_engine_hours_s: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def has_interval(self):
        if self.interval_distance_m is None and self.interval_engine_hours_s is None:
            raise ValueError("Set a distance or engine-hours interval")
        return self


class ServicePlanOut(ServicePlanIn):
    id: int
    active: bool
    last_service_distance_m: float
    last_service_engine_hours_s: float
    created_at: datetime
    last_serviced_at: datetime | None = None
    due: bool = False
    due_reason: str | None = None
    model_config = ConfigDict(from_attributes=True)


class PartIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    sku: str = Field(min_length=1, max_length=80)
    quantity_on_hand: float = Field(default=0, ge=0)
    reorder_level: float = Field(default=0, ge=0)
    unit_cost: float = Field(default=0, ge=0)


class PartOut(PartIn):
    id: int
    active: bool
    low_stock: bool = False
    model_config = ConfigDict(from_attributes=True)


class WorkOrderPartIn(BaseModel):
    part_id: int
    quantity: float = Field(gt=0)


class WorkOrderPartOut(BaseModel):
    id: int
    work_order_id: int
    part_id: int
    quantity: float
    unit_cost: float
    consumed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    contact_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)


class VendorOut(VendorIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


class WorkOrderIn(BaseModel):
    vehicle_id: int
    defect_id: int | None = None
    vendor_id: int | None = None
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    due_at: datetime | None = None
    labor_cost: float = Field(default=0, ge=0)
    parts_cost: float = Field(default=0, ge=0)
    external_cost: float = Field(default=0, ge=0)


class WorkOrderPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    priority: Literal["low", "medium", "high", "critical"] | None = None
    status: Literal["open", "in_progress", "on_hold", "completed", "cancelled"] | None = None
    due_at: datetime | None = None
    labor_cost: float | None = Field(default=None, ge=0)
    parts_cost: float | None = Field(default=None, ge=0)
    external_cost: float | None = Field(default=None, ge=0)
    vendor_id: int | None = None
    invoice_number: str | None = Field(default=None, max_length=100)


class WorkOrderOut(WorkOrderIn):
    id: int
    service_plan_id: int | None = None
    status: str
    opened_at: datetime
    completed_at: datetime | None = None
    total_cost: float
    invoice_number: str | None = None
    downtime_started_at: datetime | None = None
    downtime_ended_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class VehicleThresholdPatch(BaseModel):
    overspeed_kph: int | None = Field(default=None, ge=10, le=300)
    idle_alert_minutes: int | None = Field(default=None, ge=1, le=120)
    immobilizer_schedule: str | None = None  # "HH:MM-HH:MM" or null to disable


class ETARequest(BaseModel):
    dest_lat: float = Field(ge=-90, le=90)
    dest_lon: float = Field(ge=-180, le=180)


class DriverIn(BaseModel):
    name: str
    phone: str | None = None
    license_number: str | None = None


class DriverOut(DriverIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


class DriverCertificationIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    certificate_number: str | None = None
    expires_at: datetime | None = None


class DriverCertificationOut(DriverCertificationIn):
    id: int
    driver_id: int
    status: str
    model_config = ConfigDict(from_attributes=True)


class DriverAvailabilityIn(BaseModel):
    available_from: datetime
    available_until: datetime
    status: Literal["available", "unavailable", "leave"] = "available"

    @model_validator(mode="after")
    def valid_range(self):
        if self.available_until <= self.available_from:
            raise ValueError("Availability end must be after start")
        return self


class DriverAvailabilityOut(DriverAvailabilityIn):
    id: int
    driver_id: int
    model_config = ConfigDict(from_attributes=True)


class DriverSafetyOut(BaseModel):
    driver_id: int
    trips: int
    harsh_events: int
    overspeed_events: int
    average_score: float
    risk_level: Literal["low", "medium", "high"]


class DriverCoachingIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    notes: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None


class DriverCoachingOut(DriverCoachingIn):
    id: int
    driver_id: int
    status: str
    acknowledged_at: datetime | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TripIn(BaseModel):
    reference: str
    vehicle_id: int | None = None
    driver_id: int | None = None
    origin: str | None = None
    destination: str | None = None
    scheduled_at: datetime | None = None


class TripOut(TripIn):
    id: int
    status: str
    model_config = ConfigDict(from_attributes=True)


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    contact_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)


class CustomerOut(CustomerIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


class DeliveryOrderIn(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    customer_id: int | None = None
    cargo_description: str | None = Field(default=None, max_length=5000)
    cargo_weight_kg: float | None = Field(default=None, ge=0)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class DeliveryOrderAssign(BaseModel):
    vehicle_id: int
    driver_id: int


class DeliveryOrderOut(DeliveryOrderIn):
    id: int
    vehicle_id: int | None = None
    driver_id: int | None = None
    dispatcher_id: int | None = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DeliveryStopIn(BaseModel):
    address: str = Field(min_length=1, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    window_start: datetime | None = None
    window_end: datetime | None = None

    @model_validator(mode="after")
    def ordered_window(self):
        if self.window_start and self.window_end and self.window_end < self.window_start:
            raise ValueError("Window end must be after window start")
        return self


class DeliveryStopOut(DeliveryStopIn):
    id: int
    order_id: int
    sequence: int
    status: str
    proof_note: str | None = None
    completed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class DeliveryStopComplete(BaseModel):
    proof_note: str | None = Field(default=None, max_length=5000)


class DeliveryRouteSummaryOut(BaseModel):
    order_id: int
    stops: int
    mapped_stops: int
    distance_m: float
    estimated_minutes: float | None = None
    average_speed_kph: float
    provider: str = "straight_line"
    traffic_aware: bool = False
    traffic_factor: float = 1.0


class DeliveryRouteOptimizeOut(BaseModel):
    order_id: int
    stop_ids: list[int]
    distance_m: float
    estimated_minutes: float | None = None
    provider: str
    traffic_aware: bool
    traffic_factor: float


class DeliveryDeviationOut(BaseModel):
    order_id: int
    stop_id: int | None = None
    distance_to_next_stop_m: float | None = None
    threshold_m: float
    deviated: bool
    message: str


class DeliveryExceptionOut(BaseModel):
    id: int
    order_id: int
    stop_id: int | None = None
    kind: str
    message: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class GeofenceIn(BaseModel):
    name: str
    latitude: float = Field(default=0, ge=-90, le=90)
    longitude: float = Field(default=0, ge=-180, le=180)
    radius_m: float = Field(default=100, gt=0, le=1_000_000)
    geofence_type: Literal["circle", "polygon", "corridor"] = "circle"
    geometry: dict[str, Any] | None = None
    corridor_width_m: float | None = Field(default=None, gt=0, le=100_000)

    @model_validator(mode="after")
    def valid_geometry(self):
        if self.geofence_type in ("polygon", "corridor"):
            points = (self.geometry or {}).get("coordinates", [])
            minimum = 3 if self.geofence_type == "polygon" else 2
            if not isinstance(points, list) or len(points) < minimum: raise ValueError(f"{self.geofence_type} requires at least {minimum} coordinate pairs")
            if any(not isinstance(point, (list, tuple)) or len(point) != 2 or not (-90 <= float(point[0]) <= 90) or not (-180 <= float(point[1]) <= 180) for point in points): raise ValueError("Coordinates must be [latitude, longitude] pairs")
            if self.geofence_type == "corridor" and self.corridor_width_m is None: raise ValueError("Corridor width is required")
        return self


class GeofenceOut(GeofenceIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


RESOURCE_TYPES = Literal[
    "trailers", "equipment", "devices", "orders", "routes", "stops", "teams", "shifts",
    "certifications", "availability", "work-orders", "service-plans", "inspections", "parts",
    "vendors", "events", "incidents", "driver-safety", "investigations", "corrective-actions",
    "fuel", "costs", "reports", "analytics", "exports", "documents", "integrations",
    "notifications", "organization", "users", "roles", "api-keys", "ai", "geofences",
    "dispatch", "maintenance", "safety", "finance", "settings", "telematics", "orders", "audit"
]


class ResourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    status: str = Field(default="active", max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    details: dict[str, Any] = Field(default_factory=dict)


class ResourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    status: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    details: dict[str, Any] | None = None


class ResourceOut(ResourceIn):
    id: int
    resource_type: str
    organization_id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
