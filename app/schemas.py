from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


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


class VehicleIn(BaseModel):
    name: str
    imei: str = Field(min_length=8, max_length=32)
    license_plate: str | None = None
    protocol: str = "teltonika"
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
    device_profile: str | None = None
    device_profile_config: dict[str, Any] | None = None


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


class GeofenceIn(BaseModel):
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=1_000_000)


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
